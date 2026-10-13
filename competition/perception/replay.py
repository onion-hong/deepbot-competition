"""Replay image directories or frozen-contract camera_frame JSONL; offline only."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import platform
import shutil
import time
import uuid

import numpy as np
from PIL import Image, ImageDraw, __version__ as pillow_version

from competition.interfaces.validate import VERSION, loads, validate
from .road import PARAMETERS, candidate, road_payload


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.write('\n')


def emit(stream, value):
    stream.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + '\n')


def load_image(path, expected=None):
    # JPEG/PNG contain decoded color, not raw OpenCV byte ordering. Pillow
    # returns RGB; do not swap red/blue based on acquisition encoding metadata.
    with Image.open(path) as image:
        if image.format not in ('JPEG', 'PNG') or image.mode not in ('RGB', 'L'):
            raise ValueError('unsupported_image_format_or_mode')
        if image.getexif().get(274, 1) != 1:
            raise ValueError('oriented_exif_requires_explicit_conversion')
        image.load()
        if expected and image.size != (expected['width_px'], expected['height_px']):
            raise ValueError('decoded_dimensions_mismatch')
        if expected and ((image.mode == 'L') != (expected['encoding'] == 'mono8')):
            raise ValueError('decoded_channels_mismatch')
        return np.array(image), 'mono8' if image.mode == 'L' else 'rgb8'


def overlay(array, encoding, diagnostic, destination):
    image = Image.fromarray(array).convert('RGB')
    draw = ImageDraw.Draw(image)
    x, y = diagnostic['reference_x_px'], diagnostic['reference_y_px']
    draw.line([(x, 0), (x, image.height-1)], fill='orange', width=2)
    draw.line([(0, y), (image.width-1, y)], fill='orange', width=2)
    if diagnostic['path_px']:
        draw.line([tuple(p) for p in diagnostic['path_px']], fill='lime', width=3)
    text = ('PIXEL VALID' if diagnostic['candidate_valid'] else 'INVALID') + ' | ' + diagnostic['reason']
    draw.rectangle((0, 0, min(image.width, len(text)*7), 20), fill='black')
    draw.text((3, 3), text, fill='white')
    with destination.open('xb') as stream:
        image.save(stream, format='PNG')


def _inputs(root, manifest):
    if manifest:
        for number, line in enumerate(manifest.read_text(encoding='utf-8-sig').splitlines(), 1):
            if line.strip():
                yield number, line, None
    else:
        files = sorted(p for p in root.rglob('*') if p.suffix.lower() in ('.jpg', '.jpeg', '.png'))
        for number, path in enumerate(files, 1):
            yield number, None, path


def replay(root, output, manifest=None, camera_id=None, dataset_role='unknown'):
    root, output = Path(root).resolve(), Path(output).resolve()
    manifest = Path(manifest).resolve() if manifest else None
    if not root.is_dir():
        raise ValueError('input root must be an existing directory')
    if not manifest and camera_id not in ('high', 'low'):
        raise ValueError('directory mode requires explicit high/low role')
    inputs = list(_inputs(root, manifest))
    if not inputs:
        raise ValueError('no input frames; no successful replay claimed')
    output.mkdir(parents=True, exist_ok=False)
    (output / 'overlays').mkdir()
    (output / 'images').mkdir()
    replay_id = 'offline-replay-' + uuid.uuid4().hex
    clock_id = replay_id + '-perf-counter'
    summary = dict(replay_id=replay_id, dataset_role=dataset_role, complete=False,
                   input_count=len(inputs), processed=0, rejected=0,
                   candidate_valid=0, public_valid=0, by_camera={}, reasons={},
                   autonomous_success=False, vehicle_clearance_verified=False,
                   coverage='Only supplied images; no route coverage inferred from frame count.',
                   asset_resolution='records.jsonl image_ref resolves from this output directory; source image mapping is in provenance.jsonl.',
                   motion_permission=False,
                   timing='New high-resolution monotonic perf_counter_ns replay receipt clock; original records retained unchanged in provenance.jsonl.',
                   code_state='uncommitted', python=platform.python_version(),
                   numpy=np.__version__, pillow=pillow_version, parameters=PARAMETERS,
                   code_sha256={p.name: digest(p) for p in Path(__file__).parent.glob('*.py')},
                   test_sha256={p.name: digest(p) for p in
                                (Path(__file__).parents[1] / 'tests' / 'perception').glob('test_*.py')},
                   interface_sha256={p.name: digest(p) for p in
                                     (Path(__file__).parents[1] / 'interfaces').glob('*') if p.is_file()},
                   manifest_sha256=digest(manifest) if manifest else None)
    reasons, roles = Counter(), Counter()
    seen, previous, physical_roles = set(), {}, {}
    source_session = None
    with (output / 'records.jsonl').open('x', encoding='utf-8') as records, \
         (output / 'diagnostics.jsonl').open('x', encoding='utf-8') as diagnostics, \
         (output / 'provenance.jsonl').open('x', encoding='utf-8') as provenance:
        for index, text, path in inputs:
            source, image_hash = None, None
            try:
                if text is not None:
                    source = loads(text)
                    validate(source)
                    if source['kind'] != 'camera_frame':
                        raise ValueError('manifest_requires_camera_frame_only')
                    if source_session is not None and source['session_id'] != source_session:
                        raise ValueError('one_source_session_per_replay_required')
                    source_session = source['session_id']
                    p = source['payload']
                    path = (root / p['image_ref']).resolve()
                    if root not in path.parents:
                        raise ValueError('image_ref_escapes_root')
                    key = (source['session_id'], p['camera_id'])
                    identity = key + (p['frame_seq'],)
                    if identity in seen:
                        raise ValueError('duplicate_frame_identity')
                    last = previous.get(key)
                    if last:
                        lp = last['payload']
                        if (source['clock_id'] != last['clock_id'] or
                                p['receipt_mono_ns'] <= lp['receipt_mono_ns'] or
                                p['frame_seq'] <= lp['frame_seq'] or source['seq'] <= last['seq']):
                            raise ValueError('nonincreasing_receipt_sequence_or_clock_change')
                        if p['physical_id'] != lp['physical_id']:
                            raise ValueError('physical_identity_changed')
                        if p['source_stamp_ns'] is not None and lp['source_stamp_ns'] is not None:
                            if (p['source_clock_id'] != lp['source_clock_id'] or
                                    p['source_stamp_ns'] <= lp['source_stamp_ns']):
                                raise ValueError('nonincreasing_source_time_or_clock_change')
                    physical_key = (source['session_id'], p['physical_id'])
                    if physical_roles.get(physical_key, p['camera_id']) != p['camera_id']:
                        raise ValueError('same_physical_camera_in_two_roles')
                    seen.add(identity)
                    previous[key] = source
                    physical_roles[physical_key] = p['camera_id']
                else:
                    p = None
                    if root not in path.resolve().parents:
                        raise ValueError('image_ref_escapes_root')
                image_hash = digest(path)
                array, encoding = load_image(path, p)
                h, w = array.shape[:2]
                source_ref = path.relative_to(root).as_posix()
                image_ref = 'images/%06d%s' % (index, path.suffix.lower())
                with path.open('rb') as src, (output / image_ref).open('xb') as dst:
                    shutil.copyfileobj(src, dst)
                if digest(output / image_ref) != image_hash:
                    raise ValueError('source_image_changed_during_copy')
                stamp, unix = time.perf_counter_ns(), time.time_ns()
                # Replay identities are a distinct session. Source identity and
                # acquisition receipts are copied verbatim to provenance only.
                frame_p = dict(camera_id=p['camera_id'] if p else camera_id,
                               physical_id=p['physical_id'] if p else 'unverified-directory-' + camera_id,
                               frame_seq=p['frame_seq'] if p else index-1, width_px=w, height_px=h,
                               encoding=encoding, image_ref=image_ref,
                               source_stamp_ns=p['source_stamp_ns'] if p else None,
                               source_clock_id=p['source_clock_id'] if p else 'unknown',
                               receipt_unix_ns=unix, receipt_mono_ns=stamp)
                frame = dict(schema_version=VERSION, kind='camera_frame', session_id=replay_id,
                             seq=index-1, stamp_ns=stamp, clock_id=clock_id, payload=frame_p)
                diag = candidate(array, encoding)
                road = dict(schema_version=VERSION, kind='road', session_id=replay_id,
                            seq=index-1, stamp_ns=time.perf_counter_ns(), clock_id=clock_id,
                            payload=road_payload(frame_p, diag))
                validate(frame)
                validate(road)
                overlay(array, encoding, diag, output / 'overlays' / ('%06d.png' % index))
                emit(records, frame)
                emit(records, road)
                diag.update(input_index=index, replay_frame_seq=frame_p['frame_seq'],
                            camera_id=frame_p['camera_id'], image_sha256=image_hash,
                            decoded_encoding=encoding)
                emit(diagnostics, diag)
                emit(provenance, dict(input_index=index, original_record=source,
                                     original_image_ref=source_ref,
                                     image_ref=frame_p['image_ref'], image_sha256=image_hash,
                                     replay_frame_seq=frame_p['frame_seq'], status='processed'))
                summary['processed'] += 1
                summary['candidate_valid'] += int(diag['candidate_valid'])
                summary['public_valid'] += int(road['payload']['valid'])
                reasons[diag['reason']] += 1
                roles[frame_p['camera_id']] += 1
            except (ValueError, OSError, KeyError, TypeError) as exc:
                summary['rejected'] += 1
                reason = str(exc)
                reasons['input_rejected:' + reason] += 1
                emit(provenance, dict(input_index=index, original_record=source,
                                     original_line=text, image_sha256=image_hash,
                                     status='rejected', reason=reason))
    summary.update(complete=True, reasons=dict(reasons), by_camera=dict(roles))
    write_json(output / 'summary.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='image/session root')
    parser.add_argument('--manifest', type=Path, help='camera_frame-only JSONL')
    parser.add_argument('--camera-id', choices=('high', 'low'), help='required for directory input')
    parser.add_argument('--dataset-role', choices=('synthetic', 'static', 'visual_sequence', 'unknown'), default='unknown')
    parser.add_argument('--output', type=Path, required=True, help='new directory; existing path rejected')
    args = parser.parse_args()
    result = replay(args.root, args.output, args.manifest, args.camera_id, args.dataset_role)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result['rejected'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
