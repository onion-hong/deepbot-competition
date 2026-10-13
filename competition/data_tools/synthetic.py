"""Tiny valid image fixtures and two independent synthetic streams. No device access."""
import io
import time

from PIL import Image, ImageDraw

from .core import SessionWriter, dumps


def image_bytes(camera, number=0):
    image = Image.new('RGB', (64, 48), (220, 20, 30) if camera == 'high' else (20, 40, 220))
    draw = ImageDraw.Draw(image)
    draw.rectangle((number % 40, 10, number % 40 + 12, 30), fill=(10, 230, 40))
    out = io.BytesIO()
    image.save(out, format='PNG')
    return out.getvalue()


def capture(root, session_id, config, seconds, interval=0.1):
    if config['role'] != 'synthetic':
        raise ValueError('synthetic backend requires role=synthetic')
    writer = SessionWriter(root, session_id, config)
    reason, success = 'synthetic_duration', False
    print('SESSION=' + str(writer.path), flush=True)
    motions = [(0, 0, 0), (-0.03, 0, 0), (0, 0.03, 0), (0.02, 0, 0.1)]
    try:
        i = 0
        while time.monotonic_ns() - writer.start_ns < seconds * 1_000_000_000:
            writer.drain_requests()
            if (writer.path / 'STOP_RECORDING').exists():
                reason = 'operator_stop'
                break
            stamp = time.time_ns()
            if config.get('feedback'):
                vx, vy, wz = motions[i % len(motions)]
                motion = dict(vx_mps=vx, vy_mps=vy, wz_radps=wz)
                writer.append('feedback', dumps(motion).encode('utf-8'), motion=motion, source_stamp_ns=stamp)
            for camera in ('high', 'low'):
                writer.append(camera, image_bytes(camera, i), descriptor={'format': 'compressed'},
                    source_stamp_ns=stamp + (1_000_000 if camera == 'low' else 0),
                    message_metadata={'original_format': '', 'header_frame_id': 'camera', 'synthetic': True})
            print(dumps(writer.status()), flush=True)
            i += 1
            time.sleep(interval)
        success = all(writer.counts[c] > 0 for c in ('high', 'low'))
    except KeyboardInterrupt:
        reason = 'operator_interrupt'
        success = all(writer.counts[c] > 0 for c in ('high', 'low'))
    finally:
        try:
            writer.drain_requests()
        except Exception as exc:
            success = False
            writer.manifest['errors'].append('event_drain_error: ' + repr(exc))
        writer.close(reason, complete=success)
    print('CLOSED=' + dumps(dict(path=str(writer.path), complete=writer.manifest['complete'])), flush=True)
    return 0 if writer.manifest['complete'] else 2
