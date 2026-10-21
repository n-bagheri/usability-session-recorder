"""Portable timeline, coordinate conversion, and heatmap generation."""
import json
from pathlib import Path


def estimate_origin(before_ns, after_ns, duration_ms):
    """Estimate video zero from an OBS status duration sampled during a request.

    Half RTT is only transport uncertainty, not a bound on OBS/media latency.
    """
    if after_ns < before_ns or duration_ms < 0:
        raise ValueError('Invalid clock sample')
    return {'origin_ns': (before_ns + after_ns) // 2 - round(duration_ms * 1_000_000),
            'half_rtt_ns': (after_ns - before_ns) // 2}


def video_seconds(event_ns, origin_ns, correction_ms=0):
    return (event_ns - origin_ns) / 1e9 + correction_ms / 1000


def relative_point(x, y, rect):
    left, top, width, height = rect
    if width <= 0 or height <= 0:
        raise ValueError('Rectangle must have positive dimensions')
    return ((x-left)/width, (y-top)/height,
            left <= x < left+width and top <= y < top+height)


def density(events, rect, kind, bins=128):
    import numpy as np
    if bins < 1:
        raise ValueError('bins must be positive')
    result = np.zeros((bins, bins), dtype=int)
    for e in events:
        if e['type'] != kind or (kind == 'click' and not e.get('pressed')):
            continue
        u, v, inside = relative_point(e['x'], e['y'], rect)
        if inside:
            result[min(int(v*bins), bins-1), min(int(u*bins), bins-1)] += 1
    return result


def generate_heatmaps(folder):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    folder = Path(folder)
    meta = json.loads((folder/'metadata.json').read_text())
    rect = meta['capture_rect']
    with (folder/'events.jsonl').open() as stream:
        events = [json.loads(line) for line in stream if line.strip()]
    if meta.get('target_calibration'):
        from .analysis import generate_target_heatmaps
        return generate_target_heatmaps(folder, meta, events)
    left, top, width, height = rect
    for kind in ('move', 'click'):
        grid = density(events, rect, kind)
        fig, ax = plt.subplots(figsize=(10, 6))
        plot = ax.imshow(grid, extent=(left, left+width, top+height, top),
                         origin='upper', cmap='hot', interpolation='nearest')
        ax.set(xlabel='Desktop physical X (pixels)', ylabel='Desktop physical Y (pixels)',
               title=f'{kind.title()} event counts (fixed capture rectangle)')
        fig.colorbar(plot, ax=ax, label='Events per bin')
        fig.savefig(folder/f'{kind}_heatmap.png', dpi=150)
        plt.close(fig)

    return {'alignment': {'status': 'unverified'}, 'legacy': True}
