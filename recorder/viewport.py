"""Read-only Windows UI Automation webpage viewport discovery (physical screen pixels)."""
from .targeting import contains


def choose_document(documents, client):
    """Only accept a unique enclosing, visible UIA Document inside the client area."""
    valid = []
    for doc in documents:
        rect = doc['rect']
        x,y,w,h = rect
        if not doc.get('offscreen') and w > 0 and h > 0 and contains(client,x,y) and contains(client,x+w-1,y+h-1):
            if rect not in [item['rect'] for item in valid]:
                valid.append(doc)
    enclosing = [d for d in valid if all(
        contains(d['rect'],o['rect'][0],o['rect'][1]) and
        contains(d['rect'],o['rect'][0]+o['rect'][2]-1,o['rect'][1]+o['rect'][3]-1) for o in valid)]
    if len(enclosing) != 1:
        raise ValueError('UI Automation did not expose one unambiguous webpage Document. Enable Chrome accessibility or use the confirmed manual fallback.')
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
        return dict(chosen,method='windows_uia_document',coordinate_system='physical_desktop_pixels',
                    status='computed_not_experimentally_verified',
                    zoom_monitoring='available' if chosen['zoom_percent'] is not None else 'unavailable_keep_browser_zoom_fixed')
    finally:
        comtypes.CoUninitialize()
