"""Offline inspection, independent image/feedback pairing and derived exports."""
import bisect
import collections
import json
from pathlib import Path

from . import STORAGE_VERSION
from .core import atomic_json, decode_image, dumps, hash_file, load_json, safe_ref, validate_config, write_new


def read_lines(path, errors):
    result = []
    try:
        data = Path(path).read_bytes()
        if data and not data.endswith(b'\n'):
            errors.append('truncated_jsonl: ' + Path(path).name)
        for number, line in enumerate(data.decode('utf-8').splitlines(), 1):
            try:
                result.append(json.loads(line, parse_constant=lambda v: (_ for _ in ()).throw(ValueError(v))))
            except (ValueError, TypeError):
                errors.append('bad_jsonl: %s:%d' % (Path(path).name, number))
    except (OSError, UnicodeError) as exc:
        errors.append('read_error: ' + str(exc))
    return result


def inspect_session(session):
    root = Path(session).resolve()
    manifest = load_json(root / 'manifest.json')
    config = validate_config(load_json(root / 'frozen_config.json'))
    errors, warnings = [], []
    if manifest.get('storage_version') != STORAGE_VERSION:
        raise ValueError('unsupported storage version')
    if manifest.get('complete') is not True:
        errors.append('session_incomplete')
    if manifest['config_sha256'] != hash_file(root / 'frozen_config.json'):
        errors.append('config_hash_mismatch')
    for key in ('split', 'role', 'mode', 'acquisition_method', 'cameras'):
        if manifest[key] != config[key]:
            errors.append('manifest_config_mismatch: ' + key)
    for ref, expected in manifest.get('raw_files', {}).items():
        try:
            path = safe_ref(root, ref)
            if path.stat().st_size != expected['bytes'] or hash_file(path) != expected['sha256']:
                errors.append('file_hash_mismatch: ' + ref)
        except (OSError, ValueError):
            errors.append('missing_or_unsafe_file: ' + ref)
    actual_files = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()
                    and p.name != 'manifest.json' and 'derived' not in p.relative_to(root).parts}
    if manifest.get('complete') and actual_files != set(manifest.get('raw_files', {})):
        errors.append('file_inventory_mismatch')
    rows = read_lines(root / 'receipts.jsonl', errors)
    events = read_lines(root / 'events.jsonl', errors)
    counts, decoded = collections.Counter(), collections.Counter()
    diags, previous, source_previous = collections.Counter(), {}, {}
    gaps = collections.defaultdict(list)
    content_hashes = collections.defaultdict(set)
    for r in rows:
        try:
            stream = r['stream_id']
            spec = config['cameras'][stream] if stream in ('high', 'low') else config[stream]
            if r['seq'] != counts[stream]:
                errors.append('index_sequence_mismatch: ' + stream)
            counts[stream] += 1
            if r['topic'] != spec['topic'] or r['physical_id'] != spec.get('physical_id'):
                errors.append('source_identity_mismatch: ' + stream)
            if r['clock_id'] != manifest['clock_id']:
                errors.append('receipt_clock_mismatch: ' + stream)
            if r['source_clock_id'] != spec['source_clock_id']:
                errors.append('source_clock_mismatch: ' + stream)
            prior = previous.get(stream)
            if prior is not None:
                delta = r['receipt_mono_ns'] - prior
                if delta < 0 and 'receipt_clock_nonincreasing' not in r['diagnostics']:
                    errors.append('unflagged_receipt_clock_error: ' + stream)
                if delta > config['max_age_ns']:
                    gaps[stream].append(dict(start_ns=prior, end_ns=r['receipt_mono_ns'], gap_ns=delta))
            previous[stream] = r['receipt_mono_ns']
            stamp = r['source_stamp_ns']
            if stamp:
                if stamp <= source_previous.get(stream, -1) and 'source_clock_nonincreasing' not in r['diagnostics']:
                    errors.append('unflagged_source_clock_error: ' + stream)
                source_previous[stream] = max(stamp, source_previous.get(stream, -1))
            path = safe_ref(root, r['raw_ref'])
            if path.stat().st_size != r['raw_size'] or hash_file(path) != r['raw_sha256']:
                errors.append('raw_hash_mismatch: ' + r['raw_ref'])
            if r.get('serialized_ref'):
                if hash_file(safe_ref(root, r['serialized_ref'])) != r['serialized_sha256']:
                    errors.append('serialized_hash_mismatch: ' + r['serialized_ref'])
            diags.update(r['diagnostics'])
            if r['valid'] != (not r['diagnostics']):
                errors.append('valid_flag_mismatch: ' + r['raw_ref'])
            if stream in ('high', 'low'):
                try:
                    image = decode_image(path.read_bytes(), r['descriptor'])
                    decoded[stream] += 1
                    content_hashes[stream].add(r['raw_sha256'])
                    if r.get('decoded') != dict(width=image.width, height=image.height, encoding='rgb8'):
                        errors.append('decoded_metadata_mismatch: ' + r['raw_ref'])
                except Exception:
                    if 'bad_image' not in r['diagnostics']:
                        errors.append('unflagged_bad_image: ' + r['raw_ref'])
        except (KeyError, TypeError, ValueError, OSError) as exc:
            errors.append('record_error: ' + repr(exc))
    if dict(counts) != manifest.get('counts'):
        errors.append('manifest_count_mismatch')
    required = ['high', 'low'] + (['feedback'] if config['mode'] == 'demonstration' else [])
    for stream in required:
        if not counts[stream]:
            errors.append('required_stream_missing: ' + stream)
    if content_hashes['high'] & content_hashes['low']:
        warnings.append('cross_camera_identical_bytes_suspicious_not_identity_proof')
    if not all(s['identity_verified'] for s in config['cameras'].values()):
        warnings.append('physical_identity_not_field_verified')
    requested = {p.stem for p in (root / 'requests').glob('*.json')}
    acknowledged = {e.get('request_id') for e in events if e.get('request_id')}
    if requested != acknowledged:
        errors.append('unacknowledged_event_requests')
    for e in events:
        if e.get('clock_id') != manifest['clock_id']:
            errors.append('event_clock_mismatch')
    intervals, annotation_errors = correction_intervals(events)
    errors.extend(annotation_errors)
    report = dict(storage_version=STORAGE_VERSION, session_id=manifest['session_id'],
        split=manifest['split'], role=manifest['role'], mode=manifest['mode'],
        recording_complete=manifest['complete'], integrity_ok=not errors,
        quality_ok=not errors and not diags and not any(gaps.values()),
        counts=dict(counts), decoded=dict(decoded), diagnostics=dict(diags),
        receipt_gaps=dict(gaps), errors=errors, warnings=warnings,
        correction_intervals=intervals, upstream_drop_count=None,
        physical_identity_verified=all(s['identity_verified'] for s in config['cameras'].values()),
        autonomous_success=None, code_commit=manifest['code_commit'],
        evidence_level='local_file_integrity_and_decode_only',
        limitations=['Receipt/header matching is software timing, not exposure synchronization.',
                     'No inferred human intent or action causality; no autonomous success assessment.'])
    return report, manifest, config, rows, events


