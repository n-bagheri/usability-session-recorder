"""OBS Window Capture association and explicitly supported scene transforms."""
import hashlib
import json
import math
from .targeting import contains


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()[:20]


def _unescape(value):
    return value.replace('#3A',':').replace('#22','"').replace('#23','#')


def associate(settings, selected, windows):
    parts = settings.get('window','').split(':')
    if len(parts) != 3:
        raise ValueError('OBS source has no usable window identity')
    title, cls, exe = map(_unescape,parts)
    matches = [w for w in windows if w['identity']['class_name'] == cls and w['identity']['executable'].lower() == exe.lower()]
    exact = [w for w in matches if w['title'] == title]
    candidates = exact if exact else matches
    if len(candidates) != 1 or candidates[0]['identity'] != selected['identity']:
        raise ValueError('OBS Window Capture association is ambiguous or targets another Chrome window')
    return 'unique_title_class_executable' if exact else 'unique_class_executable_title_changed'


def _anchor(flags):
    return (0 if flags & 1 else 1 if flags & 2 else .5,
            0 if flags & 4 else 1 if flags & 8 else .5)


def compute_mapping(capture_rect, viewport_rect, transform, canvas_size, output_size):
    """Axis-aligned NONE/INNER/STRETCH bounds; reject every unsupported transform.

    Coordinates are continuous physical pixel edges, not CSS pixels. The final
    matrix includes source cropping, item/bounds alignment and OBS output scaling.
    """
    t = transform
    if abs(t.get('rotation',0)) > 1e-6 or t.get('scaleX',1) <= 0 or t.get('scaleY',1) <= 0:
        raise ValueError('Rotated or flipped OBS sources are unsupported; mapping invalid')
    if t.get('cropToBounds',False):
        raise ValueError('OBS crop-to-bounds is unsupported')
    if [t['sourceWidth'],t['sourceHeight']] != capture_rect[2:]:
        raise ValueError('OBS source dimensions do not match the measured physical capture rectangle')
    l,r,top,b = [t.get(k,0) for k in ('cropLeft','cropRight','cropTop','cropBottom')]
    if min(l,r,top,b) < 0:
        raise ValueError('Negative source crop')
    w,h = capture_rect[2]-l-r,capture_rect[3]-top-b
    if min(w,h,*canvas_size,*output_size) <= 0:
        raise ValueError('Invalid OBS source/canvas/output dimensions')
    sx,sy = t.get('scaleX',1),t.get('scaleY',1)
    boxw,boxh = w*sx,h*sy
    offx = offy = 0
    bounds = t.get('boundsType','OBS_BOUNDS_NONE')
    if bounds != 'OBS_BOUNDS_NONE':
        bw,bh = t.get('boundsWidth',0),t.get('boundsHeight',0)
        if bw <= 0 or bh <= 0:
            raise ValueError('Invalid bounds dimensions')
        if bounds == 'OBS_BOUNDS_SCALE_INNER':
            factor = min(bw/boxw,bh/boxh)
            sx *= factor
            sy *= factor
        elif bounds == 'OBS_BOUNDS_STRETCH':
            sx,sy = bw/w,bh/h
        else:
            raise ValueError('Unsupported OBS bounds mode: '+bounds)
        ax,ay = _anchor(t.get('boundsAlignment',0))
        offx,offy = (bw-w*sx)*ax,(bh-h*sy)*ay
        boxw,boxh = bw,bh
    ax,ay = _anchor(t.get('alignment',5))
    ox = t['positionX']-boxw*ax+offx-l*sx
    oy = t['positionY']-boxh*ay+offy-top*sy
    vx,vy,vw,vh = viewport_rect
    cx,cy,cw,ch = capture_rect
    if not (contains(capture_rect,vx,vy) and contains(capture_rect,vx+vw-1,vy+vh-1)):
        raise ValueError('Webpage viewport lies outside the OBS capture rectangle')
    outx,outy = output_size[0]/canvas_size[0],output_size[1]/canvas_size[1]
    matrix = [sx*outx,0,(ox+(vx-cx)*sx)*outx,0,sy*outy,(oy+(vy-cy)*sy)*outy]
    # Visible part of viewport after source cropping. Frame clipping is checked per point.
    clip = [max(0,cx+l-vx),max(0,cy+top-vy),min(vw,cx+cw-r-vx),min(vh,cy+ch-b-vy)]
    if clip[2]<=clip[0] or clip[3]<=clip[1]:
        raise ValueError('OBS crop removes the entire webpage viewport')
    canvas_clipped=not (contains([0,0,*output_size],matrix[2],matrix[5]) and
                        contains([0,0,*output_size],matrix[2]+matrix[0]*vw-1,matrix[5]+matrix[4]*vh-1))
    result = {'canvas_clipped':canvas_clipped,'clipped':clip != [0,0,vw,vh] or canvas_clipped, 'matrix':matrix,'content_size':[vw,vh],'output_size':list(output_size),
              'source_clip_ltrb':clip,'capture_rect':capture_rect,'viewport_rect':viewport_rect,
              'scene_transform':t,'canvas_size':list(canvas_size),
              'status':'computed','experimentally_verified':False}
    if not all(math.isfinite(n) for n in matrix):
        raise ValueError('Non-finite transform')
    result['id'] = fingerprint(result)
    return result


