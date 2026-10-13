"""Explicit adapter to unchanged A deepbot.offline/0.1.0 camera_frame records."""
from competition.interfaces.validate import validate


def camera_frame(manifest, receipt, image_ref):
    source = receipt['source_stamp_ns'] or None
    domain = receipt['source_clock_id'] if source is not None else 'unknown'
    if source is not None and domain == 'unknown':
        return None  # Do not fabricate a source clock or erase a real raw timestamp.
    row = dict(schema_version='deepbot.offline/0.1.0', kind='camera_frame',
        session_id=manifest['session_id'], seq=receipt['seq'], stamp_ns=receipt['receipt_mono_ns'],
        clock_id=receipt['clock_id'], payload=dict(camera_id=receipt['stream_id'],
            physical_id=receipt['physical_id'], frame_seq=receipt['seq'],
            width_px=receipt['decoded']['width'], height_px=receipt['decoded']['height'],
            encoding='rgb8', image_ref=image_ref, source_stamp_ns=source, source_clock_id=domain,
            receipt_unix_ns=receipt['receipt_unix_ns'], receipt_mono_ns=receipt['receipt_mono_ns']))
    validate(row)
    return row