EXCLUSION_TYPES = {'correction', 'reposition', 'lift', 'collision', 'out_of_bounds', 'takeover'}


def correction_intervals(events):
    intervals, active, errors = [], {}, []
    # File order is preserved, but annotation times determine interval order.
    for e in sorted(events, key=lambda e: e.get('event_mono_ns', -1)):
        if e.get('event_type') not in EXCLUSION_TYPES:
            continue
        key = e.get('interval_id')
        phase = e.get('phase')
        if phase == 'start' and key and key not in active:
            active[key] = e
        elif phase == 'end' and key in active:
            start = active.pop(key)
            if e['event_mono_ns'] <= start['event_mono_ns'] or e['clock_id'] != start['clock_id'] or e['event_type'] != start['event_type']:
                errors.append('invalid_correction_interval: ' + str(key))
            else:
                intervals.append(dict(interval_id=key, start_ns=start['event_mono_ns'],
                                      end_ns=e['event_mono_ns'], event_type=start['event_type']))
        else:
            errors.append('ambiguous_correction_annotation: ' + str(key))
    for key, start in active.items():
        intervals.append(dict(interval_id=key, start_ns=start['event_mono_ns'], end_ns=None,
                              event_type=start['event_type']))
        # Explicit conservative exclusion through end of session.
    return intervals, errors