def project(mapping, local):
    if mapping.get('status') != 'computed':
        raise ValueError('Capture mapping is invalid')
    x,y = local
    l,t,r,b = mapping['source_clip_ltrb']
    if not (l <= x < r and t <= y < b):
        return None
    a,b,c,d,e,f = mapping['matrix']
    px,py = a*x+b*y+c,d*x+e*y+f
    if not contains([0,0,*mapping['output_size']],px,py):
        return None
    return [px,py]


def profile_value(obs,category,name):
    parameter=obs.get_profile_parameter(category,name)
    value=parameter.parameter_value
    if value is None or value=='':value=getattr(parameter,'default_parameter_value',None)
    if value is None or value=='':raise ValueError(f'OBS did not expose a value/default for {category}.{name}; output calibration is unverified')
    return str(value)


def read_obs_capture(obs, selected, windows, snapshot, viewport):
    scene = obs.get_current_program_scene().current_program_scene_name
    items = obs.get_scene_item_list(scene).scene_items
    candidates = []
    for item in items:
        if not item.get('sceneItemEnabled') or item.get('isGroup'):
            continue
        try:
            data = obs.get_input_settings(item['sourceName'])
        except Exception:
            continue
        if data.input_kind != 'window_capture':
            continue
        try:
            evidence = associate(data.input_settings,selected,windows)
        except ValueError:
            continue
        candidates.append((item,data.input_settings,evidence))
    if len(candidates) != 1:
        raise ValueError('Need exactly one visible, ungrouped OBS Window Capture associated with the selected Chrome window')
    item,settings,evidence = candidates[0]
    t = obs.get_scene_item_transform(scene,item['sceneItemId']).scene_item_transform
    source_size = [t['sourceWidth'],t['sourceHeight']]
    if settings.get('client_area',True):
        capture = snapshot['client_rect']
        if capture[2:] != source_size:
            raise ValueError('OBS client capture dimensions are not the measured client dimensions')
    else:
        choices = [r for r in (snapshot.get('frame_rect'),snapshot['window_rect']) if r and r[2:] == source_size]
        unique = {tuple(r) for r in choices}
        if len(unique) != 1:
            raise ValueError('Cannot establish OBS outer-window capture origin without ambiguity')
        capture = list(unique.pop())
    for other in items:
        if other.get('sceneItemEnabled') and other['sceneItemIndex'] > item['sceneItemIndex']:
            ot = obs.get_scene_item_transform(scene,other['sceneItemId']).scene_item_transform
            if ot.get('sourceWidth',0) and ot.get('sourceHeight',0):
                raise ValueError('Additional visible video source above target; disable overlays for calibrated capture')
    # Separate recording rescale/custom FFmpeg outputs are not described by GetVideoSettings.
    mode = profile_value(obs,'Output','Mode')
    if mode.lower() == 'advanced':
        rescale = profile_value(obs,'AdvOut','RecRescale')
        rec_type = profile_value(obs,'AdvOut','RecType')
        if str(rescale).lower() in ('true','1') or rec_type.lower() != 'standard':
            raise ValueError('Advanced recording rescale/custom output is unsupported; disable it for calibrated capture')
    elif mode.lower() != 'simple':
        raise ValueError('Unknown OBS recording output mode')
    filters = obs.get_source_filter_list(item['sourceName']).filters
    if any(f.get('filterEnabled',True) for f in filters):
        raise ValueError('Source filters may alter geometry; disable them for calibrated capture')
    video = obs.get_video_settings()
    result = compute_mapping(capture,viewport['rect'],t,
                             [video.base_width,video.base_height],[video.output_width,video.output_height])
    result.update(scene=scene,source_name=item['sourceName'],scene_item_id=item['sceneItemId'],
                  source_settings=settings,association=evidence,output_profile_mode=mode,
                  obs_fps=[getattr(video,'fps_numerator',None),getattr(video,'fps_denominator',None)])
    result['id'] = fingerprint(result)
    return result
