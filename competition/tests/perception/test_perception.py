import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image

from competition.interfaces.validate import VERSION, loads, validate_stream
from competition.perception.road import candidate, road_payload
from competition.perception.replay import load_image, replay
from competition.perception.synthetic import SCENES, scene


class GeometryTests(unittest.TestCase):
    def test_straight_and_turn_signs(self):
        for name, sign in [('straight', 0), ('left_curve', -1), ('right_curve', 1)]:
            with self.subTest(name=name):
                d = candidate(scene(name))
                self.assertTrue(d['candidate_valid'], d)
                if sign:
                    self.assertGreater(d['offset_px'] * sign, 3)
                else:
                    self.assertLess(abs(d['offset_px']), 1)
                self.assertEqual(d['offset_px'], d['target_x_px']-d['reference_x_px'])

    def test_original_pixel_scaling(self):
        small = candidate(scene('right_curve'))
        large = candidate(scene('right_curve', 1280, 720))
        self.assertTrue(large['candidate_valid'])
        self.assertAlmostEqual(small['offset_px']/320, large['offset_px']/1280, delta=.005)
        self.assertGreater(large['path_px'][-1][1], 600)

    def test_moderate_shadow(self):
        self.assertTrue(candidate(scene('shadow'))['candidate_valid'])

    def test_deep_shadow_is_unknown(self):
        dark = (scene('straight').astype(float)*.25).astype(np.uint8)
        self.assertFalse(candidate(dark)['candidate_valid'])

    def test_no_line_clutter_and_occlusion(self):
        for name in ('no_line','black_clutter','occlusion','blue_only','discontinuous','no_blue_boundary'):
            with self.subTest(name=name):
                d = candidate(scene(name))
                self.assertFalse(d['candidate_valid'], d)
                self.assertEqual(d['path_px'], [])
                self.assertIsNone(d['offset_px'])

    def test_junctions_never_pick_one_branch(self):
        for name in ('branch','roundabout','two_roads'):
            with self.subTest(name=name):
                d = candidate(scene(name))
                self.assertFalse(d['candidate_valid'])
                self.assertEqual(d['reason'], 'multiple_paths_or_branch')

    def test_color_order_and_monochrome(self):
        rgb = scene('right_curve')
        self.assertEqual(candidate(rgb), candidate(rgb[:,:,::-1], 'bgr8'))
        self.assertFalse(candidate(rgb[:,:,::-1], 'rgb8')['candidate_valid'])
        self.assertEqual(candidate(rgb[:,:,0], 'mono8')['reason'], 'color_unavailable')
        with self.assertRaises(ValueError):
            candidate(rgb.astype(float))

    def test_no_stale_path_and_pixel_validity(self):
        p = dict(camera_id='low', frame_seq=1, width_px=320, height_px=240, receipt_mono_ns=1)
        for name in ('straight','narrow_dark_shadow','no_line'):
            d = candidate(scene(name))
            road = road_payload(p, d)
            self.assertFalse(d['clearance_verified'])
            self.assertEqual(road['valid'], name != 'no_line')
            if name == 'no_line':
                self.assertEqual(road['path_px'], [])
                self.assertIsNone(road['target_x_px'])
                self.assertEqual(road['quality'], 0)
            else:
                self.assertTrue(road['path_px'])
                self.assertIsNotNone(road['offset_px'])


