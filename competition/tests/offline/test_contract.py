"""Synthetic contract regression only. No imports from legacy reference code."""
import copy
import json
from pathlib import Path
import unittest

from competition.interfaces.validate import loads, request_is_current, validate, validate_stream


class ContractTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).resolve().parents[2] / 'interfaces' / 'examples.jsonl'
        self.rows = [loads(s) for s in path.read_text(encoding='utf-8').splitlines()]

    def sample(self, kind):
        return copy.deepcopy(next(r for r in self.rows if r['kind'] == kind))

    def test_complete_synthetic_exchange(self):
        self.assertEqual(validate_stream(self.rows), 10)

    def test_offset_sign_and_units(self):
        r = self.sample('road')
        r['payload']['offset_px'] *= -1
        with self.assertRaises(ValueError): validate(r)

    def test_invalid_road_cannot_reuse_path(self):
        r = self.sample('road'); r['payload']['valid'] = False
        with self.assertRaises(ValueError): validate(r)
        r['payload'].update(target_x_px=None, offset_px=None, path_px=[])
        validate(r)

    def test_box_coordinates(self):
        for box in ([10,20,5,30], [0,0,1281,720], [0,0,0,10]):
            r = self.sample('detections'); r['payload']['objects'][0]['bbox_xyxy_px'] = box
            with self.assertRaises(ValueError): validate(r)

    def test_empty_detection_is_unknown(self):
        r = self.sample('detections'); r['payload'].update(objects=[],barrier_state='clear')
        with self.assertRaises(ValueError): validate(r)
        r['payload']['barrier_state'] = 'unknown'; validate(r)

    def test_stop_must_be_zero(self):
        r = self.sample('motion_request'); r['payload']['mode'] = 'stop'
        with self.assertRaises(ValueError): validate(r)

    def test_ttl_boundary_and_clock_domain(self):
        r = self.sample('motion_request')
        self.assertTrue(request_is_current(r,1119999999,r['clock_id']))
        self.assertFalse(request_is_current(r,1120000000,r['clock_id']))
        self.assertFalse(request_is_current(r,1050000000,'different-clock'))
        self.assertFalse(request_is_current(r,1039999999,r['clock_id']))
        # Republishing does not extend validity beyond the original input.
        r['stamp_ns'] = 1200000000
        self.assertFalse(request_is_current(r,1200000001,r['clock_id']))

    def test_nonfinite_bool_version_and_unknown_fields(self):
        for value in (float('nan'),float('inf'),True):
            r = self.sample('motion_request'); r['payload']['vx_mps'] = value
            with self.assertRaises(ValueError): validate(r)
        for key,value in [('schema_version','future'),('extra',1)]:
            r = self.sample('road'); r[key] = value
            with self.assertRaises(ValueError): validate(r)
        with self.assertRaises(ValueError): loads('{"kind":1,"kind":2}')

    def test_paths(self):
        for path in ('../old.png','C:/private.png','/dev/video0','..\\old.png'):
            r=self.sample('camera_frame'); r['payload']['image_ref']=path
            with self.assertRaises(ValueError): validate(r)

    def test_two_roles_cannot_share_physical_camera(self):
        self.rows[1]['payload']['physical_id'] = self.rows[0]['payload']['physical_id']
        with self.assertRaises(ValueError): validate_stream(self.rows)

    def test_pair_skew_and_clock(self):
        r=self.sample('frame_pair'); r['payload']['delta_ns'] *= -1
        with self.assertRaises(ValueError): validate(r)
        self.rows[1]['payload']['source_clock_id']='other-source-clock'
        with self.assertRaises(ValueError): validate_stream(self.rows)

    def test_duplicate_and_missing_frame(self):
        with self.assertRaises(ValueError): validate_stream(self.rows + [self.rows[0]])
        with self.assertRaises(ValueError): validate_stream(self.rows[2:])
        self.rows[3]['payload']['width_px']=640
        with self.assertRaises(ValueError): validate_stream(self.rows)

    def test_completion_and_legal_wait(self):
        r=self.sample('state_event'); r['payload']['state']='complete'
        with self.assertRaises(ValueError): validate(r)
        r=self.sample('state_event'); r['payload']['stop_required']=False
        with self.assertRaises(ValueError): validate(r)


if __name__ == '__main__':
    unittest.main()
