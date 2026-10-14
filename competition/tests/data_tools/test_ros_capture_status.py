"""Offline capture-loop regression; stub ROS, no network/devices or session writes."""
import contextlib
import io
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

from competition.data_tools import core, ros_capture


class CaptureStatusTests(unittest.TestCase):
    def test_lock_handoff_accepts_new_frame_but_rejects_unready_streams(self):
        config_path = Path(__file__).resolve().parents[2] / 'data_tools/vehicle.visual.example.json'
        for scenario in ('fresh_during_lock_wait', 'stale', 'missing', 'future'):
            with self.subTest(scenario=scenario):
                config = core.load_json(config_path)
                clock = [10_000_000_000]  # Beyond startup grace and the short duration.
                writer = core.SessionWriter.__new__(core.SessionWriter)
                writer.config = config
                writer.start_ns = 0
                writer.failed = False
                # A path test without creating any session or stop file.
                writer.path = Path('offline_capture_status_no_session')
                writer.counts = dict(high=1, low=1)
                writer.latest = {}
                writer.manifest = {'errors': []}
                writer.drain_requests = Mock()

                class HandoffLock:
                    def __enter__(self):
                        # Model a callback publishing its receipt while status waits
                        # for the writer lock. Both happen after the caller's old now.
                        clock[0] += 1_000_000
                        offset = 1 if scenario == 'future' else (
                            -config['max_age_ns'] - 1 if scenario == 'stale' else 0)
                        writer.latest = {} if scenario == 'missing' else {
                            role: dict(receipt_mono_ns=clock[0] + offset,
                                       valid=True, diagnostics=[])
                            for role in ('high', 'low')}

                    def __exit__(self, *args):
                        return False

                writer.lock = HandoffLock()

                def close(reason, complete):
                    writer.manifest.update(complete=complete, close_reason=reason)

                writer.close = Mock(side_effect=close)
                rospy = types.ModuleType('rospy')
                rospy.init_node = Mock()
                rospy.resolve_name = lambda topic: topic
                rospy.Subscriber = Mock(return_value=Mock())
                rospy.is_shutdown = lambda: False
                rospy.signal_shutdown = Mock()
                modules = {'rospy': rospy}
                for package, names in {
                    'sensor_msgs': ('CompressedImage', 'Image'),
                    'nav_msgs': ('Odometry',), 'geometry_msgs': ('Twist',)
                }.items():
                    parent = types.ModuleType(package)
                    msg = types.ModuleType(package + '.msg')
                    for name in names:
                        setattr(msg, name, type(name, (), {}))
                    parent.msg = msg
                    modules[package] = parent
                    modules[package + '.msg'] = msg

                with patch.dict(sys.modules, modules), \
                        patch.object(ros_capture, 'check_master') as preflight, \
                        patch.object(ros_capture, 'SessionWriter', return_value=writer), \
                        patch.object(core.time, 'monotonic_ns', side_effect=lambda: clock[0]), \
                        patch.object(core.shutil, 'disk_usage', return_value=types.SimpleNamespace(free=2**40)), \
                        patch.object(Path, 'exists', return_value=False), \
                        contextlib.redirect_stdout(io.StringIO()):
                    result = ros_capture.capture(Path('.'), 'offline', config, seconds=.1)
                preflight.assert_called_once()
                if scenario == 'fresh_during_lock_wait':
                    self.assertEqual(result, 0)
                    writer.close.assert_called_once_with('duration_elapsed', complete=True)
                    self.assertEqual(writer.manifest['errors'], [])
                else:
                    self.assertEqual(result, 2)
                    writer.close.assert_called_once_with('required_stream_missing_or_stale', complete=False)
                    self.assertIn('required_stream_missing_or_stale', writer.manifest['errors'])


if __name__ == '__main__':
    unittest.main()