class ReplayTests(unittest.TestCase):
    def setUp(self):
        # All persistent/temp test writes stay within C-owned directory.
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.temp.name)
        self.images = self.root / 'images'
        self.images.mkdir()
        Image.fromarray(scene('right_curve')).save(self.images / '图像.png')

    def tearDown(self):
        self.temp.cleanup()

    def frame(self):
        return dict(schema_version=VERSION, kind='camera_frame', session_id='synthetic-source',
                    seq=0, stamp_ns=123, clock_id='synthetic-acquisition-clock',
                    payload=dict(camera_id='high', physical_id='synthetic-usb-high', frame_seq=12,
                    width_px=320, height_px=240, encoding='bgr8', image_ref='图像.png',
                    source_stamp_ns=80, source_clock_id='synthetic-source-clock',
                    receipt_unix_ns=1000, receipt_mono_ns=123))

    def run_manifest(self, frames):
        manifest = self.root / 'frames.jsonl'
        manifest.write_text('\n'.join(json.dumps(f) for f in frames), encoding='utf-8')
        return replay(self.images, self.root/'result', manifest=manifest, dataset_role='synthetic')

    def test_directory_output_contract_and_refuse_overwrite(self):
        result = replay(self.images, self.root/'result', camera_id='low', dataset_role='synthetic')
        self.assertEqual(result['processed'], 1)
        self.assertEqual(result['candidate_valid'], 1)
        self.assertEqual(result['public_valid'], 1)
        self.assertFalse(result['motion_permission'])
        rows = [loads(s) for s in (self.root/'result/records.jsonl').read_text().splitlines()]
        self.assertEqual(validate_stream(rows), 2)
        self.assertTrue(rows[1]['payload']['valid'])
        self.assertGreater(rows[1]['payload']['offset_px'], 0)
        self.assertTrue((self.root/'result'/rows[0]['payload']['image_ref']).is_file())
        self.assertIsNone(rows[0]['payload']['source_stamp_ns'])
        self.assertTrue((self.root/'result/overlays/000001.png').is_file())
        before = (self.root/'result/summary.json').read_bytes()
        with self.assertRaises(FileExistsError):
            replay(self.images, self.root/'result', camera_id='low')
        self.assertEqual(before, (self.root/'result/summary.json').read_bytes())

    def test_manifest_provenance_and_replay_clock(self):
        source = self.frame()
        result = self.run_manifest([source])
        self.assertEqual(result['processed'], 1)
        provenance = loads((self.root/'result/provenance.jsonl').read_text(encoding='utf-8'))
        self.assertEqual(provenance['original_record'], source)
        rows = [loads(s) for s in (self.root/'result/records.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual(validate_stream(rows), 2)
        self.assertNotEqual(rows[0]['clock_id'], source['clock_id'])
        self.assertEqual(rows[0]['payload']['source_stamp_ns'], 80)
        self.assertEqual(rows[0]['payload']['frame_seq'], 12)
        self.assertEqual(rows[0]['payload']['encoding'], 'rgb8')

    def test_full_batch_contract_and_asset_resolution(self):
        for name in SCENES:
            Image.fromarray(scene(name)).save(self.images/(name+'.png'))
        result = replay(self.images, self.root/'result', camera_id='low', dataset_role='synthetic')
        self.assertEqual(result['rejected'], 0)
        rows = [loads(s) for s in (self.root/'result/records.jsonl').read_text(encoding='utf-8').splitlines()]
        self.assertEqual(validate_stream(rows), 2*(len(SCENES)+1))
        for frame in rows[::2]:
            a, encoding = load_image(self.root/'result'/frame['payload']['image_ref'], frame['payload'])
            self.assertEqual(encoding, 'rgb8')
            self.assertEqual(a.shape, (240,320,3))

    def test_bad_dimensions(self):
        frame = self.frame()
        frame['payload']['width_px'] = 1280
        result = self.run_manifest([frame])
        self.assertEqual(result['processed'], 0)
        self.assertEqual(result['rejected'], 1)

    def test_duplicate_frame_and_reversed_time(self):
        first = self.frame()
        second = copy.deepcopy(first)
        second['seq'] = 1
        second['payload']['frame_seq'] = 13
        result = self.run_manifest([first, first, second])
        self.assertEqual(result['processed'], 1)
        self.assertEqual(result['rejected'], 2)

    def test_duplicate_source_time(self):
        first = self.frame()
        second = copy.deepcopy(first)
        second.update(seq=1, stamp_ns=124)
        second['payload'].update(frame_seq=13, receipt_mono_ns=124)
        result = self.run_manifest([first, second])
        self.assertEqual(result['rejected'], 1)

    def test_corrupt_file(self):
        (self.images/'bad.png').write_bytes(b'not an image')
        result = replay(self.images, self.root/'result', camera_id='low')
        self.assertEqual((result['processed'],result['rejected']), (1,1))

    def test_path_traversal(self):
        frame = self.frame()
        frame['payload']['image_ref'] = '../outside.png'
        self.assertEqual(self.run_manifest([frame])['rejected'], 1)

    def test_same_device_cannot_be_two_roles(self):
        first = self.frame()
        second = copy.deepcopy(first)
        second['payload']['camera_id'] = 'low'
        self.assertEqual(self.run_manifest([first, second])['rejected'], 1)

    def test_mixed_source_sessions_rejected(self):
        first = self.frame()
        second = copy.deepcopy(first)
        second['session_id'] = 'another-session'
        self.assertEqual(self.run_manifest([first, second])['rejected'], 1)

    def test_empty_input_is_not_success(self):
        empty = self.root/'empty'
        empty.mkdir()
        with self.assertRaises(ValueError):
            replay(empty, self.root/'result', camera_id='high')
        self.assertFalse((self.root/'result').exists())


if __name__ == '__main__':
    unittest.main()
