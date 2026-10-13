"""Only synthetic local tests: no imports from historical live-test modules."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from competition.interfaces.validate import request_is_current, validate_stream, loads
from competition.mission.core import Mission, NS
from competition.mission.synthetic import Trace, synthetic_config, complete_trace
from competition.mission.replay import replay


class MissionTests(unittest.TestCase):
    def run_trace(self, trace):
        m = Mission(trace.session, trace.clock, synthetic_config())
        outputs = [m.step(row) for row in trace.rows]
        return m, outputs

    def waiting(self, notice=True):
        t = Trace()
        t.startup()
        t.route_to_crosswalk()
        if notice:
            t.notice()
        return t

    def released(self):
        t = self.waiting()
        for _ in range(35):
            t.sensors()
        return t

    def assert_stop(self, output):
        self.assertEqual(output["motion_request"]["payload"]["mode"], "stop")
        self.assertTrue(output["state_event"]["payload"]["stop_required"])
        for key in ("vx_mps", "vy_mps", "wz_radps"):
            self.assertEqual(output["motion_request"]["payload"][key], 0)

    def test_two_complete_laps_down_first_and_second(self):
        for down in (1, 2):
            with self.subTest(down_lap=down):
                t = complete_trace(down)
                m, out = self.run_trace(t)
                self.assertEqual((m.state, m.lap_completed), ("complete", 2))
                self.assertTrue(all(o["accepted"] for o in out))
                self.assertEqual(sum(x["name"] == "lap_end" for x in m.ledger), 2)
                self.assertEqual(sum(x["name"] == "cone_pass" for x in m.ledger), 6)
                self.assertEqual(sum(x["name"] == "roundabout_orbit" for x in m.ledger), 2)
                self.assertTrue(any(o["state"] == "wait_barrier" for o in out))
                self.assertTrue(any(o["notice_request"] for o in out))
                for o in out:
                    self.assert_stop(o)
                    self.assertFalse(o["task_intent"]["motion_authorized"])
                    self.assertIn("trajectory_or_target_adapter_not_implemented", o["task_intent"]["execution_blockers"])
                records = [o[k] for o in out for k in ("state_event", "motion_request")]
                self.assertEqual(validate_stream(records), 2*len(out))

    def test_never_raised_waits_over_one_minute_without_fault(self):
        t = self.waiting()
        for _ in range(650):
            t.sensors(barrier="down")
        m, out = self.run_trace(t)
        self.assertEqual(m.state, "wait_barrier")
        self.assertIsNone(m.fault_reason)
        self.assertGreater(m.dwell_ns(), 60*NS)
        self.assertFalse(any(o["passage_evidence_ready"] for o in out))

    def test_unknown_and_clear_jitter_never_release(self):
        t = self.waiting()
        for barrier in ["down"]*35 + ["clear", "unknown", "clear", "clear", "down"]*10:
            t.sensors(barrier=barrier)
        m, out = self.run_trace(t)
        self.assertEqual(m.state, "wait_barrier")
        self.assertFalse(any(o["passage_evidence_ready"] for o in out))

    def test_single_clear_insufficient_after_dwell(self):
        t = self.waiting()
        for _ in range(35):
            t.sensors(barrier="down")
        t.sensors(barrier="clear")
        m, _ = self.run_trace(t)
        self.assertEqual(m.state, "wait_barrier")

    def test_less_than_three_seconds_rejects_crossing(self):
        t = self.waiting()
        for _ in range(27):
            t.sensors()
        t.task("crosswalk_depart", dict(crossing_confirmed=True))
        m, out = self.run_trace(t)
        self.assertEqual(m.state, "fault")
        self.assertIn("release conditions", m.fault_reason)
        self.assert_stop(out[-1])

    def test_exact_three_seconds_measured_and_tick_cannot_add_time(self):
        t = self.waiting()
        for _ in range(29):
            t.sensors()
        m, _ = self.run_trace(t)
        self.assertEqual(m.dwell_ns(), 2_900_000_000)
        t.now += 50_000_000
        o = m.step(t.event("tick"))
        self.assertEqual(o["dwell_ns"], 2_900_000_000)
        self.assertFalse(o["passage_evidence_ready"])
        start = len(t.rows)
        t.sensors(advance_ms=50)
        out = [m.step(r) for r in t.rows[start:]]
        self.assertEqual(out[-1]["dwell_ns"], 3*NS)
        self.assertEqual(m.state, "leave_crosswalk")

    def test_movement_each_axis_resets_dwell(self):
        for axis in ("vx", "vy", "wz"):
            with self.subTest(axis=axis):
                t = self.waiting()
                for _ in range(20):
                    t.sensors()
                t.sensors(**{axis: 0.02})
                for _ in range(20):
                    t.sensors()
                m, _ = self.run_trace(t)
                self.assertLess(m.dwell_ns(), 3*NS)
                self.assertEqual(m.state, "stopped_dwell")

    def test_feedback_loss_resets_continuity_and_ttl_not_renewed(self):
        t = self.released()
        m, _ = self.run_trace(t)
        old_basis = m.feedback["basis"]
        t.now += 2*NS
        o = m.step(t.event("tick"))
        self.assertEqual(o["dwell_ns"], 0)
        self.assertEqual(m.state, "stopped_dwell")
        request = o["motion_request"]
        self.assertEqual(request["payload"]["basis_stamp_ns"], old_basis)
        self.assertFalse(request_is_current(request, t.now, t.clock))
        start = len(t.rows)
        t.sensors()
        for row in t.rows[start:]:
            m.step(row)
        self.assertEqual(m.dwell_ns(), 0)

    def test_gap_without_explicit_tick_also_resets(self):
        t = self.waiting()
        for _ in range(20):
            t.sensors()
        t.sensors(advance_ms=2000)
        m, _ = self.run_trace(t)
        self.assertEqual(m.dwell_ns(), 0)
        self.assertEqual(m.state, "stopped_dwell")

    def test_pre_crosswalk_stopping_does_not_count_toward_dwell(self):
        t = Trace()
        t.startup()
        for _ in range(40):
            t.sensors()
        t.route_to_crosswalk()
        m, out = self.run_trace(t)
        self.assertEqual(out[-1]["dwell_ns"], 0)
        self.assertIsNone(m.stop_since)

    def test_delayed_sample_before_crosswalk_entry_cannot_backdate_dwell(self):
        t = self.waiting(notice=False)
        # Move arrival later than the preceding measured receipt, then supply a
        # new but delayed receipt whose basis predates the crossing-state entry.
        t.rows[-1]["stamp_ns"] += 50_000_000
        t.rows[-1]["basis_stamp_ns"] += 50_000_000
        t.now += 100_000_000
        t.event("feedback", dict(vx_mps=0, vy_mps=0, wz_radps=0,
                source_stamp_ns=t.now, source_clock_id="synthetic-odom-clock"),
                "feedback", basis=t.now-75_000_000)
        m, out = self.run_trace(t)
        self.assertTrue(out[-1]["accepted"])
        self.assertEqual(m.stop_since, t.now-50_000_000)
        self.assertEqual(m.dwell_ns(), 0)

    def test_notice_request_is_observable_but_ack_is_still_required(self):
        t = self.waiting(notice=False)
        for _ in range(40):
            t.sensors()
        m, out = self.run_trace(t)
        self.assertIsNotNone(out[-1]["notice_request"])
        self.assertEqual(m.state, "stopped_dwell")
        t.task("crosswalk_depart", dict(crossing_confirmed=True))
        m, _ = self.run_trace(t)
        self.assertEqual(m.state, "fault")

    def test_barrier_reclose_revokes_release_and_demands_new_stop(self):
        t = self.released()
        m, _ = self.run_trace(t)
        self.assertEqual(m.state, "leave_crosswalk")
        start = len(t.rows)
        t.sensors(barrier="down", vx=0.02)
        out = [m.step(r) for r in t.rows[start:]]
        self.assertFalse(out[-1]["passage_evidence_ready"])
        self.assertEqual(m.dwell_ns(), 0)
        self.assertEqual(m.state, "stopped_dwell")

    def test_empty_clear_and_stale_sensor_are_rejected(self):
        for kind in ("empty", "stale"):
            t = self.released()
            t.sensors()
            if kind == "empty":
                t.rows[-1]["data"]["observed"] = False
            else:
                t.rows[-1]["basis_stamp_ns"] -= NS
            m, out = self.run_trace(t)
            self.assertEqual(m.state, "fault")
            self.assertFalse(out[-1]["passage_evidence_ready"])

    def test_identical_marker_is_deduplicated_new_id_repeat_is_rejected(self):
        t = Trace()
        t.startup()
        t.marker(1)
        first = copy.deepcopy(t.rows[-1])
        t.rows.append(first)
        m, out = self.run_trace(t)
        self.assertEqual(m.marker, 1)
        self.assertEqual(out[-1]["reason"], "duplicate_ignored")
        self.assertEqual(sum(x["name"] == "marker" for x in m.ledger), 1)
        t.marker(1)
        m, _ = self.run_trace(t)
        self.assertEqual(m.state, "fault")

    def test_duplicate_lap_cannot_increment_twice(self):
        t = self.waiting()
        t.crossing()
        t.rows.append(copy.deepcopy(t.rows[-1]))
        m, out = self.run_trace(t)
        self.assertEqual(m.lap_completed, 1)
        self.assertEqual(m.state, "road")
        self.assertEqual(out[-1]["reason"], "duplicate_ignored")
        t.task("lap_end", dict(forward_crossing=True, rearmed=True))
        m, _ = self.run_trace(t)
        self.assertEqual(m.lap_completed, 1)
        self.assertEqual(m.state, "fault")

    def test_skipped_cones_island_s_curve_rejected(self):
        for missing in ("cone_pass", "roundabout_orbit", "s_exit"):
            t = self.waiting()
            t.rows = [r for r in t.rows if r["name"] != missing]
            m, _ = self.run_trace(t)
            self.assertEqual(m.state, "fault")
            self.assertEqual(m.lap_completed, 0)

    def test_wrong_cone_side_repeated_cone_and_wrong_ring_direction(self):
        for name, field, value in (("cone_pass", "side", "right"),
                                   ("roundabout_orbit", "direction", "cw"),
                                   ("roundabout_orbit", "path_around_island", False),
                                   ("roundabout_orbit", "swept_rad", 6.0)):
            t = self.waiting()
            row = next(r for r in t.rows if r["name"] == name)
            row["data"][field] = value
            m, _ = self.run_trace(t)
            self.assertEqual(m.state, "fault")
        t = self.waiting()
        cones = [r for r in t.rows if r["name"] == "cone_pass"]
        cones[1]["data"]["cone_id"] = cones[0]["data"]["cone_id"]
        m, _ = self.run_trace(t)
        self.assertIn("cone identity", m.fault_reason)

    def test_first_lap_must_not_enter_garage(self):
        t = self.waiting()
        t.crossing()
        t.task("garage_found", dict(entry_geometry_confirmed=True))
        m, _ = self.run_trace(t)
        self.assertEqual(m.lap_completed, 1)
        self.assertEqual(m.state, "fault")

    def test_two_laps_without_parking_cannot_complete(self):
        t = complete_trace()
        stop = next(i for i, r in enumerate(t.rows) if r["name"] == "garage_found")
        t.rows = t.rows[:stop]
        m, _ = self.run_trace(t)
        self.assertEqual((m.state, m.lap_completed), ("find_garage", 2))

    def test_parking_requires_reverse_stopped_and_geometry(self):
        for missing in ("reverse", "stop", "geometry", "rear"):
            t = complete_trace()
            if missing == "reverse":
                for r in t.rows:
                    if r["name"] == "feedback":
                        r["data"]["vx_mps"] = 0
            elif missing == "stop":
                next(r for r in reversed(t.rows) if r["name"] == "feedback")["data"]["vx_mps"] = -0.02
            elif missing == "geometry":
                t.rows[-1]["data"]["front_wheels_inside"] = False
            else:
                next(r for r in t.rows if r["name"] == "garage_aligned")["data"]["rear_clearance_confirmed"] = False
            m, _ = self.run_trace(t)
            self.assertEqual(m.state, "fault")

    def test_duplicate_completion_has_no_second_completion_transition(self):
        t = complete_trace()
        t.rows.append(copy.deepcopy(t.rows[-1]))
        m, out = self.run_trace(t)
        self.assertEqual((m.state, m.lap_completed), ("complete", 2))
        self.assertEqual(sum(o["transition"]["enter"] == "complete" for o in out), 1)
        self.assertEqual(sum(x["name"] == "parking_complete" for x in m.ledger), 1)
        self.assertEqual(out[-1]["reason"], "duplicate_ignored")

    def test_task_evidence_cannot_be_reused_with_fresh_identity(self):
        t = Trace()
        t.startup()
        t.marker(1)
        old_refs = t.rows[-1]["evidence_refs"]
        t.marker(2)
        t.rows[-1]["evidence_refs"] = old_refs
        m, _ = self.run_trace(t)
        self.assertEqual(m.marker, 1)
        self.assertEqual(m.fault_reason, "task evidence reused")

    def test_old_frames_new_envelope_do_not_renew_freshness(self):
        t = Trace()
        t.sensors()
        t.sensors()
        t.rows[-1]["data"]["frame_seq"] = 0
        m, out = self.run_trace(t)
        self.assertEqual(m.state, "fault")
        self.assertIn("replayed frame", m.fault_reason)
        self.assert_stop(out[-1])

    def test_feedback_old_source_timestamp_new_receipt_is_rejected(self):
        t = Trace()
        t.sensors()
        old = t.rows[0]["data"]["source_stamp_ns"]
        t.sensors()
        t.rows[-3]["data"]["source_stamp_ns"] = old
        m, _ = self.run_trace(t)
        self.assertIn("source replay", m.fault_reason)

    def test_all_invalid_inputs_stop_and_fault_latches(self):
        mutations = [("clock_id", "other-clock"), ("session_id", "other-session"),
                     ("stamp_ns", -1), ("lap", True), ("name", "complete"), ("seq", False),
                     ("evidence_refs", []), ("mission_version", "v99")]
        for key, value in mutations:
            t = Trace()
            t.startup()
            t.rows[-1][key] = value
            m, out = self.run_trace(t)
            self.assertEqual(m.state, "fault", (key, value))
            self.assert_stop(out[-1])
            t.now += NS
            self.assertEqual(m.step(t.event("tick"))["state"], "fault")

    def test_nonfinite_feedback_and_changed_duplicate_identity_rejected(self):
        for corruption in ("nan", "identity"):
            t = Trace()
            t.sensors()
            if corruption == "nan":
                t.rows[0]["data"]["vx_mps"] = float("nan")
            else:
                duplicate = copy.deepcopy(t.rows[-1])
                duplicate["data"]["value"] = "down"
                t.rows.append(duplicate)
            m, out = self.run_trace(t)
            self.assertEqual(m.state, "fault")
            self.assert_stop(out[-1])

    def test_oldest_required_input_controls_request_expiry(self):
        t = Trace()
        t.sensors()
        m, _ = self.run_trace(t)
        oldest = m.road["basis"]
        t.now += 100_000_000
        e = t.event("feedback", dict(vx_mps=0, vy_mps=0, wz_radps=0,
                    source_stamp_ns=t.now, source_clock_id="synthetic-odom-clock"), "feedback")
        o = m.step(e)
        self.assertEqual(o["motion_request"]["payload"]["basis_stamp_ns"], oldest)
        self.assertFalse(request_is_current(o["motion_request"], oldest+250_000_000, t.clock))

    def test_invalid_road_revokes_crosswalk_readiness(self):
        t = self.released()
        t.sensors(road=False)
        m, out = self.run_trace(t)
        self.assertFalse(out[-1]["passage_evidence_ready"])
        self.assertIn("road_missing_stale_or_invalid", out[-1]["task_intent"]["evidence_blockers"])
        self.assertEqual(m.state, "stopped_dwell")

    def test_wrong_notice_id_and_unrearmed_marker_rejected(self):
        t = self.waiting()
        t.rows[-1]["data"]["request_id"] = "different-crosswalk"
        m, _ = self.run_trace(t)
        self.assertEqual(m.state, "fault")
        t = Trace()
        t.startup()
        t.marker(1)
        t.rows[-1]["data"]["rearmed"] = False
        m, _ = self.run_trace(t)
        self.assertEqual(m.state, "fault")

    def test_public_adapter_preserves_old_frame_basis_and_rejects_empty_clear(self):
        path = Path(__file__).parents[2] / "interfaces" / "examples.jsonl"
        rows = [loads(s) for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]
        m = Mission("synthetic-001", "synthetic-clock-1", synthetic_config())
        fb = next(r for r in rows if r["kind"] == "motion_feedback")
        road = next(r for r in rows if r["kind"] == "road")
        self.assertTrue(m.step(fb)["accepted"])
        o = m.step(road)
        self.assertTrue(o["accepted"])
        self.assertEqual(m.road["basis"], road["payload"]["frame_stamp_ns"])
        barrier = copy.deepcopy(next(r for r in rows if r["kind"] == "detections"))
        barrier["payload"].update(camera_id="high", objects=[], barrier_state="clear")
        self.assertEqual(m.step(barrier)["state"], "fault")

    def test_replay_parse_error_audited_and_existing_dir_refused(self):
        allowed_root = Path(__file__).resolve().parent
        with tempfile.TemporaryDirectory(dir=allowed_root) as tmp:
            root = Path(tmp)
            self.assertTrue(root.resolve().is_relative_to(allowed_root))
            path = root / "bad.jsonl"
            path.write_text('{"a": 1, "a": 2}\n', encoding="utf-8")
            report = replay(path, synthetic_config(), "x", "clock", root / "out")
            self.assertEqual(report["state"], "fault")
            self.assertFalse(report["autonomous_success"])
            audit = json.loads((root / "out" / "audit.jsonl").read_text(encoding="utf-8"))
            self.assertIn("duplicate JSON key", audit["parse_error"])
            self.assert_stop(audit)
            with self.assertRaises(FileExistsError):
                replay(path, synthetic_config(), "x", "clock", root / "out")


if __name__ == "__main__":
    unittest.main()
