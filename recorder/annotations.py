"""Pure, non-destructive editing operations for view intervals and visual AOIs."""
import copy
import math
import uuid
import re
from datetime import datetime,timezone


def stamp():return datetime.now(timezone.utc).isoformat()


def new_aoi(segment,label,rect,frame,confirmed=False,semantic_id=None):
    return {'id':uuid.uuid4().hex[:12],'semantic_id':semantic_id or label.strip().lower().replace(' ','-'),
            'label':label.strip(),'segment_id':segment['id'],'rect':list(rect),'coordinate_space':'recorded_frame_pixels',
            'valid_interval':[segment['start'],segment['end']],'reference_frame':copy.deepcopy(frame),
            'layout_confirmed':bool(confirmed),'priority':0,'created_utc':stamp(),'updated_utc':stamp(),
            'provenance':'researcher_drawn_visual_region_not_DOM_identity'}


def validate_annotations(review,duration,frame_size=None):
    segments={s['id']:s for s in review['segments']};ids=set()
    for a in review.get('aois',[]):
        if not re.fullmatch(r'[A-Za-z0-9_-]+',a.get('id','')) or a['id'] in ids or not a.get('label','').strip():raise ValueError('Each region needs a unique ID and a label')
        ids.add(a['id'])
        if a.get('coordinate_space')!='recorded_frame_pixels':raise ValueError('Region coordinates must be recorded-frame pixels')
        if a['segment_id'] not in segments:raise ValueError('A region references a deleted view; delete or move that region first')
        x,y,w,h=a['rect'];start,end=a['valid_interval'];s=segments[a['segment_id']]
        if not all(math.isfinite(v) for v in (x,y,w,h,start,end)) or x<0 or y<0 or min(w,h)<=0:
            raise ValueError('Region bounds must be finite and positive')
        if not s['start']<=start<end<=s['end']:raise ValueError('Region time range must be inside its view interval')
        if frame_size and (x+w>frame_size[0] or y+h>frame_size[1]):raise ValueError('Region lies outside the video frame')
        ref=a.get('reference_frame')
        if a.get('layout_confirmed') and (not ref or not start<=ref['seconds']<end):raise ValueError('Confirm a representative frame inside the region time range before enabling its metrics')
        if ref and frame_size and list(ref['size'])!=list(frame_size):raise ValueError('Region reference image has a different frame size')
    for c in review.get('mapping_corrections',[]):
        if c.get('segment_id') not in segments:raise ValueError('A correction references a missing view')
        a,b=c['interval'];s=segments[c['segment_id']]
        if not s['start']<=a<b<=s['end'] or not all(math.isfinite(v) for v in c['matrix']):raise ValueError('Correction range or geometry is invalid')
    if review.get('aoi_overlap_policy','ambiguous') not in ('ambiguous','priority'):raise ValueError('Unknown region overlap policy')


def split_view(review,segment_id,seconds):
    result=copy.deepcopy(review);s=next(s for s in result['segments'] if s['id']==segment_id)
    if not s['start']<seconds<s['end']:raise ValueError('Move the playhead inside the selected view before splitting')
    right=copy.deepcopy(s);right.update(id=uuid.uuid4().hex[:12],start=seconds)
    s['end']=seconds
    s['reference_seconds']=min(s.get('reference_seconds',s['start']),seconds-1e-6)
    right['reference_seconds']=max(seconds,right.get('reference_seconds',seconds))
    result['segments'].append(right)
    regions=[]
    for a in result.get('aois',[]):
        if a['segment_id']!=segment_id:regions.append(a);continue
        for part in (s,right):
            lo=max(a['valid_interval'][0],part['start']);hi=min(a['valid_interval'][1],part['end'])
            if lo>=hi:continue
            item=copy.deepcopy(a);item['segment_id']=part['id'];item['valid_interval']=[lo,hi]
            if part is right:item['id']=uuid.uuid4().hex[:12]
            ref=item.get('reference_frame')
            if ref and not part['start']<=ref['seconds']<part['end']:
                item['original_reference_frame']=ref;item['reference_frame']=None;item['layout_confirmed']=False
            item['updated_utc']=stamp();regions.append(item)
    result['aois']=regions
    # Interval-bound corrections need explicit re-approval after a structural edit.
    for correction in result.get('mapping_corrections',[]):
        if correction.get('segment_id')==segment_id:
            correction['confirmed']=False;correction['interval']=[s['start'],s['end']]
    return result


def merge_views(review,ids,confirmed=False):
    if not confirmed:raise ValueError('Confirm that these adjacent intervals describe a compatible visual state')
    result=copy.deepcopy(review);chosen=sorted([s for s in result['segments'] if s['id'] in ids],key=lambda s:s['start'])
    if len(chosen)<2 or any(abs(a['end']-b['start'])>1e-6 for a,b in zip(chosen,chosen[1:])):
        raise ValueError('Select two or more adjacent intervals; unknown gaps cannot be silently merged')
    merged=copy.deepcopy(chosen[0]);merged['end']=chosen[-1]['end'];merged['stable']=False
    result['segments']=[s for s in result['segments'] if s['id'] not in ids]+[merged]
    for a in result.get('aois',[]):
        if a['segment_id'] in ids:
            a['segment_id']=merged['id'];a['layout_confirmed']=False;a['updated_utc']=stamp()
    for c in result.get('mapping_corrections',[]):
        if c.get('segment_id') in ids:c['confirmed']=False;c['segment_id']=merged['id']
    return result


def delete_view(review,segment_id):
    result=copy.deepcopy(review)
    result['segments']=[s for s in result['segments'] if s['id']!=segment_id]
    result['aois']=[a for a in result.get('aois',[]) if a['segment_id']!=segment_id]
    result['mapping_corrections']=[c for c in result.get('mapping_corrections',[]) if c.get('segment_id')!=segment_id]
    return result
