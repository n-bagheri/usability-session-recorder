"""Save explicit source-content to reference-frame mapping, without guessing OBS transforms."""
import json
import uuid
from pathlib import Path
from .analysis import validate_mapping


def save_frame_mapping(folder, image_path, layout_key, source_rect, frame_rect):
    from PIL import Image
    folder = Path(folder)
    report = json.loads((folder/'analysis.json').read_text(encoding='utf-8'))
    content_size = report['layouts'][layout_key]['content_size']
    name = 'reference-'+uuid.uuid4().hex[:8]+'.png'
    with Image.open(image_path) as image:
        mapping = {'version': 1, 'layout_key': layout_key, 'content_size': content_size,
                   'source_rect': list(source_rect), 'frame_rect': list(frame_rect),
                   'frame_size': list(image.size), 'frame_file': name,
                   'method': 'User-calibrated axis-aligned source crop and destination bounds; not OBS-inferred'}
        validate_mapping(mapping, image.size)
        image.convert('RGB').save(folder/name)
    path = folder/'frame_mapping.json'
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(mapping, indent=2), encoding='utf-8')
    temp.replace(path)
    return mapping
