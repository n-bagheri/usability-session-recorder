"""Explicit visual-region assignment. No DOM identity or inferred intentional clicks."""
from collections import Counter
import json
from .targeting import contains
from .review import segment_at,paired_clicks


def region_analysis(data,max_gap=.25):
    review=data.review;rows=[];stats={};blocked={}
    suggestions=getattr(data,'visual_suggestions',{})
    if getattr(data,'folder',None) and (data.folder/'review_suggestions.json').exists():
        suggestions=json.loads((data.folder/'review_suggestions.json').read_text(encoding='utf-8'))
    for a in review.get('aois',[]):
        s=next(s for s in review['segments'] if s['id']==a['segment_id'])
        ref=a.get('reference_frame')
        reason=None if data.timing_available else 'timing_unavailable'
        if not a.get('layout_confirmed') or not s.get('stable'):reason='layout_not_confirmed_stable'
        if not ref or ref.get('video_fingerprint')!=data.video.fingerprint:reason='reference_frame_missing_or_changed'
        applicable=data.events_between(*a['valid_interval'])
        if any(e['type']=='scroll' and e.get('target',{}).get('classification')=='inside' for e in applicable):reason='scroll_in_region_interval_define_separate_states'
        ids={data.mapping(e)['id'] for e in applicable if data.mapping(e) and data.predict(e) is not None}
        if len(ids)>1:reason='mapping_changed_in_region_interval'
        zoom={((e.get('target_observation') or {}).get('viewport') or {}).get('zoom_percent') for e in applicable}
        if len(zoom)>1:reason='zoom_changed_in_region_interval'
        if any(a['valid_interval'][0]<change['seconds']<a['valid_interval'][1] for change in suggestions.get('suggestions',[])) and s.get('visual_suggestion_review')!='reviewed_no_spatial_change':reason='visual_change_requires_layout_review'
        blocked[a['id']]=reason
        stats[a['id']]={'id':a['id'],'semantic_id':a.get('semantic_id',a['id']),'label':a['label'],'segment_id':a['segment_id'],
                        'button_presses':0,'button_releases':0,'movement_samples':0,'complete_button_pairs_from_presses':0,
                        'bounded_cursor_occupancy_seconds':0.0,'first_interaction_seconds':None,'event_ids':[],
                        'annotation':a,'press_timeline':[],'first_interaction_from_view_seconds':None,
                        'validity':'needs_review' if reason else 'researcher_confirmed_not_independently_verified','warning':reason}
    assignment={};reasons=Counter()
    for e in data.events:
        if e['type'] not in ('move','click','scroll'):continue
        t=data.time(e);point=data.predict(e)
        s,kind=segment_at(t,review) if t is not None else (None,'timing_unavailable')
        candidates=[];rejected=[]
        if kind=='administrative':reason='outside_participant_interval'
        elif t is None:reason='timing_unavailable'
        elif e.get('target',{}).get('classification')!='inside':reason='outside_or_uncertain_target'
        elif point is None:reason='mapping_unavailable_or_clipped'
        elif s is None:reason='unclassified_view'
        else:
            for a in review.get('aois',[]):
                if a['segment_id']==s['id'] and a['valid_interval'][0]<=t<a['valid_interval'][1] and contains(a['rect'],*point):
                    (rejected if blocked[a['id']] else candidates).append(a)
            reason='outside_labeled_regions' if not rejected else 'region_validity_uncertain'
        chosen=None
        if len(candidates)==1:chosen=candidates[0]
        elif len(candidates)>1:
            if review.get('aoi_overlap_policy','ambiguous')=='priority':chosen=min(candidates,key=lambda a:(a.get('priority',0),a['id']))
            else:reason='overlapping_regions_unassigned'
        if chosen:
            reason='researcher_region_assignment';v=stats[chosen['id']];v['event_ids'].append(e['event_id'])
            if v['first_interaction_seconds'] is None:v['first_interaction_seconds']=t;v['first_interaction_from_view_seconds']=t-s['start']
            if e['type']=='move':v['movement_samples']+=1
            elif e['type']=='click':
                v['button_presses' if e.get('pressed') else 'button_releases']+=1
                if e.get('pressed'):v['press_timeline'].append({'event_id':e['event_id'],'video_seconds':t,'view_offset_seconds':t-s['start']})
        assignment[e['event_id']]=chosen['id'] if chosen else None;reasons[reason]+=1
        rows.append({'event_id':e['event_id'],'raw_line':e['raw_line'],'video_seconds':t,'type':e['type'],'pressed':e.get('pressed'),
                     'segment_id':s['id'] if s else None,'aoi_id':chosen['id'] if chosen else None,
                     'aoi_label':chosen['label'] if chosen else None,'reason':reason,
                     'candidate_aoi_ids':[a['id'] for a in candidates], 'invalid_candidate_ids':[a['id'] for a in rejected],
                     'frame_x':point[0] if point else None,'frame_y':point[1] if point else None})
    pairs,unmatched=paired_clicks(data.events)
    for down,up in pairs:
        region=assignment.get(down['event_id'])
        if region:stats[region]['complete_button_pairs_from_presses']+=1
    covered=0.0;unsupported=0.0
    for before,after in zip(data.events,data.events[1:]):
        a=assignment.get(before['event_id']);b=assignment.get(after['event_id'])
        t1,t2=data.time(before),data.time(after)
        if not a or a!=b or t1 is None or t2 is None:continue
        gap=t2-t1
        if 0<gap<=max_gap:
            stats[a]['bounded_cursor_occupancy_seconds']+=gap;covered+=gap
        elif gap>max_gap:unsupported+=gap
    return {'regions':list(stats.values()),'events':rows,'assignment_reasons':dict(reasons),
            'observed_cursor_coverage_seconds':covered,'long_same_region_gaps_not_extrapolated_seconds':unsupported,
            'overlap_policy':review.get('aoi_overlap_policy','ambiguous'),
            'definitions':{'assignment':'mapped position at each raw event; press is counted once, release separately',
                           'complete_button_pair':'a recorded down followed by matching button up; may represent dragging, not necessarily an intentional click',
                           'occupancy':f'partial estimate only: consecutive raw events assigned to the same region, 0 < gap <= {max_gap}s; longer silence is unknown',
                           'meaning':'researcher-defined visual region, not DOM identity, gaze or attention'},
            'quality':data.qa()['spatial']['status']+' spatial; '+data.qa()['temporal']['status']+' timing'}
