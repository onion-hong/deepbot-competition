"""Local synthetic tests only. New retained directories; no ROS or hardware startup."""
import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import threading
import unittest
import uuid
from unittest.mock import patch

from competition.data_tools import core
from competition.data_tools.adapter import camera_frame
from competition.data_tools.core import SessionWriter, load_json, validate_config
from competition.data_tools.offline import export_session, inspect_export, inspect_session
from competition.data_tools.synthetic import image_bytes
from competition.interfaces.validate import validate_stream


REPO = Path(__file__).resolve().parents[3]
RUN = Path(os.environ.get('DATA_TOOLS_TEST_ROOT', str(Path(__file__).parent / 'outputs'))) / uuid.uuid4().hex


class DataToolsTests(unittest.TestCase):
    def setUp(self):
        # Keep nested CLI/atomic-write paths short on Windows; preserve the full
        # test identity in each case directory instead of embedding it in paths.
        test_id = self.id()
        case_key = hashlib.sha256(test_id.encode('utf-8')).hexdigest()[:10]
        self.root = RUN / ('t_' + case_key)
        self.root.mkdir(parents=True, exist_ok=False)
        with (self.root / 'case.json').open('x', encoding='utf-8') as file:
            json.dump({'test_id': test_id, 'directory': self.root.name}, file, indent=2)
        self.cfg = load_json(REPO / 'competition/data_tools/synthetic.example.json')
        self.cfg['reserve_bytes'] = 0

    def writer(self, demo=False):
        if demo:
            self.cfg['mode'] = 'demonstration'
            self.cfg['feedback'] = dict(topic='/synthetic_b/feedback', message_type='nav_msgs/Odometry',
                                        source_clock_id='synthetic_source_clock')
        return SessionWriter(self.root, 'session', self.cfg)

    def frame(self, w, camera, stamp=1_000_000_000, **kwargs):
        return w.append(camera, image_bytes(camera), descriptor={'format': 'compressed'},
                        source_stamp_ns=stamp, **kwargs)

    def feedback(self, w, stamp=1_000_000_000, motion=None):
        m = motion or dict(vx_mps=0, vy_mps=0, wz_radps=0)
        return w.append('feedback', core.dumps(m).encode(), motion=m, source_stamp_ns=stamp)

    def pair(self, w, stamp=1_000_000_000):
        self.frame(w, 'high', stamp)
        self.frame(w, 'low', stamp + 1_000_000)

    def test_visual_dual_roundtrip_no_feedback_and_public_adapter(self):
        w = self.writer()
        self.pair(w)
        self.assertTrue(w.status()['ready'])
        w.close()
        q = export_session(w.path, self.root / 'derived')
        self.assertTrue(q['quality_ok'])
        report = inspect_export(self.root / 'derived')
        self.assertTrue(report['integrity_ok'])
        rows = [json.loads(s) for s in (self.root / 'derived/samples.jsonl').read_text().splitlines()]
        self.assertTrue(all(r['measured_motion'] is None and r['human_intent'] is None and
                            not r['demonstration_eligible'] for r in rows))
        self.assertNotEqual((self.root / 'derived/images/high/000000000.png').read_bytes(),
                            (self.root / 'derived/images/low/000000000.png').read_bytes())
        public = [json.loads(s) for s in (self.root / 'derived/camera_frames.jsonl').read_text().splitlines()]
        self.assertEqual(validate_stream(public), 2)

    def test_empty_format_same_frame_id_is_not_duplicate_physical_camera(self):
        w = self.writer()
        for camera in ('high', 'low'):
            r = self.frame(w, camera, message_metadata={'original_format': '', 'header_frame_id': 'camera'})
            self.assertTrue(r['valid'])
            self.assertEqual(r['message_metadata']['original_format'], '')
        w.close()
        self.assertTrue(inspect_session(w.path)[0]['quality_ok'])

    def test_duplicate_physical_id_and_topic_rejected_before_session(self):
        self.cfg['cameras']['low']['physical_id'] = self.cfg['cameras']['high']['physical_id']
        with self.assertRaises(ValueError):
            self.writer()
        self.assertFalse((self.root / 'session').exists())
        self.cfg['cameras']['low']['physical_id'] = 'other'
        self.cfg['cameras']['low']['topic'] = '/synthetic_b//high/'
        with self.assertRaises(ValueError):
            self.writer()

    def test_demonstration_requires_feedback_but_visual_does_not(self):
        w = self.writer(demo=True)
        self.pair(w)
        self.assertFalse(w.status()['ready'])
        self.feedback(w)
        self.assertTrue(w.status()['ready'])
        w.close()

    def test_missing_stale_and_bad_image_diagnostics(self):
        w = self.writer()
        self.frame(w, 'high')
        self.assertFalse(w.status()['ready'])
        r = w.append('low', b'not an image', descriptor={'format': 'compressed'}, source_stamp_ns=10)
        self.assertIn('bad_image', r['diagnostics'])
        self.assertEqual((w.path / r['raw_ref']).read_bytes(), b'not an image')
        self.frame(w, 'low', 20)
        self.assertFalse(w.status(time.monotonic_ns() + 600_000_000)['ready'])
        w.close()
        self.assertFalse(inspect_session(w.path)[0]['quality_ok'])

    def test_source_clock_backwards_duplicate_and_wall_jump_raw_retained(self):
        w = self.writer()
        self.frame(w, 'high', 100, receipt_unix_ns=1000)
        r = self.frame(w, 'high', 99, receipt_unix_ns=999)
        self.assertIn('source_clock_nonincreasing', r['diagnostics'])
        self.assertIn('wall_clock_backwards', r['diagnostics'])
        self.assertTrue((w.path / r['raw_ref']).exists())
        r = self.frame(w, 'high', 100, receipt_unix_ns=1001)
        self.assertFalse(r['valid'])
        self.frame(w, 'low', 100, receipt_unix_ns=1002)
        w.close()
        self.assertEqual(inspect_session(w.path)[0]['counts']['high'], 3)

    def test_time_mismatch_refused_without_changing_tolerance(self):
        w = self.writer(demo=True)
        self.feedback(w, 1_000_000_000)
        self.pair(w, 1_300_000_000)
        w.close()
        q = export_session(w.path, self.root / 'derived')
        self.assertFalse(q['quality_ok'])
        self.assertEqual(q['pairing']['tolerance_ns'], 50_000_000)
        for camera in ('high', 'low'):
            self.assertEqual(q['cameras'][camera]['feedback_paired'], 0)
            self.assertEqual(q['cameras'][camera]['rejection_reasons']['outside_tolerance'], 1)

    def test_each_camera_pair_independently_and_tolerance_boundary(self):
        w = self.writer(demo=True)
        self.feedback(w, 1_000_000_000)
        self.frame(w, 'high', 1_050_000_000)
        self.frame(w, 'low', 1_050_000_001)
        w.close()
        q = export_session(w.path, self.root / 'derived')
        self.assertEqual(q['cameras']['high']['feedback_paired'], 1)
        self.assertEqual(q['cameras']['low']['feedback_paired'], 0)
        pairs = [json.loads(s) for s in (self.root / 'derived/pair_audit.jsonl').read_text().splitlines()]
        self.assertEqual(pairs[0]['feedback']['signed_delta_ns'], -50_000_000)

    def test_cross_clock_and_explicit_receipt_fallback(self):
        self.cfg['cameras']['low']['source_clock_id'] = 'other_source'
        w = self.writer(demo=True)
        self.feedback(w)
        self.pair(w)
        w.close()
        q = export_session(w.path, self.root / 'derived')
        self.assertEqual(q['cameras']['low']['feedback_paired'], 0)
        from competition.data_tools.offline import PairIndex
        _, _, _, rows, _ = inspect_session(w.path)
        policy = dict(basis='receipt_approximate', tolerance_ns=50_000_000)
        pairs = PairIndex([r for r in rows if r['stream_id'] == 'feedback'], policy)
        self.assertTrue(pairs.match(rows[-1])[0]['accepted'])

    def test_stop_reverse_strafe_and_correction_semantics(self):
        w = self.writer(demo=True)
        # Deterministic synthetic receipt timeline; not dependent on Windows clock resolution.
        base = time.monotonic_ns()
        motions = [(0, 0, 0), (-.03, 0, 0), (0, .03, 0), (.02, 0, .1)]
        for i, (vx, vy, wz) in enumerate(motions):
            if i == 3:
                w.event('correction', 'start', 'fix1', 'synthetic correction', event_mono_ns=base+300_000_000)
            stamp = 1_000_000_000 + i * 100_000_000
            m = dict(vx_mps=vx, vy_mps=vy, wz_radps=wz)
            w.append('feedback', core.dumps(m).encode(), motion=m, source_stamp_ns=stamp,
                     receipt_mono_ns=base+i*100_000_000)
            self.frame(w, 'high', stamp, receipt_mono_ns=base+i*100_000_000+1_000_000)
            self.frame(w, 'low', stamp+1_000_000, receipt_mono_ns=base+i*100_000_000+2_000_000)
        w.event('correction', 'end', 'fix1', event_mono_ns=base+400_000_000)
        w.close()
        q = export_session(w.path, self.root / 'derived')
        self.assertEqual(q['cameras']['high']['demonstration_samples'], 3)
        self.assertEqual(q['cameras']['low']['excluded_correction'], 1)
        self.assertEqual(q['counts']['feedback'], 4)
        rows = [json.loads(s) for s in (self.root / 'derived/samples.jsonl').read_text().splitlines()]
        self.assertTrue(all(r['observed_command'] is None and r['human_intent'] is None for r in rows))

    def test_cross_stream_callback_reordering_is_not_wall_clock_regression(self):
        w = self.writer()
        later = self.frame(w, 'low', receipt_mono_ns=200, receipt_unix_ns=2000)
        earlier = self.frame(w, 'high', receipt_mono_ns=100, receipt_unix_ns=1000)
        self.assertTrue(later['valid'])
        self.assertTrue(earlier['valid'])
        equal = self.frame(w, 'high', 1_100_000_000, receipt_mono_ns=100, receipt_unix_ns=1001)
        self.assertTrue(equal['valid'])
        backward = self.frame(w, 'high', 1_200_000_000, receipt_mono_ns=101, receipt_unix_ns=999)
        self.assertIn('wall_clock_backwards', backward['diagnostics'])
        w.close()

    def test_callback_close_drains_admitted_waiters_before_complete(self):
        from competition.data_tools.callback_gate import CallbackGate
        gate = CallbackGate()
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        w = self.writer()
        def callback():
            started.set()
            release.wait(5)
            self.pair(w)
        worker = threading.Thread(target=lambda: gate.run(callback))
        worker.start()
        self.assertTrue(started.wait(2))
        def close():
            gate.close_intake()
            gate.drain()
            w.close()
            finished.set()
        closer = threading.Thread(target=close)
        closer.start()
        self.assertFalse(finished.wait(.05))
        release.set()
        worker.join(3)
        closer.join(3)
        self.assertTrue(finished.is_set())
        self.assertFalse(gate.run(lambda: self.fail('late callback admitted')))
        self.assertEqual(w.counts['high'], 1)
        self.assertTrue(inspect_session(w.path)[0]['quality_ok'])

    def test_unclosed_correction_excluded_and_orphan_end_rejected(self):
        w = self.writer(demo=True)
        w.event('takeover', 'start', 'x')
        self.feedback(w)
        self.pair(w)
        w.close()
        q = export_session(w.path, self.root / 'derived')
        self.assertEqual(q['cameras']['high']['demonstration_samples'], 0)
        from competition.data_tools.offline import correction_intervals
        _, errors = correction_intervals([{'event_type': 'correction', 'phase': 'end',
                                           'interval_id': 'orphan', 'event_mono_ns': 1}])
        self.assertTrue(errors)

    def test_command_and_feedback_are_distinct(self):
        self.cfg['command'] = dict(topic='/synthetic_b/command', message_type='geometry_msgs/Twist',
                                   source_clock_id='synthetic_source_clock')
        w = self.writer(demo=True)
        self.feedback(w)
        command = dict(vx_mps=.2, vy_mps=.1, wz_radps=.7)
        w.append('command', core.dumps(command).encode(), motion=command, source_stamp_ns=1_000_000_000)
        self.pair(w)
        w.close()
        export_session(w.path, self.root / 'derived')
        r = json.loads((self.root / 'derived/samples.jsonl').read_text().splitlines()[0])
        self.assertEqual(r['measured_motion']['wz_radps'], 0)
        self.assertEqual(r['observed_command']['wz_radps'], .7)
        self.assertIsNone(r['human_intent'])

    def test_session_and_export_no_overwrite(self):
        w = self.writer()
        self.pair(w)
        w.close()
        before = core.hash_file(w.path / 'manifest.json')
        with self.assertRaises(FileExistsError):
            self.writer()
        export_session(w.path, self.root / 'derived')
        with self.assertRaises(FileExistsError):
            export_session(w.path, self.root / 'derived')
        self.assertEqual(core.hash_file(w.path / 'manifest.json'), before)

    def test_append_disk_failure_incomplete(self):
        w = self.writer()
        with patch('competition.data_tools.core.write_new', side_effect=OSError('ENOSPC injected')):
            with self.assertRaises(OSError):
                self.frame(w, 'high')
        w.close()
        self.assertFalse(load_json(w.path / 'manifest.json')['complete'])
        self.assertTrue(w.failed)

    def test_close_failure_never_marks_complete(self):
        w = self.writer()
        self.pair(w)
        with patch('competition.data_tools.core.atomic_json', side_effect=OSError('close manifest injected')):
            with self.assertRaises(OSError):
                w.close()
        self.assertFalse(load_json(w.path / 'manifest.json')['complete'])
        self.assertTrue(w.closed)

    def test_initialization_failure_leaves_incomplete_manifest(self):
        real_write = core.write_new
        def fail_config(path, data):
            if Path(path).name == 'frozen_config.json':
                raise OSError('config failure injected')
            return real_write(path, data)
        with patch('competition.data_tools.core.write_new', side_effect=fail_config):
            with self.assertRaises(OSError):
                self.writer()
        self.assertFalse(load_json(self.root / 'session/manifest.json')['complete'])

    def test_raw_tamper_detected_and_incomplete_rejected(self):
        w = self.writer()
        self.pair(w)
        w.close(complete=False)
        with self.assertRaises(ValueError):
            export_session(w.path, self.root / 'derived')
        with (w.path / 'raw/high_000000000.bin').open('ab') as f:
            f.write(b'tamper')
        self.assertFalse(inspect_session(w.path)[0]['integrity_ok'])

    def test_unknown_source_domain_retained_not_fabricated_in_adapter(self):
        self.cfg['cameras']['high']['source_clock_id'] = 'unknown'
        w = self.writer()
        r = self.frame(w, 'high')
        self.assertEqual(r['source_stamp_ns'], 1_000_000_000)
        self.assertIsNone(camera_frame(w.manifest, r, 'images/high/0.png'))
        self.frame(w, 'low')
        w.close()

    def test_raw_rgb_stride_and_bad_stride(self):
        from competition.data_tools.core import decode_image
        im = decode_image(bytes([0, 0, 255, 99, 99, 99]),
                          dict(format='raw', width=1, height=1, step=6, encoding='bgr8'))
        self.assertEqual(im.getpixel((0, 0)), (255, 0, 0))
        with self.assertRaises(ValueError):
            decode_image(b'x', dict(format='raw', width=1, height=1, step=3, encoding='rgb8'))

    def test_split_preserved(self):
        self.cfg['split'] = 'validation'
        w = self.writer()
        self.pair(w)
        w.close()
        q = export_session(w.path, self.root / 'derived')
        self.assertEqual(q['split'], 'validation')
        for s in (self.root / 'derived/samples.jsonl').read_text().splitlines():
            self.assertEqual(json.loads(s)['split'], 'validation')

    def test_ros_adapter_static_no_publish_or_process_launch(self):
        source = ast.parse((REPO / 'competition/data_tools/ros_capture.py').read_text(encoding='utf-8'))
        forbidden = {'Publisher', 'ServiceProxy', 'Popen', 'system', 'VideoCapture'}
        self.assertFalse(any(isinstance(n, ast.Attribute) and n.attr in forbidden for n in ast.walk(source)))
        self.assertFalse(any(isinstance(n, ast.Import) and any(a.name == 'subprocess' for a in n.names)
                             for n in ast.walk(source)))

    def cli(self, *args):
        return subprocess.run([sys.executable, '-X', 'utf8', '-B', '-m', 'competition.data_tools', *args],
                              cwd=REPO, text=True, encoding='utf-8', capture_output=True, timeout=15)

    def test_cli_ros_missing_dependencies_no_session_created(self):
        if importlib.util.find_spec('rospy') is not None:
            self.skipTest('Never start ROS from local unit tests')
        self.cfg.update(role='manual_visual', acquisition_method='stationary')
        cfg = self.root / 'config.json'
        cfg.write_text(core.dumps(self.cfg), encoding='utf-8')
        p = self.cli('start', '--backend', 'ros', '--config', str(cfg), '--root', str(self.root),
                     '--session', 'no_ros', '--seconds', '1')
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertFalse((self.root / 'no_ros').exists())

    def test_cli_existing_session_and_low_space_exit_nonzero(self):
        w = self.writer()
        self.pair(w)
        w.close()
        cfg = self.root / 'config.json'
        cfg.write_text(core.dumps(self.cfg), encoding='utf-8')
        p = self.cli('start', '--backend', 'synthetic', '--config', str(cfg), '--root', str(self.root),
                     '--session', 'session', '--seconds', '1')
        self.assertEqual(p.returncode, 2)
        self.cfg['reserve_bytes'] = 10**30
        cfg2 = self.root / 'low_space.json'
        cfg2.write_text(core.dumps(self.cfg), encoding='utf-8')
        p = self.cli('start', '--backend', 'synthetic', '--config', str(cfg2), '--root', str(self.root),
                     '--session', 'low_space', '--seconds', '1')
        self.assertEqual(p.returncode, 2)
        self.assertFalse((self.root / 'low_space').exists())

    def test_cli_start_event_stop_export_inspect(self):
        cfg = self.root / 'config.json'
        cfg.write_text(core.dumps(self.cfg), encoding='utf-8')
        session = self.root / 'cli_session'
        log = (self.root / 'capture.log').open('x', encoding='utf-8')
        p = subprocess.Popen([sys.executable, '-X', 'utf8', '-B', '-m', 'competition.data_tools', 'start',
            '--backend', 'synthetic', '--config', str(cfg), '--root', str(self.root),
            '--session', 'cli_session', '--seconds', '10'], cwd=REPO, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 8
            while not (session / 'receipts.jsonl').exists() or (session / 'receipts.jsonl').stat().st_size == 0:
                self.assertIsNone(p.poll(), 'synthetic recorder exited before input')
                if time.monotonic() > deadline:
                    self.fail('synthetic start timeout')
                time.sleep(.05)
            e = self.cli('event', '--session', str(session), '--type', 'static_check', '--reason', 'synthetic test')
            self.assertEqual(e.returncode, 0, e.stderr)
            stop = self.cli('stop', '--session', str(session))
            self.assertEqual(stop.returncode, 0, stop.stderr)
            self.assertEqual(p.wait(timeout=10), 0)
        finally:
            if p.poll() is None:
                p.terminate()
                p.wait(timeout=5)
            log.close()
        exp = self.cli('export', '--session', str(session), '--output', str(self.root / 'derived'))
        self.assertEqual(exp.returncode, 0, exp.stderr + exp.stdout)
        check = self.cli('inspect', '--export', str(self.root / 'derived'))
        self.assertEqual(check.returncode, 0, check.stderr + check.stdout)
        self.assertEqual(len((session / 'events.jsonl').read_text().splitlines()), 1)


if __name__ == '__main__':
    print('RETAINED_TEST_ROOT=' + str(RUN))
    unittest.main()
