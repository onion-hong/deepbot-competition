#!/usr/bin/env python3
"""Passive ROS recorder. Does not launch hardware or publish motion commands.

Preserves raw input for replay; export_demonstration.py retains the factory
data_collect.py image_path/steering format and measured-yaw label semantics.
"""
import argparse
import collections
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import threading
import time
import uuid

import cv2
import numpy as np
import rosbag
import rospy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import Float32


def atomic_json(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    os.replace(str(temporary), str(path))


class SessionWriter:
    def __init__(self, root, split, metadata, reserve_bytes=1024**3):
        if split not in ('development', 'validation'):
            raise ValueError('split must be chosen before recording')
        root = Path(root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(str(root)).free < reserve_bytes:
            raise OSError('insufficient free disk space')
        self.path = root / (time.strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8])
        self.path.mkdir(exist_ok=False)
        self.lock = threading.RLock()
        self.closed = False
        self.counts = collections.Counter()
        self.latest = {}
        self.source_stamps = {}
        self.first_mono = time.monotonic()
        self.last_receipt_ns = 0
        self.reserve_bytes = reserve_bytes
        self.bag = rosbag.Bag(str(self.path / 'raw.bag'), 'w', compression='lz4')
        self.index = (self.path / 'receipts.jsonl').open('x', encoding='utf-8')
        self.manifest = dict(metadata, schema=1, split=split, role='manual_demonstration',
                             autonomous_success=False, complete=False,
                             label_semantics='measured angular.z rad/s; not joystick command',
                             pairing='source header stamps; receipt fallback requires explicit export option',
                             recorder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        atomic_json(self.path / 'manifest.json', self.manifest)

    def append(self, topic, msg, receipt_ns=None, monotonic=None):
        with self.lock:
            if self.closed:
                return
            receipt_ns = time.time_ns() if receipt_ns is None else receipt_ns
            monotonic = time.monotonic() if monotonic is None else monotonic
            if receipt_ns < self.last_receipt_ns:
                raise RuntimeError('host wall clock moved backwards')
            self.last_receipt_ns = receipt_ns
            stamp = getattr(getattr(msg, 'header', None), 'stamp', None)
            header_ns = stamp.to_nsec() if stamp is not None else None
            seq = self.counts[topic]
            record = dict(topic=topic, seq=seq, receipt_ns=receipt_ns,
                          monotonic=monotonic, header_ns=header_ns,
                          header_seq=getattr(getattr(msg, 'header', None), 'seq', None))
            valid = True
            if isinstance(msg, (Odometry, CompressedImage)):
                previous_stamp = self.source_stamps.get(topic, 0)
                valid = bool(header_ns and header_ns > previous_stamp
                             and abs(header_ns-receipt_ns) <= 500000000)
                if header_ns and header_ns < previous_stamp:
                    raise RuntimeError('source stamp moved backwards: ' + topic)
                self.source_stamps[topic] = header_ns or 0
                record['valid_source_stamp'] = valid
            if isinstance(msg, Odometry):
                values = [msg.twist.twist.linear.x, msg.twist.twist.linear.y,
                          msg.twist.twist.angular.z]
                finite = all(math.isfinite(v) for v in values)
                valid = valid and finite
                record['motion'] = values if finite else None
                record['valid_motion'] = finite
            if isinstance(msg, CompressedImage):
                decoded = cv2.imdecode(np.frombuffer(msg.data, np.uint8), cv2.IMREAD_COLOR) if msg.data else None
                decodable = decoded is not None
                valid = valid and decodable
                record['valid_image_bytes'] = decodable
                record['image_shape'] = list(decoded.shape) if decodable else None
            self.bag.write(topic, msg, rospy.Time(receipt_ns // 10**9, receipt_ns % 10**9))
            self.index.write(json.dumps(record, allow_nan=False) + '\n')
            self.counts[topic] += 1
            self.latest[topic] = (monotonic, valid)

    def status(self, image_topic, odom_topic, now=None):
        with self.lock:
            now = time.monotonic() if now is None else now
            ages = {topic: now - self.latest.get(topic, (-float('inf'), False))[0]
                    for topic in (image_topic, odom_topic)}
            ready = all(0 <= ages[t] <= 0.5 and self.latest.get(t, (0, False))[1]
                        for t in ages)
            self.index.flush()
            self.bag.flush()
            free = shutil.disk_usage(str(self.path)).free
            return dict(streams_fresh=ready,
                        ages={t: a if math.isfinite(a) else None for t, a in ages.items()},
                        counts=dict(self.counts), free_bytes=free)

    def close(self, reason, complete=True):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            try:
                self.bag.close()
                self.index.flush()
                os.fsync(self.index.fileno())
                self.index.close()
                self.manifest.update(complete=complete, close_reason=reason,
                                     counts=dict(self.counts), duration_s=time.monotonic()-self.first_mono)
                atomic_json(self.path / 'manifest.json', self.manifest)
            except Exception:
                self.manifest.update(complete=False, close_reason='close_error')
                atomic_json(self.path / 'manifest.json', self.manifest)
                raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--split', required=True, choices=['development', 'validation'])
    parser.add_argument('--route-id', required=True)
    parser.add_argument('--camera-pose', required=True)
    parser.add_argument('--operator', default='onsite_manual')
    parser.add_argument('--config', required=True, help='Frozen JSON of route/camera/code versions')
    parser.add_argument('--image-topic', default='/camera_720_trial/image_raw/compressed')
    parser.add_argument('--odom-topic', default='/raw_odom')
    parser.add_argument('--max-seconds', type=float, default=600)
    args = parser.parse_args(rospy.myargv()[1:])
    if not 1 <= args.max_seconds <= 1800:
        parser.error('max-seconds must be 1..1800')
    rospy.init_node('demonstration_recorder', anonymous=True)
    config_bytes = Path(args.config).read_bytes()
    json.loads(config_bytes.decode('utf-8'))
    metadata = dict(vars(args), config_sha256=hashlib.sha256(config_bytes).hexdigest())
    writer = SessionWriter(args.root, args.split, metadata)
    (writer.path / 'frozen_config.json').write_bytes(config_bytes)
    reason = 'operator_shutdown'
    errors = []
    subscribers = []

    def receive(msg, topic):
        try:
            writer.append(topic, msg)
        except Exception as exc:
            errors.append(str(exc))
            rospy.signal_shutdown('recording_error: ' + str(exc))

    topics = [(args.image_topic, CompressedImage), (args.odom_topic, Odometry),
              ('/cmd_vel', Twist), ('/battery', Float32), ('/sonar', Float32)]
    try:
        for topic, msgtype in topics:
            subscribers.append(rospy.Subscriber(topic, msgtype, receive, callback_args=topic,
                                               queue_size=300, buff_size=16*1024*1024))
        print('SESSION=' + str(writer.path), flush=True)
        while not rospy.is_shutdown():
            state = writer.status(args.image_topic, args.odom_topic)
            print(json.dumps(state), flush=True)
            if state['free_bytes'] < writer.reserve_bytes:
                reason = 'low_disk'; errors.append(reason); break
            if (writer.path / 'STOP_RECORDING').exists():
                reason = 'operator_stop_file'; break
            elapsed = time.monotonic() - writer.first_mono
            if elapsed >= args.max_seconds:
                reason = 'time_limit'; break
            if elapsed > 5 and not state['streams_fresh']:
                reason = 'required_stream_missing_or_stale'; errors.append(reason); break
            time.sleep(0.2)
    except BaseException as exc:
        if not isinstance(exc, KeyboardInterrupt):
            errors.append(repr(exc))
        raise
    finally:
        for sub in subscribers:
            sub.unregister()
        writer.manifest['errors'] = errors
        writer.close(reason, complete=not errors)
        print('CLOSED=' + str(writer.path), flush=True)
        print('Recorder exit does not stop manual driving.', flush=True)
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
