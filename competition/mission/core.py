"""Deterministic offline evidence state machine; never generates a driving speed.

Evidence truth is the adapter's responsibility. Synthetic traces exercise logic,
not vehicle capability. All timestamps are supplied by the caller, never wall time.
"""
from dataclasses import dataclass, asdict
from math import isfinite, pi
from copy import deepcopy

from competition.interfaces.validate import VERSION as PUBLIC_VERSION, validate
from . import VERSION


NS = 1_000_000_000
WAIT = {"approach_crosswalk", "stopped_dwell", "wait_barrier"}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def exact(data, keys):
    require(isinstance(data, dict) and set(data) == set(keys.split()), "invalid data fields")


def integer(value):
    return type(value) is int and value >= 0


def number(value):
    return type(value) in (int, float) and isfinite(value)


@dataclass(frozen=True)
class Config:
    # Deliberately no default cone-side order or claim that a site was measured.
    cone_sides: tuple
    route_profile_ref: str
    evidence_role: str = "synthetic"
    road_camera: str = "low"
    barrier_camera: str = "high"
    ttl_ms: int = 250
    feedback_gap_ms: int = 150
    clear_samples: int = 3
    clear_span_ms: int = 200
    stop_linear_mps: float = 0.005
    stop_angular_radps: float = 0.01

    def __post_init__(self):
        require(tuple(self.cone_sides) in (("left", "right", "left"),
                                         ("right", "left", "right")), "need explicit alternating cone sides")
        require(isinstance(self.route_profile_ref, str) and self.route_profile_ref, "route profile required")
        require(self.evidence_role in ("synthetic", "recorded_evidence"), "invalid evidence role")
        require(self.road_camera in ("high", "low") and self.barrier_camera in ("high", "low"), "camera role")
        require(type(self.ttl_ms) is int and 1 <= self.ttl_ms <= 500, "TTL outside contract")
        require(type(self.feedback_gap_ms) is int and 0 < self.feedback_gap_ms <= self.ttl_ms, "feedback gap")
        require(type(self.clear_samples) is int and self.clear_samples >= 2, "clear confirmation count")
        require(type(self.clear_span_ms) is int and self.clear_span_ms > 0, "clear confirmation span")
        require(number(self.stop_linear_mps) and self.stop_linear_mps >= 0, "stop linear threshold")
        require(number(self.stop_angular_radps) and self.stop_angular_radps >= 0, "stop angular threshold")


