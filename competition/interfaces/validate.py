"""Offline JSON contract checks. Standard library only; no ROS or device access.

Implements only the schema keywords used in the adjacent schema.json. This is
not a general JSON Schema implementation, a ROS adapter or a motion permit.
"""
import argparse
import json
import math
from pathlib import Path, PurePosixPath


VERSION = 'deepbot.offline/0.1.0'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _finite(value):
    if isinstance(value, float):
        require(math.isfinite(value), 'non-finite number')
    elif isinstance(value, dict):
        for item in value.values():
            _finite(item)
    elif isinstance(value, list):
        for item in value:
            _finite(item)


def _shape(value, spec):
    for keyword in ('oneOf', 'anyOf'):
        if keyword in spec:
            count = 0
            for option in spec[keyword]:
                try:
                    _shape(value, option)
                    count += 1
                except ValueError:
                    pass
            require(count == 1 if keyword == 'oneOf' else count >= 1,
                    'schema alternatives rejected record')
            return
    if 'enum' in spec:
        require(any(type(value) is type(v) and value == v for v in spec['enum']), 'invalid enum')
    kind = spec.get('type')
    checks = {'object': lambda: isinstance(value, dict),
              'array': lambda: isinstance(value, list),
              'integer': lambda: type(value) is int,
              'number': lambda: type(value) in (int, float),
              'boolean': lambda: type(value) is bool,
              'string': lambda: isinstance(value, str),
              'null': lambda: value is None}
    if kind:
        require(checks[kind](), 'wrong type: expected ' + kind)
    if kind == 'object':
        require(set(spec['required']) <= value.keys(), 'missing required field')
        require(value.keys() <= spec['properties'].keys(), 'unknown field')
        for key, item in value.items():
            _shape(item, spec['properties'][key])
    if kind == 'array':
        require(len(value) >= spec.get('minItems', 0), 'array too short')
        require(len(value) <= spec.get('maxItems', len(value)), 'array too long')
        for item in value:
            _shape(item, spec['items'])
    if kind == 'string':
        require(len(value) >= spec.get('minLength', 0), 'empty string')
    if kind in ('integer', 'number'):
        require(value >= spec.get('minimum', value), 'below minimum')
        require(value <= spec.get('maximum', value), 'above maximum')


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key: ' + key)
        result[key] = value
    return result


def loads(text):
    value = json.loads(text, object_pairs_hook=_pairs)
    _finite(value)
    return value


def validate(record):
    _finite(record)
    schema = loads(Path(__file__).with_name('schema.json').read_text(encoding='utf-8'))
    _shape(record, schema)
    p, kind = record['payload'], record['kind']
    if kind == 'camera_frame':
        path = PurePosixPath(p['image_ref'])
        require(not path.is_absolute() and '..' not in path.parts and
                ':' not in p['image_ref'] and '\\' not in p['image_ref'], 'unsafe image_ref')
        require(record['stamp_ns'] == p['receipt_mono_ns'], 'receipt clock mismatch')
    if kind in ('camera_frame', 'motion_feedback'):
        require((p['source_stamp_ns'] is None) == (p['source_clock_id'] == 'unknown'),
                'missing source time must use unknown clock')
    if kind in ('road', 'detections'):
        require(p['frame_stamp_ns'] <= record['stamp_ns'], 'result precedes input')
    if kind == 'road':
        require(0 <= p['reference_x_px'] < p['width_px'] and
                0 <= p['reference_y_px'] < p['height_px'], 'reference outside image')
        if p['valid']:
            require(p['target_x_px'] is not None and p['offset_px'] is not None and p['path_px'],
                    'valid road needs target, offset and path')
            require(0 <= p['target_x_px'] < p['width_px'], 'target outside image')
            require(abs(p['offset_px'] - (p['target_x_px'] - p['reference_x_px'])) < 1e-6,
                    'offset sign or unit mismatch')
        else:
            require(p['target_x_px'] is None and p['offset_px'] is None and p['path_px'] == [],
                    'invalid road must not carry stale path')
        for x, y in p['path_px']:
            require(0 <= x < p['width_px'] and 0 <= y < p['height_px'], 'path outside image')
    if kind == 'detections':
        for item in p['objects']:
            x1, y1, x2, y2 = item['bbox_xyxy_px']
            require(0 <= x1 < x2 <= p['width_px'] and 0 <= y1 < y2 <= p['height_px'], 'invalid box')
        if p['barrier_state'] != 'unknown':
            require(any(o['class_name'] == 'barrier' for o in p['objects']), 'barrier state lacks evidence')
    if kind == 'motion_request':
        require(p['basis_stamp_ns'] <= record['stamp_ns'], 'request precedes basis')
        if p['mode'] == 'stop':
            require(all(p[k] == 0 for k in ('vx_mps', 'vy_mps', 'wz_radps')), 'stop must be zero')
    if kind == 'frame_pair':
        require(p['delta_ns'] == p['low_stamp_ns'] - p['high_stamp_ns'], 'wrong pair skew')
        require(p['accepted'] == (abs(p['delta_ns']) <= p['tolerance_ns']), 'wrong pair decision')
    if kind == 'state_event':
        if p['state'] in ('standby','stopped_dwell','wait_barrier','complete','fault'):
            require(p['stop_required'], 'stopped state must require stop')
        if p['state'] == 'complete':
            require(p['lap_completed'] == 2 and p['evidence_refs'], 'completion needs two laps and evidence')
    return record


