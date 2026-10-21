"""MapGen-only, layout-separated heatmaps and explicit frame alignment."""
import json
from collections import Counter, defaultdict
from pathlib import Path
from .targeting import classify, frame_point


def target_events(events, calibration):
    groups = defaultdict(list)
    counts = Counter(included=0, excluded=0, uncertain=0)
    clicks = Counter(included=0, excluded=0, uncertain=0)
    reasons = Counter()
    for event in events:
        if event['type'] not in ('move', 'click', 'scroll'):
            continue
        result = classify(event['x'], event['y'], calibration, event.get('target_observation'))
        category = {'inside': 'included', 'outside': 'excluded', 'uncertain': 'uncertain'}[result['classification']]
        counts[category] += 1
        reasons[result['reason']] += 1
        if event['type'] == 'click' and event.get('pressed'):
            clicks[category] += 1
        if category == 'included':
            groups[result['layout_key']].append(dict(event, x=result['local'][0], y=result['local'][1],
                                                    content_size=result['content_rect'][2:]))
    return groups, {'mouse_events': dict(counts), 'click_presses': dict(clicks), 'reasons': dict(reasons)}


def validate_mapping(mapping, image_size):
    if list(image_size) != mapping['frame_size']:
        raise ValueError('Reference frame dimensions differ from calibration')
    source, dest = mapping['source_rect'], mapping['frame_rect']
    if len(source) != 4 or len(dest) != 4 or len(mapping['content_size']) != 2:
        raise ValueError('Invalid rectangle dimensions')
    # Exercise finite/positive validation even when no clicks exist.
    frame_point(source[:2], mapping['content_size'], mapping)
    for rect, size in ((source, mapping['content_size']), (dest, image_size)):
        x, y, w, h = rect
        if x < 0 or y < 0 or x+w > size[0] or y+h > size[1]:
            raise ValueError('Mapping rectangle extends beyond source content or frame')


def click_overlay(folder, events, mapping):
    from PIL import Image, ImageDraw
    folder = Path(folder)
    # Keep reference frames local to the session; no filesystem traversal.
    name = mapping['frame_file']
    if Path(name).name != name:
        raise ValueError('frame_file must be a filename inside the session folder')
    with Image.open(folder/name) as source:
        validate_mapping(mapping, source.size)
        image = source.convert('RGB')
    draw = ImageDraw.Draw(image)
    included = cropped = 0
    for event in events:
        if event['type'] != 'click' or not event.get('pressed'):
            continue
        point = frame_point([event['x'], event['y']], event['content_size'], mapping)
        if point is None:
            cropped += 1
            continue
        included += 1
        x, y = point
        draw.ellipse((x-7, y-7, x+7, y+7), outline='red', width=3)
        draw.text((x+9, y), str(included), fill='red')
    image.save(folder/'mapgen_click_overlay.png')
    return {'status': 'calibrated_mapping_applied_visual_verification_required',
            'layout_key': mapping['layout_key'], 'plotted_clicks': included,
            'clicks_outside_source_crop': cropped,
            'mapping': mapping}


def generate_target_heatmaps(folder, meta, events):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from .core import density
    folder = Path(folder)
    groups, report = target_events(events, meta['target_calibration'])
    report['layouts'] = {}
    for key, selected in groups.items():
        width, height = selected[0]['content_size']
        files = []
        for kind in ('move', 'click'):
            fig, ax = plt.subplots(figsize=(10, 6))
            grid = density(selected, [0, 0, width, height], kind)
            plot = ax.imshow(grid, extent=(0, width, height, 0), origin='upper',
                             cmap='hot', interpolation='nearest')
            ax.set(xlabel='MapGen-local physical X (pixels)', ylabel='MapGen-local physical Y (pixels)',
                   title=f'MapGen-only {kind} event counts — {key}')
            fig.colorbar(plot, ax=ax, label='Events per bin')
            name = f'mapgen_{kind}_{key}.png'
            fig.savefig(folder/name, dpi=150)
            plt.close(fig)
            files.append(name)
        report['layouts'][key] = {'content_size': [width, height], 'files': files,
                                  'mouse_events': len(selected),
                                  'click_presses': sum(e['type'] == 'click' and e.get('pressed', False) for e in selected)}
    # Do not leave a stale overlay suggesting current validation succeeded.
    (folder/'mapgen_click_overlay.png').unlink(missing_ok=True)
    report['alignment'] = {'status': 'unverified', 'action': 'Supply frame_mapping.json and a reference frame; no OBS transform inferred'}
    mapping_file = folder/'frame_mapping.json'
    if mapping_file.exists():
        try:
            mapping = json.loads(mapping_file.read_text(encoding='utf-8'))
            key = mapping['layout_key']
            if key not in groups:
                raise ValueError('No included events match the calibrated layout')
            report['alignment'] = click_overlay(folder, groups[key], mapping)
        except (KeyError, ValueError, OSError) as exc:
            report['alignment'] = {'status': 'unverified', 'error': str(exc)}
    (folder/'analysis.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report