def in_correction(stamp, intervals):
    return any(stamp >= i['start_ns'] and (i['end_ns'] is None or stamp < i['end_ns']) for i in intervals)


class PairIndex:
    def __init__(self, rows, policy):
        self.policy = policy
        self.groups = collections.defaultdict(list)
        for row in rows:
            t, domain = self.time(row)
            if row['valid'] and t is not None and domain != 'unknown':
                self.groups[domain].append((t, row['seq'], row))
        for group in self.groups.values():
            group.sort(key=lambda x: (x[0], x[1]))
        self.keys = {domain: [item[0] for item in group] for domain, group in self.groups.items()}

    def time(self, row):
        if self.policy['basis'] == 'source_header':
            return row['source_stamp_ns'] or None, row['source_clock_id']
        return row['receipt_mono_ns'], row['clock_id']

    def match(self, frame):
        stamp, domain = self.time(frame)
        result = dict(basis=self.policy['basis'], tolerance_ns=self.policy['tolerance_ns'],
            pairing_clock_id=domain, image_time_ns=stamp, matched_seq=None,
            matched_time_ns=None, signed_delta_ns=None, accepted=False, reasons=[])
        if not frame['valid']:
            result['reasons'].append('invalid_image_record')
        if stamp is None or domain == 'unknown':
            result['reasons'].append('image_clock_unknown')
            return result, None
        group = self.groups.get(domain, [])
        if not group:
            result['reasons'].append('no_valid_same_clock_candidate')
            return result, None
        i = bisect.bisect_left(self.keys[domain], stamp)
        candidates = group[max(0, i - 1):i + 1]
        t, seq, chosen = min(candidates, key=lambda x: (abs(x[0] - stamp), x[0], x[1]))
        delta = t - stamp
        result.update(matched_seq=seq, matched_time_ns=t, signed_delta_ns=delta)
        if abs(delta) > self.policy['tolerance_ns']:
            result['reasons'].append('outside_tolerance')
        result['accepted'] = not result['reasons']
        return result, chosen


