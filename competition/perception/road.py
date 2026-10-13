"""Conservative black-guide/white-road candidate extractor, original pixels.

Public validity describes a pixel path estimate, never vehicle clearance or a
motion permit. Geometry is uncalibrated and carries no ground-distance units.
"""
import numpy as np


PARAMETERS = dict(roi_top=0.40, roi_bottom=0.90, row_step_fraction=0.01,
                  blue_margin=25, white_min=105, white_chroma=55,
                  black_max=80, minimum_row_coverage=0.90,
                  max_line_width_fraction=0.055)


def rgb_array(array, encoding):
    if array.dtype != np.uint8:
        raise ValueError('expected uint8 image')
    if encoding == 'mono8':
        if array.ndim != 2:
            raise ValueError('mono8 requires HxW')
        return np.repeat(array[:, :, None], 3, axis=2)
    if encoding not in ('rgb8', 'bgr8') or array.ndim != 3 or array.shape[2] != 3:
        raise ValueError('expected HxWx3 rgb8/bgr8')
    return array[:, :, ::-1] if encoding == 'bgr8' else array


def runs(mask):
    changes = np.diff(np.r_[False, mask, False].astype(np.int8))
    return list(zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1)))


def candidate(array, encoding='rgb8'):
    rgb = rgb_array(array, encoding)
    h, w = rgb.shape[:2]
    result = dict(candidate_valid=False, reason='insufficient_image_size', quality=0.0,
                  reference_x_px=(w - 1) / 2, reference_y_px=round((h - 1) * .70),
                  target_x_px=None, offset_px=None, path_px=[], rows_examined=0,
                  rows_supported=0, blue_fraction=0.0, white_fraction=0.0,
                  clearance_verified=False)
    if min(h, w) < 64:
        return result
    if encoding == 'mono8':
        result['reason'] = 'color_unavailable'
        return result
    p = PARAMETERS
    pixels = rgb.astype(np.int16)
    r, g, b = pixels[:, :, 0], pixels[:, :, 1], pixels[:, :, 2]
    hi, lo = pixels.max(axis=2), pixels.min(axis=2)
    blue = (b > r + p['blue_margin']) & (b > g + 10) & (b > 65)
    white = (lo >= p['white_min']) & (hi - lo <= p['white_chroma'])
    black = hi <= p['black_max']
    start, end = round(h * p['roi_top']), round(h * p['roi_bottom'])
    rows = list(range(start, end, max(1, round(h * p['row_step_fraction']))))
    result.update(rows_examined=len(rows), blue_fraction=float(blue[start:end].mean()),
                  white_fraction=float(white[start:end].mean()))
    points, missing, gap, max_gap = [], [], 0, 0
    reasons = []
    for y in rows:
        # White shoulders must bound a thin dark run within a road island that
        # itself has visible blue on both sides. No largest-component shortcut.
        corridors = []
        for left, right in runs(white[y] | black[y]):
            width = right - left
            if width < w * .15 or left < 2 or right > w - 2:
                continue
            flank = max(2, round(w * .015))
            if (blue[y, max(0, left-flank):left].mean() < .7 or
                    blue[y, right:min(w, right+flank)].mean() < .7):
                continue
            if white[y, left:right].mean() < .55:
                reasons.append('dark_occlusion_or_road_uncertain')
                continue
            corridors.append((left, right))
        row_points = []
        for left, right in corridors:
            for a, z in runs(black[y, left:right]):
                a, z = a + left, z + left
                size = z - a
                shoulder = max(3, round(w * .025))
                if size < max(2, w * .003):
                    continue
                if size > w * p['max_line_width_fraction']:
                    reasons.append('wide_dark_region_or_junction')
                    continue
                if a-left < shoulder or right-z < shoulder:
                    continue
                if (white[y, a-shoulder:a].mean() >= .85 and
                        white[y, z:z+shoulder].mean() >= .85):
                    row_points.append([float((a + z - 1) / 2), float(y)])
        if len(corridors) > 1 or len(row_points) > 1:
            reasons.append('multiple_paths_or_branch')
        if len(row_points) == 1 and len(corridors) == 1:
            points.append(row_points[0])
            gap = 0
        else:
            missing.append(y)
            gap += 1
            max_gap = max(max_gap, gap)
    coverage = len(points) / len(rows)
    result['rows_supported'] = len(points)
    if 'multiple_paths_or_branch' in reasons:
        result['reason'] = 'multiple_paths_or_branch'
    elif reasons:
        result['reason'] = reasons[0]
    elif coverage < p['minimum_row_coverage'] or max_gap > 2:
        result['reason'] = 'line_missing_or_road_unbounded'
    elif (points[0][1] > rows[1] or points[-1][1] < rows[-2]):
        result['reason'] = 'insufficient_near_far_support'
    elif max(abs(b[0] - a[0]) / max(1, b[1] - a[1]) for a, b in zip(points, points[1:])) > 2:
        result['reason'] = 'discontinuous_or_sharp_path'
    else:
        xs, ys = np.array(points).T
        target = float(np.interp(result['reference_y_px'], ys, xs))
        result.update(candidate_valid=True, reason='pixel_path_estimate_clearance_unverified',
                      quality=coverage, target_x_px=target,
                      offset_px=target-result['reference_x_px'], path_px=points)
    return result


def road_payload(frame_payload, diagnostics):
    """Expose pixel validity. Clearance and motion permission belong to A."""
    return dict(camera_id=frame_payload['camera_id'], frame_seq=frame_payload['frame_seq'],
                width_px=frame_payload['width_px'], height_px=frame_payload['height_px'],
                frame_stamp_ns=frame_payload['receipt_mono_ns'], valid=diagnostics['candidate_valid'],
                reason=diagnostics['reason'], quality=diagnostics['quality'],
                reference_x_px=diagnostics['reference_x_px'],
                reference_y_px=diagnostics['reference_y_px'], target_x_px=diagnostics['target_x_px'],
                offset_px=diagnostics['offset_px'], path_px=diagnostics['path_px'])
