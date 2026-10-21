"""Non-destructive analysis intervals and named view/stable-state segments."""
import copy
import json
import math
import time
from pathlib import Path


def save_json(path,data):
    path = Path(path)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,indent=2,allow_nan=False),encoding='utf-8')
    temp.replace(path)


def load_review(folder,duration):
    path = Path(folder)/'review.json'
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    return {'version':1,'analysis_interval':[0,duration],'segments':[],
            'spatial_measurements':[],'temporal_measurements':[],
            'visually_inspected_mapping_ids':[],'time_correction':{},'classification_labels':[],
            'validation_environment':'unverified',
            'note':'Unknown gaps stay unclassified; view/state labels are researcher annotations, not automatic semantics'}


def validate_review(review,duration):
    start,end = review['analysis_interval']
    if not (math.isfinite(start) and math.isfinite(end) and 0<=start<end<=duration+.001):
        raise ValueError('Analysis interval must lie inside the saved video')
    previous = 0
    ids = set()
    for segment in sorted(review['segments'],key=lambda s:s['start']):
        a,b = segment['start'],segment['end']
        if not (math.isfinite(a) and math.isfinite(b) and 0<=a<b<=duration+.001 and a>=previous):
            raise ValueError('Segments must be finite, non-overlapping and inside saved video')
        if not segment['id'] or segment['id'] in ids or not segment['view'].strip() or not segment['state'].strip():
            raise ValueError('Each segment needs a unique ID, view label and visual-state label')
        if not a<=segment.get('reference_seconds',a)<b:
            raise ValueError('Reference frame must be inside its segment')
        previous=b
        ids.add(segment['id'])


def write_review(folder,review,duration):
    validate_review(review,duration)
    path = Path(folder)/'review.json'
    if path.exists():
        history = Path(folder)/'review_history'
        history.mkdir(exist_ok=True)
        (history/f'{time.time_ns()}.json').write_bytes(path.read_bytes())
    save_json(path,review)


def segment_at(seconds,review):
    start,end = review['analysis_interval']
    if not start<=seconds<end:
        return None,'administrative'
    for segment in review['segments']:
        if segment['start']<=seconds<segment['end']:
            return segment,'annotated'
    return None,'unknown'


def paired_clicks(events):
    pending,complete,unmatched = {},[],[]
    for event in events:
        if event['type']!='click': continue
        key=event.get('button','unknown')
        if event.get('pressed'):
            if key in pending: unmatched.append(pending[key])
            pending[key]=event
        elif key in pending:
            complete.append((pending.pop(key),event))
        else:
            unmatched.append(event)
    return complete,unmatched+list(pending.values())
