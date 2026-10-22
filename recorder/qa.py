"""Independent reference measurements. Computed mappings are never self-verifying."""
import math
import statistics
from .core import video_seconds


def event_seconds(event, sync, review=None):
    base = video_seconds(event['monotonic_ns'],sync['origin_ns'],sync.get('manual_correction_ms',0))
    correction = (review or {}).get('time_correction',{})
    return base + correction.get('offset_seconds',0) + base*correction.get('drift_ppm',0)/1e6


def temporal_report(measurements, duration, fps=30):
    threshold = 2000/fps  # Two frames, 66.7ms at 30FPS; target, never an unstated guarantee.
    result = {'status':'unverified','target_max_error_ms':threshold,
              'rationale':'Two recorded frames allow onset selection and frame quantization; not frame accurate',
              'measurements':measurements,'clock_model':'Python perf_counter_ns -> OBS duration estimate -> saved-video presentation timestamps'}
    if not measurements:
        return result
    x = [m['estimated_seconds'] for m in measurements]
    y = [m['observed_seconds']-m['estimated_seconds'] for m in measurements]
    offset = statistics.median(y)
    mean = statistics.mean(x)
    denominator = sum((t-mean)**2 for t in x)
    slope = sum((t-mean)*(v-statistics.mean(y)) for t,v in zip(x,y))/denominator if denominator else 0
    corrected = [abs((m.get('corrected_seconds',m['estimated_seconds']))-m['observed_seconds'])*1000 for m in measurements]
    coverage = (max(m['observed_seconds'] for m in measurements)-min(m['observed_seconds'] for m in measurements))/duration if duration else 0
    result.update(offset_ms=offset*1000,estimated_drift_ppm=slope*1e6,
                  drift_over_session_ms=slope*duration*1000,max_error_ms=max(corrected),coverage_fraction=coverage,
                  suggested_offset_seconds=offset,measurement_count=len(measurements),
                  onset_uncertainty_ms=max(m.get('uncertainty_ms',1000/fps) for m in measurements))
    qualified = (len(measurements)>=3 and coverage>=.5 and min(x)<=duration*.2 and max(x)>=duration*.8 and any(duration*.3<=t<=duration*.7 for t in x))
    result['status'] = ('measured_pass' if max(corrected)<=threshold and abs(slope*duration*1000)<=1000/fps else 'measured_fail') if qualified else 'insufficient_measurements'
    if qualified and result['onset_uncertainty_ms']>threshold:result['status']='uncertain_measurement_resolution'
    result['warning'] = 'Measurements are operator-identified visible actions; do not measure added overlays. Drift estimate is diagnostic, not automatically applied.'
    return result


def spatial_report(measurements, frame_size, expected_fingerprint):
    valid = [m for m in measurements if m.get('video_fingerprint')==expected_fingerprint]
    result = {'status':'computed','threshold_px':5,'measurements':valid,
              'rationale':'5 recorded pixels is a practical registration target allowing edge selection/rounding at 1080p; measure tighter criteria for small UI targets.'}
    if not valid:
        return result
    errors = [math.dist(m['predicted'],m['observed']) for m in valid]
    xs = [m['predicted'][0] for m in valid]
    ys = [m['predicted'][1] for m in valid]
    # Coverage must span the mapped viewport, supplied with each independent point.
    rect = valid[0].get('viewport_frame_rect',[0,0,*frame_size])
    l,t,w,h = rect
    regions = set()
    for m in valid:
        x,y = m['predicted']
        u,v = (x-l)/w,(y-t)/h
        if .3<=u<=.7 and .3<=v<=.7:
            regions.add('center')
        if u<=.2 and v<=.2: regions.add('tl')
        if u>=.8 and v<=.2: regions.add('tr')
        if u<=.2 and v>=.8: regions.add('bl')
        if u>=.8 and v>=.8: regions.add('br')
    # Never combine evidence for different calibration matrices in a "verified" claim.
    ids = {m['mapping_id'] for m in valid}
    qualified = len(valid)>=5 and len(regions)==5 and len(ids)==1 and len({m['event_id'] for m in valid})>=5
    result.update(max_error_px=max(errors),mean_error_px=statistics.mean(errors),regions=sorted(regions),
                  mapping_ids=sorted(ids),measurement_count=len(valid))
    result['status'] = ('experimentally_verified' if max(errors)<=5 else 'failed') if qualified else 'measured_insufficient_coverage'
    result['reference_selection_uncertainty_px']=max(m.get('reference_selection_uncertainty_px',0) for m in valid)
    result['verification_scope']='operator-annotated trial with stated uncertainty; not a guaranteed device-accuracy bound'
    if qualified and any(m.get('reference_selection_uncertainty_px',0)<=0 for m in valid):result['status']='uncertainty_not_documented'
    if qualified and result['reference_selection_uncertainty_px']>5:result['status']='insufficient_reference_resolution'
    return result