def request_is_current(record, now_ns, clock_id):
    """Only TTL/clock check; does NOT authorize motion or check other safety inputs."""
    validate(record)
    require(record['kind'] == 'motion_request', 'expected motion_request')
    require(type(now_ns) is int and now_ns >= 0, 'invalid now_ns')
    p = record['payload']
    return (clock_id == record['clock_id'] and record['stamp_ns'] <= now_ns and
            now_ns < p['basis_stamp_ns'] + p['ttl_ms'] * 1000000)


def validate_stream(records):
    """Complete synthetic exchange check; missing frame dependencies are errors."""
    frames, roles, ids, sequences = {}, {}, set(), {}
    count = 0
    for r in records:
        validate(r)
        p, kind, session = r['payload'], r['kind'], r['session_id']
        key = (session, kind, p.get('camera_id', p.get('source', 'default')))
        require(r['seq'] > sequences.get(key, -1), 'non-increasing stream sequence')
        sequences[key] = r['seq']
        if kind == 'camera_frame':
            for (sess, role), physical in roles.items():
                if sess == session and role != p['camera_id']:
                    require(physical != p['physical_id'], 'one physical camera used twice')
            role_key = (session, p['camera_id'])
            require(roles.get(role_key, p['physical_id']) == p['physical_id'], 'camera identity changed')
            roles[role_key] = p['physical_id']
            frame_key = (session, p['camera_id'], p['frame_seq'])
            require(frame_key not in frames, 'duplicate frame')
            previous = [v for k,v in frames.items() if k[:2] == frame_key[:2]]
            if previous:
                last = previous[-1]
                require(last['clock_id'] == r['clock_id'] and last['stamp_ns'] < r['stamp_ns'], 'frame clock reset')
                lp = last['payload']
                require(lp['frame_seq'] < p['frame_seq'], 'frame sequence reset')
                if lp['source_stamp_ns'] is not None and p['source_stamp_ns'] is not None:
                    require(lp['source_clock_id'] == p['source_clock_id'] and lp['source_stamp_ns'] < p['source_stamp_ns'],
                            'source clock reset or duplicate')
            frames[frame_key] = r
        if kind in ('road', 'detections'):
            f = frames.get((session,p['camera_id'],p['frame_seq']))
            require(f is not None, 'missing input frame')
            require(f['clock_id'] == r['clock_id'] and f['stamp_ns'] == p['frame_stamp_ns'], 'wrong frame time')
            require(all(f['payload'][v] == p[v] for v in ('width_px','height_px')), 'wrong image dimensions')
        if kind == 'frame_pair':
            for role in ('high','low'):
                f = frames.get((session,role,p[role+'_frame_seq']))
                require(f is not None, 'missing pair frame')
                field = 'source_stamp_ns' if p['basis'] == 'source_header' else 'receipt_mono_ns'
                domain = f['payload']['source_clock_id'] if p['basis'] == 'source_header' else f['clock_id']
                require(domain == p['pairing_clock_id'] and f['payload'][field] == p[role+'_stamp_ns'], 'pair clock mismatch')
        if kind in ('state_event','motion_request'):
            identity = (session,kind,p.get('event_id',p.get('request_id')))
            require(identity not in ids, 'duplicate event/request id')
            ids.add(identity)
        count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('jsonl', type=Path)
    args = parser.parse_args()
    rows = [loads(line) for line in args.jsonl.read_text(encoding='utf-8').splitlines() if line.strip()]
    print('OFFLINE_CONTRACT_OK records=%d version=%s hardware_access=none' % (validate_stream(rows), VERSION))


if __name__ == '__main__':
    main()