def export_session(session, output):
    report, manifest, config, rows, events = inspect_session(session)
    if not report['integrity_ok']:
        raise ValueError('session integrity/annotation failed: ' + '; '.join(report['errors']))
    root, out = Path(session).resolve(), Path(output).resolve()
    # Never create exports inside raw or overwrite any existing output.
    if out == root or root in out.parents and 'derived' not in out.relative_to(root).parts[:1]:
        raise ValueError('output must be external or under session/derived/')
    out.mkdir(parents=True, exist_ok=False)
    export_manifest = dict(storage_version=STORAGE_VERSION, complete=False, session_id=manifest['session_id'],
        split=manifest['split'], role=manifest['role'], source_manifest_sha256=hash_file(root / 'manifest.json'),
        pairing=config['pairing'], correction_rule='exclude_image_or_matched_feedback_in_interval_start_inclusive_end_exclusive',
        source_events_sha256=hash_file(root / 'events.jsonl'), exporter_sha256=hash_file(Path(__file__)))
    atomic_json(out / 'manifest.json', export_manifest)
    try:
        feedback = PairIndex([r for r in rows if r['stream_id'] == 'feedback'], config['pairing'])
        commands = PairIndex([r for r in rows if r['stream_id'] == 'command'], config['pairing'])
        low = PairIndex([r for r in rows if r['stream_id'] == 'low'], config['pairing'])
        for camera in ('high', 'low'):
            (out / 'images' / camera).mkdir(parents=True)
        stats = {c: dict(frames=0, decoded=0, feedback_paired=0, demonstration_samples=0,
                         excluded_correction=0, rejection_reasons=collections.Counter(), signed_skews_ns=[])
                 for c in ('high', 'low')}
        public = []
        public_last_stamp = {}
        public_omissions = collections.Counter()
        with (out / 'samples.jsonl').open('x', encoding='utf-8') as samples, \
                (out / 'pair_audit.jsonl').open('x', encoding='utf-8') as audit, \
                (out / 'camera_pairs.jsonl').open('x', encoding='utf-8') as camera_pairs:
            from .adapter import camera_frame
            for r in rows:
                camera = r['stream_id']
                if camera not in stats:
                    continue
                s = stats[camera]
                s['frames'] += 1
                pair, candidate = feedback.match(r)
                command_pair, command_candidate = commands.match(r)
                audit.write(dumps(dict(camera_id=camera, frame_seq=r['seq'], feedback=pair, command=command_pair)) + '\n')
                if camera == 'high':
                    camera_pair, _ = low.match(r)
                    camera_pairs.write(dumps(dict(high_frame_seq=r['seq'], low_match=camera_pair)) + '\n')
                s['rejection_reasons'].update(pair['reasons'])
                measured = candidate['motion'] if pair['accepted'] else None
                command = command_candidate['motion'] if command_pair['accepted'] else None
                if pair['accepted']:
                    s['feedback_paired'] += 1
                    s['signed_skews_ns'].append(pair['signed_delta_ns'])
                excluded = in_correction(r['receipt_mono_ns'], report['correction_intervals']) or (
                    candidate is not None and pair['accepted'] and
                    in_correction(candidate['receipt_mono_ns'], report['correction_intervals']))
                if excluded:
                    s['excluded_correction'] += 1
                image_ref = None
                # Decode all decodable original images, including clock-invalid records.
                if 'bad_image' not in r['diagnostics']:
                    image = decode_image(safe_ref(root, r['raw_ref']).read_bytes(), r['descriptor'])
                    image_ref = 'images/%s/%09d.png' % (camera, r['seq'])
                    with (out / image_ref).open('xb') as f:
                        image.save(f, format='PNG')
                    s['decoded'] += 1
                    if r['valid']:
                        normalized = camera_frame(manifest, r, image_ref)
                        if normalized is None:
                            public_omissions['unknown_source_domain_with_nonzero_stamp'] += 1
                        elif normalized['stamp_ns'] <= public_last_stamp.get(camera, -1):
                            public_omissions['receipt_resolution_collision'] += 1
                        else:
                            public.append(normalized)
                            public_last_stamp[camera] = normalized['stamp_ns']
                demonstration_eligible = (config['mode'] == 'demonstration' and
                    config['role'] in ('manual_demonstration', 'synthetic') and
                    r['valid'] and pair['accepted'] and not excluded)
                s['demonstration_samples'] += int(demonstration_eligible)
                reasons = list(r['diagnostics'])
                if excluded:
                    reasons.append('manual_correction')
                if config['mode'] == 'visual_only':
                    reasons.append('visual_only_no_action_training')
                if not pair['accepted']:
                    reasons.extend(pair['reasons'])
                sample = dict(session_id=manifest['session_id'], split=manifest['split'], role=manifest['role'],
                    camera_id=camera, frame_seq=r['seq'], image_ref=image_ref, raw_ref=r['raw_ref'],
                    image_valid=r['valid'], measured_motion=measured, observed_command=command,
                    human_intent=None, demonstration_eligible=demonstration_eligible,
                    training_use='engineering_fixture_only' if config['role'] == 'synthetic' else
                        ('measured_motion_research_only' if demonstration_eligible else 'not_demonstration'),
                    exclusion_reasons=reasons)
                samples.write(dumps(sample) + '\n')
        write_new(out / 'events.jsonl', (root / 'events.jsonl').read_bytes())
        write_new(out / 'camera_frames.jsonl', ''.join(dumps(r) + '\n' for r in public).encode('utf-8'))
        for s in stats.values():
            values = sorted(abs(v) for v in s.pop('signed_skews_ns'))
            s['max_abs_skew_ns'] = max(values) if values else None
            s['p95_abs_skew_ns'] = values[max(0, (95 * len(values) + 99) // 100 - 1)] if values else None
            s['feedback_pair_fraction'] = s['feedback_paired'] / s['frames'] if s['frames'] else None
        report.update(cameras=stats, pairing=config['pairing'], denominator='all_received_images_per_camera',
            labels=dict(measured_motion='odometry; not a command', observed_command='observed Twist; not human intent', human_intent=None),
            public_frame_count=len(public), public_omissions=dict(public_omissions),
            public_adapter_limit='Unknown source domain or equal-resolution receipt stamps omitted from public camera_frames; retained in samples/raw. No timestamp invention.',
            export_kind='engineering_fixture_only' if config['role'] == 'synthetic' else config['mode'])
        if config['mode'] == 'demonstration' and any(s['feedback_paired'] == 0 for s in stats.values()):
            report['quality_ok'] = False
            report['errors'].append('no_feedback_pairs_for_one_or_both_cameras')
        report['demonstration_usable'] = (config['mode'] == 'demonstration' and
            config['role'] in ('manual_demonstration', 'synthetic') and
            all(s['demonstration_samples'] > 0 for s in stats.values()) and report['quality_ok'])
        if config['mode'] == 'demonstration' and not report['demonstration_usable']:
            report['quality_ok'] = False
            report['errors'].append('no_usable_demonstration_or_quality_rejected')
        atomic_json(out / 'quality.json', report)
        export_manifest.update(complete=True, quality_ok=report['quality_ok'],
            files={p.relative_to(out).as_posix(): hash_file(p) for p in out.rglob('*')
                   if p.is_file() and p.name != 'manifest.json'})
        atomic_json(out / 'manifest.json', export_manifest)
        return report
    except BaseException as exc:
        export_manifest.update(complete=False, error=repr(exc))
        try:
            atomic_json(out / 'manifest.json', export_manifest)
        except OSError:
            pass
        raise


def inspect_export(output):
    root = Path(output).resolve()
    m = load_json(root / 'manifest.json')
    errors = []
    if m.get('complete') is not True:
        errors.append('export_incomplete')
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p.name != 'manifest.json'}
    if actual != set(m.get('files', {})):
        errors.append('export_inventory_mismatch')
    for ref, expected in m.get('files', {}).items():
        try:
            if hash_file(safe_ref(root, ref)) != expected:
                errors.append('hash_mismatch: ' + ref)
        except (OSError, ValueError):
            errors.append('missing_or_unsafe: ' + ref)
    rows = read_lines(root / 'samples.jsonl', errors)
    try:
        from competition.interfaces.validate import validate_stream
        validate_stream(read_lines(root / 'camera_frames.jsonl', errors))
    except ValueError as exc:
        errors.append('public_adapter_error: ' + str(exc))
    for row in rows:
        if row.get('image_ref'):
            try:
                decode_image(safe_ref(root, row['image_ref']).read_bytes(), {'format': 'compressed'})
            except Exception:
                errors.append('bad_export_image: ' + str(row['image_ref']))
        if row['session_id'] != m['session_id'] or row['split'] != m['split']:
            errors.append('session_split_mismatch')
    return dict(integrity_ok=not errors, errors=errors, samples=len(rows),
                quality=load_json(root / 'quality.json'))
