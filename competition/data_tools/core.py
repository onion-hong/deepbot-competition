"""Versioned storage core; no ROS imports or hardware access."""
import collections
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import threading
import time
import uuid

from PIL import Image

from . import STORAGE_VERSION


def dumps(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)


def load_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def hash_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def write_new(path, data):
    with Path(path).open('xb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def atomic_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    write_new(temp, (dumps(value) + '\n').encode('utf-8'))
    # Windows indexers/readers can briefly hold the destination without delete sharing.
    # Retry the same completed temp file; never remove either file as a workaround.
    for attempt in range(5):
        try:
            os.replace(str(temp), str(path))
            break
        except PermissionError:
            if os.name != 'nt' or attempt == 4:
                raise
            time.sleep(0.01 * (2 ** attempt))


def safe_ref(root, ref):
    if not isinstance(ref, str) or not ref or '\\' in ref or ':' in ref:
        raise ValueError('unsafe relative reference')
    path = Path(ref)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('unsafe relative reference')
    result = (Path(root) / path).resolve()
    result.relative_to(Path(root).resolve())
    return result


def validate_config(config):
    c = json.loads(dumps(config))  # deep copy; reject nonfinite values
    if c.get('storage_version') != STORAGE_VERSION:
        raise ValueError('unsupported storage_version')
    if c.get('mode') not in ('visual_only', 'demonstration'):
        raise ValueError('mode must be visual_only or demonstration')
    if c.get('split') not in ('development', 'validation'):
        raise ValueError('split must be development or validation')
    if c.get('role') not in ('synthetic', 'manual_visual', 'manual_demonstration', 'autonomous_evaluation'):
        raise ValueError('explicit role required')
    if c['role'] == 'manual_visual' and c['mode'] != 'visual_only':
        raise ValueError('manual_visual cannot be demonstration')
    if c['role'] == 'manual_demonstration' and c['mode'] != 'demonstration':
        raise ValueError('manual_demonstration needs feedback-required mode')
    if c.get('acquisition_method') not in ('synthetic', 'stationary', 'hand_push', 'joystick', 'autonomous'):
        raise ValueError('explicit acquisition_method required')
    allowed = {'synthetic': {'synthetic'}, 'manual_visual': {'stationary', 'hand_push', 'joystick'},
               'manual_demonstration': {'joystick'}, 'autonomous_evaluation': {'autonomous'}}
    if c['acquisition_method'] not in allowed[c['role']]:
        raise ValueError('role/acquisition_method mismatch')
    if set(c.get('cameras', {})) != {'high', 'low'}:
        raise ValueError('exactly high and low installation roles required; neither implies front/rear')
    streams = list(c['cameras'].values())
    ids = [s.get('physical_id') for s in streams]
    if any(not isinstance(i, str) or not i.strip() for i in ids) or len(set(ids)) != 2:
        raise ValueError('two distinct stable physical_id values required')
    for spec in streams:
        if spec.get('message_type') not in ('sensor_msgs/CompressedImage', 'sensor_msgs/Image'):
            raise ValueError('unsupported camera message_type')
        if type(spec.get('identity_verified')) is not bool:
            raise ValueError('identity_verified must be explicit boolean')
    devices = [s.get('device_key') for s in streams]
    if all(devices) and len(set(devices)) != 2:
        raise ValueError('duplicate physical device_key')
    if c.get('feedback') is not None:
        if c['feedback'].get('message_type') != 'nav_msgs/Odometry':
            raise ValueError('feedback must be Odometry; preserve other messages separately in future versions')
        streams.append(c['feedback'])
    if c.get('command') is not None:
        if c['command'].get('message_type') != 'geometry_msgs/Twist':
            raise ValueError('command must be observed Twist')
        streams.append(c['command'])
    if c['mode'] == 'demonstration' and c.get('feedback') is None:
        raise ValueError('demonstration requires configured feedback')
    topics = []
    for spec in streams:
        topic = spec.get('topic')
        if not isinstance(topic, str) or not topic.startswith('/') or topic == '/' or any(ch.isspace() for ch in topic):
            raise ValueError('explicit absolute topic required')
        topic = '/' + '/'.join(p for p in topic.split('/') if p)
        spec['topic'] = topic
        topics.append(topic)
        if not isinstance(spec.get('source_clock_id'), str) or not spec['source_clock_id']:
            raise ValueError('source_clock_id required; use unknown when not verified')
        if spec.get('compare_source_to_ros_time') is True and spec['source_clock_id'] == 'unknown':
            raise ValueError('cannot compare an unknown source clock with ROS time')
    if len(set(topics)) != len(topics):
        raise ValueError('duplicate resolved topic')
    for key in ('max_age_ns', 'startup_grace_ns', 'reserve_bytes'):
        if type(c.get(key)) is not int or c[key] < (0 if key == 'reserve_bytes' else 1):
            raise ValueError('invalid ' + key)
    policy = c.get('pairing', {})
    if policy.get('basis') not in ('source_header', 'receipt_approximate'):
        raise ValueError('pairing basis must be explicit')
    if type(policy.get('tolerance_ns')) is not int or policy['tolerance_ns'] <= 0:
        raise ValueError('positive explicit pairing tolerance required')
    return c


def decode_image(data, descriptor):
    if descriptor.get('format') == 'compressed':
        with Image.open(io.BytesIO(data)) as source:
            source.load()
            return source.convert('RGB')
    if descriptor.get('format') != 'raw':
        raise ValueError('unknown image format')
    width, height, step = (descriptor[k] for k in ('width', 'height', 'step'))
    encoding = descriptor['encoding']
    modes = {'rgb8': ('RGB', 'RGB', 3), 'bgr8': ('RGB', 'BGR', 3), 'mono8': ('L', 'L', 1)}
    if encoding not in modes or any(type(v) is not int or v <= 0 for v in (width, height, step)):
        raise ValueError('unsupported raw encoding or dimensions')
    mode, rawmode, channels = modes[encoding]
    if step < width * channels or len(data) != step * height:
        raise ValueError('raw image stride/length mismatch')
    return Image.frombytes(mode, (width, height), data, 'raw', rawmode, step, 1).convert('RGB')


class SessionWriter:
    """Exclusive session writer. complete describes durable closure, not quality."""
    def __init__(self, root, session_id, config, clock_id=None):
        self.config = validate_config(config)
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', session_id):
            raise ValueError('session_id must be a safe filename')
        self.lock = threading.RLock()
        self.path = Path(root).resolve() / session_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if shutil.disk_usage(self.path.parent).free < self.config['reserve_bytes']:
            raise OSError('insufficient_disk_before_start')
        self.path.mkdir(exist_ok=False)
        self.closed = False
        self.failed = False
        self.counts = collections.Counter()
        self.latest = {}
        self.last_source = {}
        self.last_mono = {}
        self.last_wall = {}
        self.processed_requests = set()
        self.start_ns = time.monotonic_ns()
        self.clock_id = clock_id or ('recorder-' + uuid.uuid4().hex)
        config_bytes = (dumps(self.config) + '\n').encode('utf-8')
        self.manifest = dict(storage_version=STORAGE_VERSION, schema_version='deepbot.offline/0.1.0',
            session_id=session_id, split=self.config['split'], role=self.config['role'],
            mode=self.config['mode'], acquisition_method=self.config['acquisition_method'],
            validation_consumed=False, autonomous_success=None, code_commit=None,
            code_state='uncommitted_or_commit_unverified',
            code_sha256={p.name: hash_file(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
            config_sha256=sha(config_bytes), cameras=self.config['cameras'], clock_id=self.clock_id,
            start_mono_ns=self.start_ns, complete=False, state='creating', close_reason=None,
            errors=[], counts={}, raw_files={})
        self.index = self.events = None
        try:
            atomic_json(self.path / 'manifest.json', self.manifest)
            write_new(self.path / 'frozen_config.json', config_bytes)
            (self.path / 'raw').mkdir()
            (self.path / 'requests').mkdir()
            self.index = (self.path / 'receipts.jsonl').open('x', encoding='utf-8')
            self.events = (self.path / 'events.jsonl').open('x', encoding='utf-8')
            self.manifest['state'] = 'recording'
            atomic_json(self.path / 'manifest.json', self.manifest)
        except BaseException as exc:
            self._fail('initialization_error: ' + repr(exc))
            for f in (self.index, self.events):
                if f is not None:
                    f.close()
            raise

    def _fail(self, reason):
        self.failed = True
        self.manifest.update(complete=False, state='incomplete', close_reason=reason)
        self.manifest['errors'].append(reason)
        try:
            atomic_json(self.path / 'manifest.json', self.manifest)
        except OSError:
            pass  # initial incomplete manifest remains; caller must report stderr

    def _line(self, file, value):
        file.write(dumps(value) + '\n')
        file.flush()
        os.fsync(file.fileno())

    def _spec(self, stream):
        if stream in ('high', 'low'):
            return self.config['cameras'][stream]
        if stream in ('feedback', 'command') and self.config.get(stream):
            return self.config[stream]
        raise ValueError('unconfigured stream: ' + stream)

    def append(self, stream, data, *, descriptor=None, motion=None, source_stamp_ns=None,
               receipt_mono_ns=None, receipt_unix_ns=None, source_now_ns=None,
               serialized_message=None, message_metadata=None):
        """Save original bytes before validating payload/time. Invalid records remain indexed."""
        with self.lock:
            if self.closed or self.failed:
                raise RuntimeError('session is closed or failed')
            spec = self._spec(stream)
            now = time.monotonic_ns() if receipt_mono_ns is None else receipt_mono_ns
            wall = time.time_ns() if receipt_unix_ns is None else receipt_unix_ns
            if any(type(v) is not int or v < 0 for v in (now, wall)):
                raise ValueError('receipt times must be nonnegative integer ns')
            if source_stamp_ns is not None and (type(source_stamp_ns) is not int or source_stamp_ns < 0):
                raise ValueError('source stamp must be null or nonnegative integer ns')
            seq = self.counts[stream]
            ref = 'raw/%s_%09d.bin' % (stream, seq)
            try:
                write_new(self.path / ref, bytes(data))
                record = dict(stream_id=stream, seq=seq, topic=spec['topic'],
                    message_type=spec['message_type'], physical_id=spec.get('physical_id'),
                    source_stamp_ns=source_stamp_ns, source_clock_id=spec['source_clock_id'],
                    receipt_mono_ns=now, receipt_unix_ns=wall, clock_id=self.clock_id,
                    raw_ref=ref, raw_sha256=sha(data), raw_size=len(data),
                    descriptor=descriptor, motion=None, diagnostics=[], warnings=[],
                    message_metadata=message_metadata)
                if serialized_message is not None:
                    msg_ref = 'raw/%s_%09d.rosmsg' % (stream, seq)
                    write_new(self.path / msg_ref, serialized_message)
                    record.update(serialized_ref=msg_ref, serialized_sha256=sha(serialized_message))
                issues = record['diagnostics']
                if now < self.last_mono.get(stream, -1):
                    issues.append('receipt_clock_nonincreasing')
                elif now == self.last_mono.get(stream, -1):
                    record['warnings'].append('receipt_clock_resolution_collision')
                if stream in self.last_wall and wall < self.last_wall[stream]:
                    issues.append('wall_clock_backwards')
                self.last_mono[stream] = max(now, self.last_mono.get(stream, -1))
                self.last_wall[stream] = max(wall, self.last_wall.get(stream, -1))
                if source_stamp_ns in (None, 0):
                    record['warnings'].append('source_stamp_missing')
                else:
                    if source_stamp_ns <= self.last_source.get(stream, -1):
                        issues.append('source_clock_nonincreasing')
                    self.last_source[stream] = max(source_stamp_ns, self.last_source.get(stream, -1))
                    if spec['source_clock_id'] == 'unknown':
                        record['warnings'].append('source_clock_unknown')
                    if source_now_ns is not None:
                        # Adapter may supply only a clock explicitly matching this stream.
                        age = source_now_ns - source_stamp_ns
                        record['source_age_ns'] = age
                        if age < 0 or age > self.config['max_age_ns']:
                            issues.append('source_future_or_stale')
                if stream in ('high', 'low'):
                    try:
                        decoded = decode_image(data, descriptor or {})
                        record['decoded'] = dict(width=decoded.width, height=decoded.height, encoding='rgb8')
                    except Exception as exc:
                        issues.append('bad_image')
                        record['decode_error'] = type(exc).__name__ + ': ' + str(exc)
                else:
                    if (not isinstance(motion, dict) or set(motion) != {'vx_mps', 'vy_mps', 'wz_radps'}
                            or any(type(v) not in (int, float) or not math.isfinite(v) for v in motion.values())):
                        issues.append('invalid_motion')
                    else:
                        record['motion'] = motion
                record['valid'] = not issues
                self._line(self.index, record)
                self.counts[stream] += 1
                self.latest[stream] = record
                return record
            except BaseException as exc:
                self._fail('append_error: ' + repr(exc))
                raise

    def event(self, event_type, phase='point', interval_id=None, reason='', event_mono_ns=None,
              request_id=None):
        with self.lock:
            if self.closed or self.failed:
                raise RuntimeError('session is closed or failed')
            if not event_type or phase not in ('point', 'start', 'end'):
                raise ValueError('invalid event')
            if phase != 'point' and not interval_id:
                raise ValueError('interval_id required for start/end')
            now = time.monotonic_ns()
            stamp = now if event_mono_ns is None else event_mono_ns
            if type(stamp) is not int or stamp < 0:
                raise ValueError('invalid event time')
            value = dict(event_id=uuid.uuid4().hex, event_type=event_type, phase=phase,
                interval_id=interval_id, reason=reason, event_mono_ns=stamp,
                annotation_receipt_mono_ns=now, clock_id=self.clock_id, request_id=request_id)
            try:
                self._line(self.events, value)
            except BaseException as exc:
                self._fail('event_write_error: ' + repr(exc))
                raise
            return value

    def drain_requests(self):
        for path in sorted((self.path / 'requests').glob('*.json')):
            if path.name in self.processed_requests:
                continue
            value = load_json(path)
            self.event(value['event_type'], value['phase'], value.get('interval_id'),
                       value.get('reason', ''), request_id=path.stem)
            self.processed_requests.add(path.name)

    def status(self, now_ns=None):
        with self.lock:
            now = time.monotonic_ns() if now_ns is None else now_ns
            required = ['high', 'low'] + (['feedback'] if self.config['mode'] == 'demonstration' else [])
            streams = {}
            for name in required:
                r = self.latest.get(name)
                age = None if r is None else now - r['receipt_mono_ns']
                streams[name] = dict(count=self.counts[name], age_ns=age,
                    ready=bool(r and r['valid'] and 0 <= age <= self.config['max_age_ns']),
                    diagnostics=['missing_stream'] if r is None else r['diagnostics'])
            free = shutil.disk_usage(self.path).free
            return dict(ready=not self.failed and all(s['ready'] for s in streams.values())
                        and free >= self.config['reserve_bytes'], streams=streams, free_bytes=free,
                        physical_identity_verified=all(s['identity_verified'] for s in self.config['cameras'].values()))

    def close(self, reason='operator_stop', complete=True):
        with self.lock:
            if self.closed:
                return self.manifest
            self.closed = True
            try:
                for f in (self.index, self.events):
                    if f is not None and not f.closed:
                        f.flush()
                        os.fsync(f.fileno())
                        f.close()
                files = {}
                for p in sorted(self.path.rglob('*')):
                    if p.is_file() and p.name != 'manifest.json' and not p.name.endswith('.tmp'):
                        files[p.relative_to(self.path).as_posix()] = dict(sha256=hash_file(p), bytes=p.stat().st_size)
                self.manifest.update(complete=bool(complete and not self.failed),
                    state='complete' if complete and not self.failed else 'incomplete',
                    close_reason=self.manifest['close_reason'] if self.failed else reason,
                    end_mono_ns=time.monotonic_ns(), counts=dict(self.counts), raw_files=files)
                atomic_json(self.path / 'manifest.json', self.manifest)
            except BaseException as exc:
                self._fail('close_error: ' + repr(exc))
                for f in (self.index, self.events):
                    if f is not None and not f.closed:
                        try:
                            f.close()
                        except OSError:
                            pass
                raise
            return self.manifest
