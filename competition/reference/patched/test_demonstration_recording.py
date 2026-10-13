#!/usr/bin/env python3
"""Real rosbag/message/codec checks without ROS master, cameras or serial ports."""
import ast
import csv
import json
from pathlib import Path
import tempfile

import cv2
import numpy as np
import rospy
import rosbag
from nav_msgs.msg import Odometry
from sensor_msgs.msg import CompressedImage

from record_demonstration import SessionWriter
from export_demonstration import export


def odom(stamp, wz):
    msg = Odometry()
    msg.header.stamp = rospy.Time.from_sec(stamp)
    msg.twist.twist.linear.x = 0.04
    msg.twist.twist.angular.z = wz
    return msg


def image(stamp, payload):
    msg = CompressedImage()
    msg.header.stamp = rospy.Time.from_sec(stamp)
    msg.format = 'jpeg'
    msg.data = payload
    return msg


def main():
    img_topic, odom_topic = '/test/image', '/test/odom'
    meta = dict(image_topic=img_topic, odom_topic=odom_topic, route_id='SYNTHETIC_ONLY')
    _, encoded = cv2.imencode('.jpg', np.full((720, 1280, 3), 100, np.uint8))
    payload = encoded.tobytes()
    with tempfile.TemporaryDirectory(prefix='passive_recording_test_') as root:
        marker = Path(root) / 'existing_data.txt'
        marker.write_text('preserve me')
        writer = SessionWriter(root, 'development', meta, reserve_bytes=0)
        assert not writer.status(img_topic, odom_topic, now=0)['streams_fresh']
        for i in range(6):
            stamp = 100 + i*0.1
            writer.append(odom_topic, odom(stamp, 0.1*i), int(stamp*1e9), float(i)*0.1)
            writer.append(img_topic, image(stamp+0.01, payload), int((stamp+0.01)*1e9), float(i)*0.1+0.01)
        assert writer.status(img_topic, odom_topic, now=0.55)['streams_fresh']
        assert not writer.status(img_topic, odom_topic, now=1.2)['streams_fresh']
        writer.close('synthetic_complete')
        writer.close('idempotent')
        assert marker.read_text() == 'preserve me'
        with rosbag.Bag(str(writer.path / 'raw.bag')) as bag:
            assert bag.get_message_count() == 12
        stats = export(writer.path)
        assert stats['paired'] == 6 and stats['moving'] == 6, stats
        rows = list(csv.DictReader((writer.path / 'export' / 'data.csv').open()))
        assert [float(r['steering']) for r in rows] == [0, .1, .2, .3, .4, .5]
        assert cv2.imread(rows[0]['image_path']).shape == (120, 160, 3)
        try:
            export(writer.path)
            raise AssertionError('export overwrite accepted')
        except FileExistsError:
            pass
        validation = SessionWriter(root, 'validation', meta, reserve_bytes=0)
        validation.append(odom_topic, odom(200, 0.2), 200000000000, 0)
        validation.append(img_topic, image(200.01, payload), 200010000000, 0.01)
        validation.close('synthetic_validation')
        export(validation.path)
        assert (validation.path / 'export' / 'validation.csv').exists()
        assert not (validation.path / 'export' / 'data.csv').exists()
        invalid = SessionWriter(root, 'development', meta, reserve_bytes=0)
        invalid.append(odom_topic, odom(300, float('nan')), 300000000000, 0)
        invalid.append(img_topic, image(300.01, payload), 300010000000, 0.01)
        assert not invalid.status(img_topic, odom_topic, now=0.1)['streams_fresh']
        invalid.close('invalid_stream', complete=False)
        try:
            export(invalid.path)
            raise AssertionError('incomplete accepted')
        except ValueError:
            pass
        mismatch = SessionWriter(root, 'development', meta, reserve_bytes=0)
        mismatch.append(odom_topic, odom(400, .2), 400000000000, 0)
        mismatch.append(img_topic, image(400.3, payload), 400300000000, .3)
        mismatch.close('synthetic_clock_mismatch')
        try:
            export(mismatch.path)
            raise AssertionError('skew accepted')
        except ValueError:
            pass
        assert json.loads((mismatch.path / 'export' / 'quality.json').read_text())['paired'] == 0
        duplicate = SessionWriter(root, 'development', meta, reserve_bytes=0)
        duplicate.append(odom_topic, odom(500, .2), 500000000000, 0)
        duplicate.append(img_topic, image(500.01, payload), 500010000000, .01)
        duplicate.append(img_topic, image(500.01, payload), 500110000000, .11)
        assert not duplicate.status(img_topic, odom_topic, now=.2)['streams_fresh']
        duplicate.close('duplicate_fixture')
        stats = export(duplicate.path)
        assert stats['duplicate_stamp'] == 1
        full = (duplicate.path / 'export' / 'full_frames' / '000000.jpg').read_bytes()
        assert full == payload
    source = ast.parse(Path(__file__).with_name('record_demonstration.py').read_text())
    forbidden = {'Publisher', 'ServiceProxy', 'Popen', 'system'}
    assert not any(isinstance(n, ast.Attribute) and n.attr in forbidden for n in ast.walk(source))
    print('PASS: raw bag roundtrip, paired labels/shape, full-frame preservation, stale/missing/invalid/duplicate checks, skew rejection, split/overwrite protection; no master or hardware used')


if __name__ == '__main__':
    main()
