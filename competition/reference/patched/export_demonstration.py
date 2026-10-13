#!/usr/bin/env python3
"""Offline export of recorded manual data. No ROS node or hardware access."""
import argparse
import bisect
import csv
import hashlib
import json
import math
from pathlib import Path

import cv2
import numpy as np
import rosbag


def export(session, allow_receipt=False, tolerance=0.05):
    session = Path(session).resolve()
    manifest = json.loads((session / 'manifest.json').read_text())
    if not manifest['complete']:
        raise ValueError('incomplete session: inspect raw records before using as data')
    if not 0 < tolerance <= 0.1:
        raise ValueError('pair tolerance must be 0..0.1 seconds')
    out = session / 'export'
    out.mkdir(exist_ok=False)
    (out / 'images').mkdir()
    (out / 'full_frames').mkdir()
    odom_topic = manifest['odom_topic']
    image_topic = manifest['image_topic']
    odom = []
    with rosbag.Bag(str(session / 'raw.bag')) as bag:
        for _, msg, receipt in bag.read_messages(topics=[odom_topic]):
            vx, vy, wz = msg.twist.twist.linear.x, msg.twist.twist.linear.y, msg.twist.twist.angular.z
            if not all(math.isfinite(x) for x in (vx, vy, wz)):
                continue
            stamp = msg.header.stamp.to_sec()
            key = receipt.to_sec() if allow_receipt else stamp
            if key > 0:
                odom.append((key, stamp, receipt.to_sec(), vx, vy, wz))
    odom.sort()
    keys = [x[0] for x in odom]
    stats = dict(images=0, eligible=0, skipped_rate=0, paired=0, rejected=0, moving=0, zero_stamp=0,
                 duplicate_stamp=0, bad_decode=0)
    seen = set()
    last_sample = -float('inf')
    skews = []
    csv_name = 'data.csv' if manifest['split'] == 'development' else 'validation.csv'
    with (out / csv_name).open('x', newline='') as train_file, \
            (out / 'pairs.csv').open('x', newline='') as pair_file:
        train = csv.writer(train_file); train.writerow(['image_path', 'steering'])
        pairs = csv.writer(pair_file)
        pairs.writerow(['frame', 'image_stamp', 'odom_stamp', 'image_receipt', 'odom_receipt',
                        'pair_skew_s', 'vx', 'vy', 'measured_wz', 'moving', 'split', 'time_basis'])
        with rosbag.Bag(str(session / 'raw.bag')) as bag:
            for _, msg, receipt in bag.read_messages(topics=[image_topic]):
                stats['images'] += 1
                stamp = msg.header.stamp.to_sec()
                key = receipt.to_sec() if allow_receipt else stamp
                if key <= 0:
                    stats['zero_stamp'] += 1; stats['rejected'] += 1; continue
                # Duplicate source stamps cannot become independent training frames.
                if stamp > 0 and stamp in seen:
                    stats['duplicate_stamp'] += 1; stats['rejected'] += 1; continue
                if stamp > 0:
                    seen.add(stamp)
                if key < last_sample:
                    raise ValueError('image clock went backwards')
                if key-last_sample < 0.099:
                    stats['skipped_rate'] += 1
                    continue
                stats['eligible'] += 1
                last_sample = key
                pos = bisect.bisect_left(keys, key)
                candidates = odom[max(0, pos-1):min(len(odom), pos+1)]
                if not candidates:
                    stats['rejected'] += 1; continue
                best = min(candidates, key=lambda x: abs(x[0]-key))
                skew = abs(best[0]-key)
                if skew > tolerance:
                    stats['rejected'] += 1; continue
                image = cv2.imdecode(np.frombuffer(msg.data, np.uint8), cv2.IMREAD_COLOR)
                if image is None:
                    stats['bad_decode'] += 1; stats['rejected'] += 1; continue
                name = '%06d.jpg' % stats['paired']
                full_path = out / 'full_frames' / name
                train_path = out / 'images' / name
                # Original JPEG retained byte-for-byte; resized BGR JPEG matches factory collector.
                full_path.write_bytes(bytes(msg.data))
                if not cv2.imwrite(str(train_path), cv2.resize(image, (160, 120))):
                    raise OSError('JPEG write failed')
                moving = abs(best[3]) > 0.02 or abs(best[5]) > 0.02
                pairs.writerow([name, stamp, best[1], receipt.to_sec(), best[2], skew,
                                best[3], best[4], best[5], int(moving), manifest['split'],
                                'receipt_approximate' if allow_receipt else 'source_header'])
                if moving:
                    train.writerow([str(train_path), round(best[5], 4)])
                    stats['moving'] += 1
                stats['paired'] += 1
                skews.append(skew)
    stats.update(split=manifest['split'], tolerance_s=tolerance,
                 time_basis='receipt_approximate' if allow_receipt else 'source_header',
                 raw_bag_sha256=hash_file(session / 'raw.bag'),
                 exporter_sha256=hash_file(Path(__file__)),
                 label='measured angular.z, not command',
                 evaluated_autonomy=False,
                 pair_fraction=stats['paired']/stats['eligible'] if stats['eligible'] else 0,
                 max_skew_s=max(skews) if skews else None,
                 p95_skew_s=float(np.percentile(skews, 95)) if skews else None)
    (out / 'quality.json').write_text(json.dumps(stats, indent=2), encoding='utf-8')
    if not stats['paired']:
        raise ValueError('no usable pairs; see quality.json; do not silently loosen tolerance')
    return stats


def hash_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1024*1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session')
    parser.add_argument('--allow-receipt-time', action='store_true',
                        help='Explicit approximate fallback; inspect clock issue before enabling')
    parser.add_argument('--tolerance', type=float, default=0.05)
    args = parser.parse_args()
    print(json.dumps(export(args.session, args.allow_receipt_time, args.tolerance), indent=2))