class Mission:
    def __init__(self, session_id, clock_id, config):
        require(isinstance(session_id, str) and session_id and isinstance(clock_id, str) and clock_id, "identity")
        self.session_id, self.clock_id, self.config = session_id, clock_id, config
        self.state, self.lap_completed, self.now_ns = "standby", 0, 0
        self.marker, self.cones, self.ring, self.s_curve = 0, [], "none", "none"
        self.feedback = self.road = self.barrier = None
        self.stop_since = None
        self.hold_not_before_ns = 0
        self.clear_run = []
        self.notice_id = self.notice_ack = None
        self.reverse_seen = False
        self.ledger, self.used_refs, self.seen, self.sequences = [], set(), {}, {}
        self.public_sources, self.frames = {}, {}
        self.sensor_sources = {}
        self.output_seq = 0
        self.fault_reason = None

    @property
    def lap(self):
        return min(self.lap_completed + 1, 2)

    def fresh(self, item, age_ms=None):
        return item is not None and 0 <= self.now_ns - item["basis"] < (age_ms or self.config.ttl_ms) * 1_000_000

    def stopped(self):
        return self.fresh(self.feedback, self.config.feedback_gap_ms) and self.feedback["stopped"]

    def dwell_ns(self):
        if self.stop_since is None or not self.stopped():
            return 0
        # Only covered measured intervals count. Ticks do not extend this value.
        return max(0, self.feedback["basis"] - self.stop_since)

    def clear(self):
        return (self.fresh(self.barrier) and self.barrier["value"] == "clear"
                and len(self.clear_run) >= self.config.clear_samples
                and self.clear_run[-1] - self.clear_run[0] >= self.config.clear_span_ms * 1_000_000)

    def sensors_ready(self):
        return self.fresh(self.feedback, self.config.feedback_gap_ms) and self.fresh(self.road) and self.road["valid"]

    def reset_hold(self):
        self.stop_since = None
        self.hold_not_before_ns = self.now_ns
        self.clear_run = []
        if self.state == "leave_crosswalk":
            self.state = "stopped_dwell"

    def refresh(self):
        if not self.fresh(self.feedback, self.config.feedback_gap_ms):
            self.stop_since = None
        if not self.fresh(self.barrier):
            self.clear_run = []
        if self.state == "leave_crosswalk" and not (self.clear() and self.sensors_ready()):
            self.reset_hold()
        if self.state in WAIT:
            if not self.stopped():
                self.stop_since = None
            if self.dwell_ns() < 3 * NS or not self.notice_ack:
                self.state = "stopped_dwell"
            else:
                self.state = "wait_barrier"
                if self.clear() and self.sensors_ready():
                    self.state = "leave_crosswalk"

    def _event(self, record):
        if record.get("schema_version") == PUBLIC_VERSION:
            return self._adapt(record)
        exact(record, "mission_version session_id clock_id source seq stamp_ns basis_stamp_ns event_id evidence_role name lap evidence_refs data")
        require(record["mission_version"] == VERSION, "mission version mismatch")
        return deepcopy(record)

    def _adapt(self, r):
        """Public sensor adapter only. No detection-to-route-completion inference."""
        validate(r)
        p, kind = r["payload"], r["kind"]
        require(kind in ("motion_feedback", "road", "detections"), "unsupported public input")
        source = kind + "/" + p.get("camera_id", p.get("source_topic", "default"))
        ref = "%s/%s/%s" % (r["session_id"], source, r["seq"])
        basis = p.get("frame_stamp_ns", r["stamp_ns"])
        if kind == "motion_feedback":
            require(p["source_stamp_ns"] is not None, "feedback source time missing")
            data = {k: p[k] for k in ("vx_mps", "vy_mps", "wz_radps", "source_stamp_ns", "source_clock_id")}
            name = "feedback"
        else:
            expected = self.config.road_camera if kind == "road" else self.config.barrier_camera
            require(p["camera_id"] == expected, "unexpected camera for configured adapter")
            data = {"frame_seq": p["frame_seq"]}
            if kind == "road":
                name = "road"
                data["valid"] = p["valid"]
            else:
                name = "barrier"
                data.update(value=p["barrier_state"], observed=any(x["class_name"] == "barrier" for x in p["objects"]))
        return dict(mission_version=VERSION, session_id=r["session_id"], clock_id=r["clock_id"],
                    source=source, seq=r["seq"], stamp_ns=r["stamp_ns"], basis_stamp_ns=basis,
                    event_id=ref, evidence_role=self.config.evidence_role, name=name, lap=self.lap,
                    evidence_refs=[ref], data=data)

    def step(self, record, now_ns=None):
        """Consume one record at an explicit reception time; return auditable output.

        Malformed/unordered inputs latch fault. Identical repeats are held and
        deduplicated without progress; a new valid observation can resume a hold.
        A new Mission instance/new session is required to restart after fault.
        """
        previous, ledger_before = self.state, len(self.ledger)
        accepted, reason, event = False, "", None
        try:
            supplied = record.get("stamp_ns") if isinstance(record, dict) else None
            now = supplied if now_ns is None else now_ns
            require(integer(now) and now >= self.now_ns, "arrival clock rollback or invalid time")
            self.now_ns = now
            require(isinstance(record, dict), "record must be an object")
            event = self._event(record)
            self._validate_event(event)
            identity = (event["source"], event["event_id"])
            if identity in self.seen:
                require(self.seen[identity] == event, "event identity reused with changed content")
                self.reset_hold()
                reason = "duplicate_ignored"
            else:
                key = event["source"]
                require(event["seq"] > self.sequences.get(key, -1), "source sequence rollback")
                require(self.state != "fault", self.fault_reason or "latched fault")
                self.refresh()
                self._consume(event)
                self.seen[identity] = deepcopy(event)
                self.sequences[key] = event["seq"]
                accepted, reason = True, event["name"] + "_accepted"
                self.refresh()
        except (ValueError, TypeError, KeyError) as exc:
            self.fault_reason = self.fault_reason or str(exc)
            self.state = "fault"
            self.reset_hold()
            reason = "rejected: " + self.fault_reason
        return self._output(previous, accepted, reason, event, ledger_before)

    def _validate_event(self, e):
        require(e["session_id"] == self.session_id and e["clock_id"] == self.clock_id, "session/clock mismatch")
        require(e["evidence_role"] == self.config.evidence_role, "evidence role mismatch")
        for key in ("source", "event_id", "name"):
            require(isinstance(e[key], str) and e[key], "empty event identity")
        require(integer(e["seq"]) and integer(e["stamp_ns"]) and integer(e["basis_stamp_ns"]), "invalid event time/sequence")
        require(e["basis_stamp_ns"] <= e["stamp_ns"] <= self.now_ns, "future input or basis")
        require(self.now_ns - e["basis_stamp_ns"] < self.config.ttl_ms * 1_000_000, "stale input")
        require(type(e["lap"]) is int and e["lap"] in (1, 2), "invalid lap")
        require(isinstance(e["evidence_refs"], list) and e["evidence_refs"] and
                all(isinstance(x, str) and x for x in e["evidence_refs"]), "missing evidence refs")
        require(len(set(e["evidence_refs"])) == len(e["evidence_refs"]), "duplicate evidence refs")
        require(isinstance(e["data"], dict), "data must be object")

    def _consume(self, e):
        name, d, basis = e["name"], e["data"], e["basis_stamp_ns"]
        if name == "tick":
            exact(d, "")
            return
        if name in ("feedback", "road", "barrier"):
            self._sensor(e)
            return
        require(e["lap"] == self.lap, "wrong lap evidence")
        require(self.state != "complete", "mission already complete")
        require(not (set(e["evidence_refs"]) & self.used_refs), "task evidence reused")
        require(self.sensors_ready(), "fresh road and measured feedback required")
        if name == "start":
            exact(d, "")
            require(self.state == "standby", "start outside standby")
            self.state = "exit_garage"
        elif name == "garage_exit":
            exact(d, "fully_out")
            require(self.state == "exit_garage" and d["fully_out"] is True, "garage exit evidence required")
            self.state = "road"
        elif name == "marker":
            exact(d, "number direction rearmed")
            require(self.state in ("road", "cones", "roundabout", "s_curve"), "marker outside route")
            require(type(d["number"]) is int and d["number"] == self.marker + 1 and d["number"] <= 8,
                    "marker order violation")
            require(d["direction"] == "forward" and d["rearmed"] is True, "marker crossing needs direction and rearm")
            if d["number"] == 5:
                require(len(self.cones) == 3, "three alternating cones required before marker 5")
            if d["number"] == 7:
                require(self.ring == "exited", "complete CCW island required before marker 7")
            if d["number"] == 8:
                require(self.s_curve == "exited", "S curve required before marker 8")
            self.marker = d["number"]
            self.state = "cones" if self.marker in (3, 4) else "road"
        elif name == "cone_pass":
            exact(d, "index cone_id side clearance_confirmed")
            require(self.marker in (3, 4) and self.state == "cones", "cone outside 3-5 region")
            require(type(d["index"]) is int and d["index"] == len(self.cones) + 1 and d["index"] <= 3, "cone order violation")
            require(isinstance(d["cone_id"], str) and d["cone_id"] and d["cone_id"] not in self.cones, "cone identity repeated")
            require(d["side"] == self.config.cone_sides[len(self.cones)] and d["clearance_confirmed"] is True,
                    "wrong cone side or unconfirmed clearance")
            self.cones.append(d["cone_id"])
        elif name == "roundabout_enter":
            exact(d, "entry_confirmed")
            require(self.marker == 6 and self.ring == "none" and d["entry_confirmed"] is True, "island entry order")
            self.ring, self.state = "entered", "roundabout"
        elif name == "roundabout_orbit":
            exact(d, "direction swept_rad loop_closure path_around_island")
            require(self.ring == "entered" and self.state == "roundabout", "island orbit order")
            require(d["direction"] == "ccw" and number(d["swept_rad"]) and d["swept_rad"] >= 2 * pi
                    and d["loop_closure"] is True and d["path_around_island"] is True, "full CCW circuit evidence required")
            self.ring = "orbited"
        elif name == "roundabout_exit":
            exact(d, "exit_confirmed")
            require(self.ring == "orbited" and d["exit_confirmed"] is True, "island exit before full orbit")
            self.ring, self.state = "exited", "road"
        elif name == "s_enter":
            exact(d, "")
            require(self.marker == 7 and self.s_curve == "none", "S entry order (profile places S at 7-8)")
            self.s_curve, self.state = "entered", "s_curve"
        elif name == "s_exit":
            exact(d, "continuous_path_confirmed")
            require(self.s_curve == "entered" and d["continuous_path_confirmed"] is True, "S exit evidence required")
            self.s_curve, self.state = "exited", "road"
        elif name == "crosswalk_arrive":
            exact(d, "before_line")
            require(self.marker == 8 and self.state == "road" and d["before_line"] is True, "must stop before crosswalk after marker 8")
            self.state = "approach_crosswalk"
            self.stop_since = None
            self.hold_not_before_ns = self.now_ns
            self.clear_run = []
            self.notice_id = "%s/crosswalk/%d" % (self.session_id, self.lap)
            self.notice_ack = None
        elif name == "notice_ack":
            exact(d, "request_id channel observable")
            require(self.state in WAIT and d["request_id"] == self.notice_id and
                    d["channel"] in ("speech", "display") and d["observable"] is True,
                    "observable notice acknowledgement required")
            self.notice_ack = e["event_id"]
        elif name == "crosswalk_depart":
            exact(d, "crossing_confirmed")
            require(self.state == "leave_crosswalk" and self.clear() and d["crossing_confirmed"] is True,
                    "crosswalk release conditions not met")
            self.state = "lap_confirm"
        elif name == "lap_end":
            exact(d, "forward_crossing rearmed")
            require(self.state == "lap_confirm" and self.marker == 8 and d["forward_crossing"] is True
                    and d["rearmed"] is True, "lap end missing ordered tasks or crossing")
            self.lap_completed += 1
            self.state = "road" if self.lap_completed == 1 else "find_garage"
            self.marker, self.cones, self.ring, self.s_curve = 0, [], "none", "none"
            self.stop_since = self.notice_id = self.notice_ack = None
        elif name == "garage_found":
            exact(d, "entry_geometry_confirmed")
            require(self.state == "find_garage" and self.lap_completed == 2 and d["entry_geometry_confirmed"] is True,
                    "garage search only after two laps")
            self.state = "align_garage"
        elif name == "garage_aligned":
            exact(d, "alignment_confirmed rear_clearance_confirmed")
            require(self.state == "align_garage" and d["alignment_confirmed"] is True
                    and d["rear_clearance_confirmed"] is True, "alignment/rear clearance missing")
            self.state, self.reverse_seen = "reverse_parking", False
        elif name == "parking_complete":
            exact(d, "front_wheels_inside no_board_contact geometry_confirmed")
            require(self.state == "reverse_parking" and self.lap_completed == 2 and self.reverse_seen
                    and self.stopped() and all(v is True for v in d.values()), "real reverse, stopped feedback and parking geometry required")
            self.state = "complete"
        else:
            raise ValueError("unknown event: " + name)
        self.ledger.append({"event_id": e["event_id"], "name": name, "lap": e["lap"],
                            "basis_stamp_ns": basis, "evidence_refs": list(e["evidence_refs"])})
        self.used_refs.update(e["evidence_refs"])

    def _sensor(self, e):
        d, name, basis, source = e["data"], e["name"], e["basis_stamp_ns"], e["source"]
        require(self.sensor_sources.get(name, source) == source, "sensor source changed within session")
        if name == "feedback":
            exact(d, "vx_mps vy_mps wz_radps source_stamp_ns source_clock_id")
            require(all(number(d[k]) for k in ("vx_mps", "vy_mps", "wz_radps")), "non-finite velocity")
            require(integer(d["source_stamp_ns"]) and d["source_stamp_ns"] > 0 and
                    isinstance(d["source_clock_id"], str) and d["source_clock_id"] not in ("", "unknown"), "feedback source clock required")
            old = self.public_sources.get(source)
            require(old is None or (old[0] == d["source_clock_id"] and old[1] < d["source_stamp_ns"]), "feedback source replay/reset")
            require(self.feedback is None or basis > self.feedback["basis"], "feedback receipt did not advance")
            stopped = (abs(d["vx_mps"]) <= self.config.stop_linear_mps and abs(d["vy_mps"]) <= self.config.stop_linear_mps
                       and abs(d["wz_radps"]) <= self.config.stop_angular_radps)
            if self.state in WAIT:
                if not stopped:
                    self.stop_since = None
                elif self.stop_since is None:
                    self.stop_since = max(basis, self.hold_not_before_ns)
            if self.state == "reverse_parking" and d["vx_mps"] < -self.config.stop_linear_mps:
                self.reverse_seen = True
            self.feedback = dict(basis=basis, stopped=stopped, ref=e["evidence_refs"][0])
            self.public_sources[source] = (d["source_clock_id"], d["source_stamp_ns"])
        else:
            exact(d, "frame_seq valid" if name == "road" else "frame_seq value observed")
            require(integer(d["frame_seq"]), "invalid frame sequence")
            old = self.frames.get(source)
            require(old is None or (d["frame_seq"] > old[0] and basis > old[1]), "replayed frame cannot refresh TTL")
            if name == "road":
                require(type(d["valid"]) is bool, "invalid road validity")
                self.road = dict(basis=basis, valid=d["valid"], ref=e["evidence_refs"][0])
            else:
                require(d["value"] in ("clear", "down", "unknown") and type(d["observed"]) is bool, "invalid barrier state")
                require(d["observed"] or d["value"] == "unknown", "empty detection cannot clear barrier")
                if d["value"] == "clear":
                    self.clear_run.append(basis)
                    # Keep start timestamp for span while bounding confirmations memory.
                    if len(self.clear_run) > self.config.clear_samples:
                        self.clear_run = [self.clear_run[0]] + self.clear_run[-(self.config.clear_samples - 1):]
                else:
                    self.clear_run = []
                self.barrier = dict(basis=basis, value=d["value"], ref=e["evidence_refs"][0])
            self.frames[source] = (d["frame_seq"], basis)
        self.sensor_sources[name] = source

    def _output(self, previous, accepted, reason, event, ledger_before):
        self.output_seq += 1
        refs = [x["event_id"] for x in self.ledger]
        basis_inputs = [x["basis"] for x in (self.feedback, self.road) if x is not None]
        if self.state in WAIT | {"leave_crosswalk"} and self.barrier:
            basis_inputs.append(self.barrier["basis"])
        if event and integer(event.get("basis_stamp_ns")) and event["basis_stamp_ns"] <= self.now_ns:
            basis_inputs.append(event["basis_stamp_ns"])
        basis = min(basis_inputs, default=self.now_ns)
        barrier_state = self.barrier["value"] if self.fresh(self.barrier) else "unknown"
        def public(kind, payload):
            r = dict(schema_version=PUBLIC_VERSION, kind=kind, session_id=self.session_id,
                     seq=self.output_seq, stamp_ns=self.now_ns, clock_id=self.clock_id, payload=payload)
            return validate(r)
        state_event = public("state_event", dict(event_id="mission-state-%d" % self.output_seq, state=self.state,
            lap_completed=self.lap_completed, segment="lap-%d/marker-%d" % (self.lap, self.marker),
            reason=reason, evidence_refs=refs, stop_required=True, barrier_state=barrier_state))
        request = public("motion_request", dict(source="mission", request_id="mission-stop-%d" % self.output_seq,
            mode="stop", vx_mps=0, vy_mps=0, wz_radps=0, ttl_ms=self.config.ttl_ms,
            basis_stamp_ns=basis, reason=reason + "; offline evidence only; trajectory controller unavailable"))
        return dict(mission_version=VERSION, evidence_role=self.config.evidence_role, hardware_access="none",
                    accepted=accepted, reason=reason, transition={"exit": previous if previous != self.state else None,
                    "enter": self.state if previous != self.state else None}, state=self.state,
                    lap_completed=self.lap_completed, dwell_ns=self.dwell_ns(),
                    passage_evidence_ready=accepted and self.state == "leave_crosswalk",
                    task_intent=self.intent(accepted, reason),
                    ledger_added=deepcopy(self.ledger[ledger_before:]),
                    notice_request=({"request_id": self.notice_id, "channel": "speech_or_display",
                                     "text": "人行道前停车，等待确认可通行", "execution": "offline_request_only"}
                                    if self.notice_id and not self.notice_ack else None),
                    state_event=state_event, motion_request=request)

    def intent(self, accepted=True, reason="snapshot"):
        """Module-local semantic target. This is never a motion permit."""
        goals = {"standby": "hold", "exit_garage": "exit_garage_required", "road": "follow_road",
                 "cones": "alternating_cones_required", "roundabout": "ccw_full_orbit_required",
                 "s_curve": "s_curve_required", "approach_crosswalk": "hold_before_crosswalk",
                 "stopped_dwell": "hold_before_crosswalk", "wait_barrier": "hold_for_barrier",
                 "leave_crosswalk": "crosswalk_traverse_required", "lap_confirm": "lap_crossing_required",
                 "find_garage": "garage_localization_required", "align_garage": "garage_alignment_required",
                 "reverse_parking": "reverse_required", "complete": "hold_complete", "fault": "hold_fault"}
        blockers = []
        if not accepted:
            blockers.append(reason)
        if not self.fresh(self.feedback, self.config.feedback_gap_ms):
            blockers.append("measured_feedback_missing_or_stale")
        if not self.fresh(self.road) or not self.road["valid"]:
            blockers.append("road_missing_stale_or_invalid")
        if self.state in WAIT | {"leave_crosswalk"}:
            if self.dwell_ns() < 3*NS and self.state != "leave_crosswalk":
                blockers.append("continuous_measured_stop_less_than_3_seconds")
            if not self.notice_ack:
                blockers.append("observable_notice_ack_missing")
            if not self.clear():
                blockers.append("barrier_not_confirmed_clear")
        if self.state == "reverse_parking" and not self.reverse_seen:
            blockers.append("measured_reverse_not_observed")
        if self.state == "fault":
            blockers.append(self.fault_reason or "latched_fault")
        return dict(intent_version=VERSION, goal=goals[self.state], marker_completed=self.marker,
                    cone_sides=list(self.config.cone_sides), cone_count=len(self.cones),
                    route_profile_ref=self.config.route_profile_ref, evidence_blockers=blockers,
                    evidence_ready_for_crosswalk=accepted and self.state == "leave_crosswalk",
                    execution_blockers=["trajectory_or_target_adapter_not_implemented",
                                        "offline_only_no_motion_authorization"],
                    motion_authorized=False)

    def snapshot(self):
        return dict(mission_version=VERSION, state=self.state, lap_completed=self.lap_completed,
                    evidence_role=self.config.evidence_role, config=asdict(self.config),
                    ledger=deepcopy(self.ledger), fault_reason=self.fault_reason, hardware_access="none")
