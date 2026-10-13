"""Synthetic evidence fixtures, intentionally independent of state-machine state.

The illustrative L/R/L cone order and S at 7-8 are NOT a surveyed site plan.
"""
from math import pi
from . import VERSION
from .core import Config


def synthetic_config():
    return Config(("left", "right", "left"), "synthetic:illustrative-route-not-site-confirmed")


class Trace:
    def __init__(self, session="synthetic-mission"):
        self.session, self.clock, self.now = session, "synthetic-monotonic", 1_000_000_000
        self.rows, self.seq, self.lap = [], {}, 1

    def event(self, name, data=None, source="task", basis=None, refs=None):
        seq = self.seq.get(source, 0)
        self.seq[source] = seq + 1
        ref = "%s/%s/%d" % (self.session, source, seq)
        row = dict(mission_version=VERSION, session_id=self.session, clock_id=self.clock,
                   source=source, seq=seq, stamp_ns=self.now, basis_stamp_ns=self.now if basis is None else basis,
                   event_id=ref, evidence_role="synthetic", name=name, lap=self.lap,
                   evidence_refs=refs or [ref + "/observation"], data=data or {})
        self.rows.append(row)
        return row

    def sensors(self, barrier="clear", vx=0, vy=0, wz=0, road=True, advance_ms=100):
        self.now += advance_ms * 1_000_000
        self.event("feedback", dict(vx_mps=vx, vy_mps=vy, wz_radps=wz,
                   source_stamp_ns=self.now, source_clock_id="synthetic-odom-clock"), "feedback")
        self.event("road", dict(frame_seq=self.seq.get("road", 0), valid=road), "road")
        self.event("barrier", dict(frame_seq=self.seq.get("barrier", 0), value=barrier,
                                  observed=barrier != "unknown"), "barrier")

    def task(self, name, data=None, **sensor_args):
        self.sensors(**sensor_args)
        return self.event(name, data)

    def marker(self, n):
        self.task("marker", dict(number=n, direction="forward", rearmed=True))

    def route_to_crosswalk(self):
        for n in (1, 2, 3):
            self.marker(n)
        self.task("cone_pass", dict(index=1, cone_id="cone-a", side="left", clearance_confirmed=True))
        self.marker(4)
        for i, side, identity in ((2, "right", "cone-b"), (3, "left", "cone-c")):
            self.task("cone_pass", dict(index=i, cone_id=identity, side=side, clearance_confirmed=True))
        self.marker(5)
        self.marker(6)
        self.task("roundabout_enter", dict(entry_confirmed=True))
        self.task("roundabout_orbit", dict(direction="ccw", swept_rad=2*pi,
                                          loop_closure=True, path_around_island=True))
        self.task("roundabout_exit", dict(exit_confirmed=True))
        self.marker(7)
        self.task("s_enter")
        self.task("s_exit", dict(continuous_path_confirmed=True))
        self.marker(8)
        self.task("crosswalk_arrive", dict(before_line=True))

    def notice(self):
        self.task("notice_ack", dict(request_id="%s/crosswalk/%d" % (self.session, self.lap),
                                     channel="display", observable=True))

    def crossing(self, down=False):
        self.notice()
        for _ in range(40):
            self.sensors(barrier="down" if down else "clear")
        for _ in range(4):
            self.sensors(barrier="clear")
        self.task("crosswalk_depart", dict(crossing_confirmed=True))
        self.task("lap_end", dict(forward_crossing=True, rearmed=True))
        self.lap = 2

    def startup(self):
        self.task("start")
        self.task("garage_exit", dict(fully_out=True))

    def parking(self):
        self.task("garage_found", dict(entry_geometry_confirmed=True))
        self.task("garage_aligned", dict(alignment_confirmed=True, rear_clearance_confirmed=True))
        self.sensors(vx=-0.02)
        self.task("parking_complete", dict(front_wheels_inside=True, no_board_contact=True,
                                           geometry_confirmed=True))


def complete_trace(down_lap=1):
    trace = Trace("synthetic-down-lap-%d" % down_lap)
    trace.startup()
    for lap in (1, 2):
        trace.route_to_crosswalk()
        trace.crossing(down=lap == down_lap)
    trace.parking()
    return trace


def demo_traces():
    result = {"complete_down_first": complete_trace(1), "complete_down_second": complete_trace(2)}
    t = Trace("synthetic-never-raised")
    t.startup()
    t.route_to_crosswalk()
    t.notice()
    for _ in range(650):
        t.sensors(barrier="down")
    result["never_raised"] = t
    t = Trace("synthetic-skip-cones")
    t.startup()
    for n in range(1, 6):
        t.marker(n)
    result["reject_skip_cones"] = t
    t = Trace("synthetic-short-stop")
    t.startup()
    t.route_to_crosswalk()
    t.notice()
    for _ in range(10):
        t.sensors()
    t.task("crosswalk_depart", dict(crossing_confirmed=True))
    result["reject_short_stop"] = t
    t = complete_trace(1)
    t.rows = [r for r in t.rows if r["name"] not in ("garage_found", "garage_aligned", "parking_complete")]
    result["no_parking_no_complete"] = t
    return result
