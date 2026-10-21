"""Offline timeline report: python -m recorder.tools SESSION_FOLDER."""
import argparse
import json
from pathlib import Path
from .core import video_seconds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    sync = json.loads((args.folder/'sync.json').read_text())
    origin = sync['origin_ns']
    correction = sync['manual_correction_ms']
    report = {'estimated_origin_ns': origin, 'manual_correction_ms': correction,
              'sample_origin_spread_ms': (max(s['origin_ns'] for s in sync['samples'])-
                                         min(s['origin_ns'] for s in sync['samples']))/1e6,
              'markers': [dict(m, estimated_video_seconds=video_seconds(m['monotonic_ns'],origin,correction))
                          for m in sync['markers']]}
    print(json.dumps(report, indent=2))
    # Derived timeline is reproducible; raw events remain unchanged.
    with (args.folder/'events.jsonl').open() as source, (args.folder/'timeline.jsonl').open('w') as target:
        for line in source:
            event = json.loads(line)
            event['estimated_video_seconds'] = video_seconds(event['monotonic_ns'],origin,correction)
            target.write(json.dumps(event)+'\n')


if __name__ == '__main__':
    main()
