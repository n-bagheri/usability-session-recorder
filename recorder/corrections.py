"""Researcher-defined desktop-to-recorded-frame registrations, separate from raw evidence."""
import math
import uuid
from .annotations import stamp
from .obs_geometry import fingerprint
from .targeting import classify,contains


def geometry_key(snapshot):
    return fingerprint(dict({k:snapshot.get(k) for k in ('identity','client_rect','dpi','monitor','maximized')},
                            raw_capture_mapping_id=(snapshot.get('capture_mapping') or {}).get('id'),
                            # Failed webpage detection still retains source transforms. They
                            # must not change underneath a retrospective registration.
                            observed_capture_mapping_id=((snapshot.get('automatic_calibration') or {}).get('mapping') or {}).get('id') if not snapshot.get('capture_mapping') else None,
                            raw_obs_evidence=(snapshot.get('automatic_calibration') or {}).get('obs_capture_evidence') if not snapshot.get('capture_mapping') else None))


def fit_registration(segment,anchors,page_rect,video_fingerprint):
    if len(anchors)<2:raise ValueError('Mark at least two widely separated clicks, one near each diagonal corner')
    if len({a['event_id'] for a in anchors})<2:raise ValueError('Use different recorded clicks for the reference anchors')
    if any(a['frame']['video_fingerprint']!=video_fingerprint or not segment['start']<=a['frame']['seconds']<segment['end'] for a in anchors):raise ValueError('Reference frames must come from this saved video and view interval')
    keys={a['geometry_key'] for a in anchors}
    if len(keys)!=1:raise ValueError('These clicks have different window geometry. Use separate view intervals.')
    def fit(axis):
        x=[a['desktop'][axis] for a in anchors];y=[a['observed'][axis] for a in anchors]
        if max(x)-min(x)<20:raise ValueError('Choose clicks separated in both horizontal and vertical directions')
        mx=sum(x)/len(x);my=sum(y)/len(y)
        slope=sum((v-mx)*(w-my) for v,w in zip(x,y))/sum((v-mx)**2 for v in x)
        if slope<=0 or not math.isfinite(slope):raise ValueError('The registration is flipped or invalid; check the reference clicks')
        return slope,my-slope*mx
    sx,tx=fit(0);sy,ty=fit(1)
    x,y,w,h=page_rect
    if not all(math.isfinite(v) for v in page_rect) or min(w,h)<=0:raise ValueError('Draw the visible webpage boundary on the recorded frame')
    viewport=[(x-tx)/sx,(y-ty)/sy,w/sx,h/sy]
    client=anchors[0]['client_rect']
    uncertainty=max(a.get('uncertainty_px',2) for a in anchors)
    allowance=uncertainty/min(sx,sy)
    expanded=[client[0]-allowance,client[1]-allowance,client[2]+2*allowance,client[3]+2*allowance]
    if not (contains(expanded,viewport[0],viewport[1]) and contains(expanded,viewport[0]+viewport[2]-1,viewport[1]+viewport[3]-1)):
        raise ValueError('The registration puts the webpage outside the recorded Chrome geometry; revise the anchors/boundary')
    errors=[math.dist([sx*a['desktop'][0]+tx,sy*a['desktop'][1]+ty],a['observed']) for a in anchors]
    return {'id':uuid.uuid4().hex[:12],'kind':'desktop_registration','segment_id':segment['id'],
            'interval':[segment['start'],segment['end']],'geometry_key':next(iter(keys)),
            'matrix':[sx,0,tx,0,sy,ty],'viewport_rect':viewport,'page_frame_rect':list(page_rect),
            'anchors':anchors,'fit_residual_max_px':max(errors),
            'reference_uncertainty_px':max(a.get('uncertainty_px',2) for a in anchors),
            'video_fingerprint':video_fingerprint,'created_utc':stamp(),'confirmed':True,
            'status':'researcher_adjusted_unverified','note':'Fitted anchors are calibration inputs, not independent validation evidence'}


def active_registration(event,seconds,review,video_fingerprint):
    if seconds is None:return None
    snapshot=event.get('target_observation') or {}
    matches=[c for c in review.get('mapping_corrections',[]) if c.get('confirmed') and
             c.get('video_fingerprint')==video_fingerprint and c['interval'][0]<=seconds<c['interval'][1] and
             c.get('geometry_key')==geometry_key(snapshot)]
    if len(matches)>1:raise ValueError('Mapping corrections overlap for this geometry; disable or narrow one correction')
    return matches[0] if matches else None


def corrected_target(event,correction,expected_identity=None):
    s=dict(event.get('target_observation') or {})
    # Historical hit-test, identity, visibility and delayed-observation facts still apply.
    s.pop('viewport_error',None);s['viewport']={'rect':correction['viewport_rect']}
    c={'identity':expected_identity or correction.get('target_identity') or s.get('identity',{}),'method':'automatic_uia_obs'}
    result=classify(event['x'],event['y'],c,s)
    if result['classification']=='inside':
        vx,vy,vw,vh=correction['viewport_rect'];sx=correction['matrix'][0];sy=correction['matrix'][4]
        edge=min((event['x']-vx)*sx,(vx+vw-event['x'])*sx,(event['y']-vy)*sy,(vy+vh-event['y'])*sy)
        if edge<=correction['reference_uncertainty_px']:result.update(classification='uncertain',reason='researcher_registration_boundary_uncertainty')
    result.update(correction_id=correction['id'],derivation='researcher_registration_unverified')
    return result


def corrected_mapping(correction,size):
    x,y,w,h=correction['viewport_rect'];a,b,c,d,e,f=correction['matrix']
    return {'status':'computed','matrix':[a,b,a*x+b*y+c,d,e,d*x+e*y+f],
            'content_size':[w,h],'output_size':size,'source_clip_ltrb':[0,0,w,h],
            'id':'review-'+correction['id'],'method':'researcher_registration_unverified'}
