"""Read-only Windows UI Automation webpage viewport discovery (physical screen pixels)."""
import math
from .targeting import contains


class ViewportDetectionError(ValueError):
    def __init__(self,message,evidence):
        super().__init__(message);self.evidence=evidence


def viewport_sanity(rect, client):
    """Conservative geometry policy for a normal Chrome webpage, not proof of DOM bounds.

    Ratios avoid a fixed toolbar height at different DPI. Unusual layouts should
    use the visual fallback, not relax the automatic policy silently.
    """
    if len(rect)!=4 or len(client)!=4 or not all(math.isfinite(v) for v in (*rect,*client)):
        return False,'invalid_geometry'
    x,y,w,h=rect;cx,cy,cw,ch=client
    if min(w,h,cw,ch)<=0 or not (contains(client,x,y) and contains(client,x+w-1,y+h-1)):
        return False,'clipped_or_outside_chrome'
    ratios={'width':w/cw,'height':h/ch,'area':w*h/(cw*ch),'top':(y-cy)/ch,
            'left':(x-cx)/cw,'bottom':(cy+ch-y-h)/ch}
    if ratios['width']<.55 or ratios['height']<.45 or ratios['area']<.35:
        return False,'implausibly_small_webpage'
    if ratios['top']>.40 or ratios['left']>.25 or ratios['bottom']>.25:
        return False,'inconsistent_webpage_position'
    return True,ratios


def choose_document(documents, client):
    valid=[];rejected=[]
    for doc in documents:
        ok,evidence=viewport_sanity(doc['rect'],client)
        if doc.get('offscreen') or not ok:
            rejected.append('offscreen' if doc.get('offscreen') else evidence);continue
        if doc['rect'] not in [item['rect'] for item in valid]:
            valid.append(dict(doc,sanity={'policy':'chrome_geometry_v2','ratios':evidence,
                                         'status':'plausible_not_experimentally_verified'}))
    enclosing=[d for d in valid if all(contains(d['rect'],o['rect'][0],o['rect'][1]) and
        contains(d['rect'],o['rect'][0]+o['rect'][2]-1,o['rect'][1]+o['rect'][3]-1) for o in valid)]
    if len(enclosing)!=1:
        raise ViewportDetectionError('Recorder could not confidently find the webpage area ('+', '.join(sorted(set(rejected)) or ['ambiguous areas'])+
                         '). Use Mark webpage area to confirm it on a screenshot. Recording evidence can still be preserved.',
                                     {'policy':'chrome_geometry_v2','client_rect':client,'candidates':documents,'rejection_reasons':rejected})
    return enclosing[0]


def read_viewport(hwnd, client):
    # COM initialization belongs to the calling worker, not the Tk thread.
    import comtypes
    import comtypes.client
    comtypes.CoInitialize()
    try:
        comtypes.client.GetModule('UIAutomationCore.dll')
        from comtypes.gen import UIAutomationClient as UIA
        automation = comtypes.client.CreateObject('{FF48DBA4-60EF-4201-AA87-54103EEF594E}',interface=UIA.IUIAutomation)
        root = automation.ElementFromHandle(hwnd)
        items = root.FindAll(4,automation.CreatePropertyCondition(30003,50030))
        docs = []
        for i in range(items.Length):
            node = items.GetElement(i)
            r = node.CurrentBoundingRectangle
            # Do not collect Document names, DOM contents, URLs or accessibility text.
            doc = {'rect':[int(r.left),int(r.top),int(r.right-r.left),int(r.bottom-r.top)],
                   'offscreen':bool(node.CurrentIsOffscreen), 'zoom_percent':None}
            try:
                pattern = node.GetCurrentPattern(10028).QueryInterface(UIA.IUIAutomationTransformPattern2)
                doc['zoom_percent'] = float(pattern.CurrentZoomLevel)
            except Exception:
                pass  # UIA providers often do not implement TransformPattern2.
            docs.append(doc)
        chosen = choose_document(docs,client)
        user=__import__('ctypes').windll.user32
        desktop=[user.GetSystemMetrics(i) for i in (76,77,78,79)]
        r=chosen['rect']
        if not (contains(desktop,r[0],r[1]) and contains(desktop,r[0]+r[2]-1,r[1]+r[3]-1)):
            raise ViewportDetectionError('The webpage appears partly offscreen. Bring Chrome fully onto the display or mark its visible area manually.',
                                         {'candidates':docs,'client_rect':client,'virtual_desktop':desktop,'chosen':chosen})
        # Read the candidate again; a transient clipped Document must not become calibration.
        again=[]
        second=root.FindAll(4,automation.CreatePropertyCondition(30003,50030))
        for i in range(second.Length):
            node=second.GetElement(i);r=node.CurrentBoundingRectangle
            again.append({'rect':[int(r.left),int(r.top),int(r.right-r.left),int(r.bottom-r.top)],'offscreen':bool(node.CurrentIsOffscreen)})
        corroborated=choose_document(again,client)
        if chosen['rect']!=corroborated['rect']:
            raise ViewportDetectionError('The webpage area changed during detection. Wait for Chrome to settle and retry.',
                                         {'candidates':docs,'second_candidates':again,'client_rect':client})
        chosen['sanity']['corroboration']='two_matching_UIA_reads_and_virtual_desktop_containment'
        return dict(chosen,method='windows_uia_document',coordinate_system='physical_desktop_pixels',
                    status='computed_not_experimentally_verified',
                    zoom_monitoring='available' if chosen['zoom_percent'] is not None else 'unavailable_keep_browser_zoom_fixed')
    finally:
        comtypes.CoUninitialize()
