"""Reproducible, conservative OS-window classification and coordinate transforms."""
import hashlib
import math


def title_digest(title):
    # Detect changes without saving browser titles/URLs in recordings.
    return hashlib.sha256(title.encode('utf-8')).hexdigest()


def same_identity(expected, actual):
    keys = ('hwnd', 'pid', 'process_started', 'class_name')
    return all(expected.get(k) is not None and expected[k] == actual.get(k) for k in keys)


def contains(rect, x, y):
    left, top, width, height = rect
    return width > 0 and height > 0 and left <= x < left+width and top <= y < top+height


def content_rect(calibration, snapshot):
    if calibration.get('method') == 'automatic_uia_obs':
        if snapshot.get('viewport_error') or not snapshot.get('viewport'):
            raise ValueError('Fresh automatic viewport measurement required')
        return snapshot['viewport']['rect']
    left, top, width, height = snapshot['client_rect']
    scale = snapshot['dpi'] / calibration['dpi']
    l, t, r, b = [round(v*scale) for v in calibration['insets']]
    if min(l, t, r, b) < 0 or width <= l+r or height <= t+b:
        raise ValueError('Content calibration does not fit current client rectangle')
    return [left+l, top+t, width-l-r, height-t-b]


def calibrate(snapshot, first, last):
    """Two physical-pixel content corners; last pixel is inclusive."""
    client = snapshot['client_rect']
    x, y = first
    right, bottom = last
    if not (contains(client, x, y) and contains(client, right, bottom) and right > x and bottom > y):
        raise ValueError('Choose top-left then bottom-right INSIDE the Chrome client area')
    left, top, width, height = client
    return {'version': 1, 'identity': snapshot['identity'], 'dpi': snapshot['dpi'],
            'title_digest': snapshot['title_digest'],
            'insets': [x-left, y-top, left+width-right-1, top+height-bottom-1],
            'reference_size': [right-x+1, bottom-y+1], 'maximized': snapshot.get('maximized', False),
            'assumption': 'User confirmed selected Chrome tab and page-content corners; not URL verification'}


def classify(x, y, calibration, snapshot):
    result = {'classification': 'uncertain', 'reason': 'observation_unavailable',
              'policy_version': 1}
    if not calibration or not snapshot or snapshot.get('error'):
        return result
    if not same_identity(calibration['identity'], snapshot.get('identity', {})):
        result['reason'] = 'target_identity_changed'
        return result
    if snapshot.get('observation_delayed'):
        return dict(result,reason='geometry_observation_delayed_over_100ms')
    if not snapshot.get('stable'):
        result['reason'] = 'window_changed_during_observation'
        return result
    if not snapshot.get('visible') or snapshot.get('minimized') or snapshot.get('cloaked'):
        return dict(result, classification='outside', reason='target_not_visible')
    if calibration.get('method') != 'automatic_uia_obs' and snapshot.get('maximized', False) != calibration.get('maximized', False):
        return dict(result, reason='window_mode_changed_recalibration_required')
    try:
        rect = content_rect(calibration, snapshot)
    except (KeyError, ValueError, ZeroDivisionError):
        return dict(result, reason='invalid_geometry_or_calibration')
    result['content_rect'] = rect
    result['layout_key'] = f'{rect[2]}x{rect[3]}-dpi{snapshot["dpi"]}'
    result['local'] = [x-rect[0], y-rect[1]]
    result['normalized'] = [(x-rect[0])/rect[2], (y-rect[1])/rect[3]]
    if not contains(rect, x, y):
        return dict(result, classification='outside', reason='outside_content_rectangle')
    if calibration.get('method') != 'automatic_uia_obs' and snapshot.get('title_digest') != calibration.get('title_digest'):
        return dict(result, reason='page_title_changed_recalibration_required')
    # Missing hit-test or capture information is not evidence of an inside event.
    if not snapshot.get('hit_root') or snapshot.get('capture_root') is None:
        return dict(result, reason='hit_test_or_capture_unavailable')
    hwnd = calibration['identity']['hwnd']
    if snapshot['hit_root'] != hwnd:
        return dict(result, classification='outside', reason='other_window_at_point')
    if snapshot.get('possible_occluders'):
        return dict(result, reason='possible_visual_occlusion')
    if snapshot['capture_root'] not in (0, hwnd):
        return dict(result, classification='outside', reason='other_window_has_mouse_capture')
    return dict(result, classification='inside', reason='calibrated_content_and_target_hit')


def frame_point(local, content_size, mapping):
    """Map an explicit source crop to an explicit frame rectangle; never infer OBS transforms."""
    if list(content_size) != mapping['content_size']:
        raise ValueError('Frame mapping is for a different content layout')
    sx, sy, sw, sh = mapping['source_rect']
    dx, dy, dw, dh = mapping['frame_rect']
    if not all(math.isfinite(v) for v in (*local, sx, sy, sw, sh, dx, dy, dw, dh)):
        raise ValueError('Non-finite coordinate')
    if sw <= 0 or sh <= 0 or dw <= 0 or dh <= 0:
        raise ValueError('Mapping rectangles must have positive dimensions')
    if not contains([sx, sy, sw, sh], *local):
        return None
    return [dx+(local[0]-sx)*dw/sw, dy+(local[1]-sy)*dh/sh]
