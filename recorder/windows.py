"""Windows physical-pixel geometry and target hit-testing. No MapGen access."""
import ctypes
from ctypes import wintypes
from .targeting import title_digest


class GUIINFO(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('flags', wintypes.DWORD),
                ('hwndActive', wintypes.HWND), ('hwndFocus', wintypes.HWND),
                ('hwndCapture', wintypes.HWND), ('hwndMenuOwner', wintypes.HWND),
                ('hwndMoveSize', wintypes.HWND), ('hwndCaret', wintypes.HWND),
                ('rcCaret', wintypes.RECT)]


def api():
    user = ctypes.windll.user32
    user.GetForegroundWindow.restype = wintypes.HWND
    for name in ('GetWindowRect', 'GetClientRect'):
        getattr(user, name).argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user.GetAncestor.restype = wintypes.HWND
    user.WindowFromPoint.argtypes = [wintypes.POINT]
    user.WindowFromPoint.restype = wintypes.HWND
    for name in ('IsWindowVisible', 'IsIconic', 'IsZoomed', 'IsWindow', 'GetDpiForWindow'):
        getattr(user, name).argtypes = [wintypes.HWND]
    user.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(GUIINFO)]
    user.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user.GetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user.GetAwarenessFromDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    return user


def enable_dpi_awareness():
    user = api()
    if not user.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
        if user.GetAwarenessFromDpiAwarenessContext(user.GetThreadDpiAwarenessContext()) != 2:
            raise RuntimeError('Per-monitor DPI awareness could not be enabled')


def _rect(user, hwnd, client=False):
    rect = wintypes.RECT()
    getter = user.GetClientRect if client else user.GetWindowRect
    if not getter(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError()
    origin = wintypes.POINT(rect.left, rect.top)
    if client and not user.ClientToScreen(hwnd, ctypes.byref(origin)):
        raise ctypes.WinError()
    return [origin.x, origin.y, rect.right-rect.left, rect.bottom-rect.top]


def _identity(user, hwnd):
    pid = wintypes.DWORD()
    user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)]*4
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
    if not handle:
        raise ctypes.WinError()
    try:
        created, exited, ktime, utime = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *[ctypes.byref(t) for t in (created, exited, ktime, utime)]):
            raise ctypes.WinError()
        path = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(path))
        if not kernel.QueryFullProcessImageNameW(handle, 0, path, ctypes.byref(size)):
            raise ctypes.WinError()
        name = ctypes.create_unicode_buffer(256)
        if not user.GetClassNameW(hwnd, name, len(name)):
            raise ctypes.WinError()
        return {'hwnd': int(hwnd), 'pid': pid.value,
                'process_started': (created.dwHighDateTime << 32) | created.dwLowDateTime,
                'class_name': name.value, 'executable': path.value.rsplit('\\', 1)[-1].lower()}
    finally:
        kernel.CloseHandle(handle)


def _title(user, hwnd):
    title = ctypes.create_unicode_buffer(2048)
    user.GetWindowTextW(hwnd, title, len(title))
    return title.value


def chrome_windows():
    user = api()
    windows = []
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if user.IsWindowVisible(hwnd):
            try:
                identity = _identity(user, hwnd)
                if identity['executable'] == 'chrome.exe' and identity['class_name'] == 'Chrome_WidgetWin_1':
                    windows.append({'identity': identity, 'title': _title(user, hwnd)})
            except OSError:
                pass  # Inaccessible processes are never offered as valid targets.
        return True
    callback = callback_type(visit)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    if not user.EnumWindows(callback, 0):
        raise ctypes.WinError()
    return windows


def geometry():
    user = api()
    hwnd = user.GetForegroundWindow()
    return {'desktop_rect': [user.GetSystemMetrics(i) for i in (76, 77, 78, 79)],
            'foreground': {'hwnd': int(hwnd or 0), 'rect': _rect(user, hwnd) if hwnd else None}}


def _is_cloaked(hwnd):
    value = wintypes.DWORD()
    dwm = ctypes.windll.dwmapi
    dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    if dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(value), ctypes.sizeof(value)) != 0:
        raise RuntimeError('Window visibility state unavailable')
    return bool(value.value)


def _possible_occluders(user, hwnd, x, y):
    """Conservative Z-order bounds check for overlays ignored by WindowFromPoint.

    Bounding boxes cannot prove visual occlusion for shaped/transparent windows;
    callers label these uncertain rather than assuming the target is unobscured.
    """
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found, blockers = [], []
    def visit(other, _):
        if int(other) == int(hwnd):
            found.append(True)
            return False
        if user.IsWindowVisible(other) and not user.IsIconic(other):
            try:
                from .targeting import contains
                if contains(_rect(user, other), x, y) and not _is_cloaked(other):
                    blockers.append(int(other))
            except (OSError, RuntimeError):
                blockers.append(int(other))
        return True
    callback = callback_type(visit)
    user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user.EnumWindows(callback, 0)  # callback intentionally terminates on target
    if not found:
        raise RuntimeError('Target missing from window Z-order')
    return blockers


def target_snapshot(hwnd, x, y):
    """Snapshot per event; failures become uncertain, never drop raw input."""
    user = api()
    try:
        identity = _identity(user, hwnd)
        client = _rect(user, hwnd, client=True)
        title = title_digest(_title(user, hwnd))
        dpi = user.GetDpiForWindow(hwnd)
        if not dpi:
            raise RuntimeError('Target DPI unavailable')
        hit = user.WindowFromPoint(wintypes.POINT(int(x), int(y)))
        hit_root = user.GetAncestor(hit, 2) if hit else None  # GA_ROOT, not ROOTOWNER
        info = GUIINFO()
        info.cbSize = ctypes.sizeof(info)
        capture = None
        if user.GetGUIThreadInfo(0, ctypes.byref(info)):
            capture = int(user.GetAncestor(info.hwndCapture, 2) or 0) if info.hwndCapture else 0
        cloaked = _is_cloaked(hwnd)
        return {'identity': identity, 'client_rect': client, 'window_rect': _rect(user, hwnd),
                'dpi': dpi, 'title_digest': title, 'hit_hwnd': int(hit or 0),
                'possible_occluders': _possible_occluders(user, hwnd, x, y),
                'hit_root': int(hit_root or 0), 'capture_root': capture,
                'foreground_root': int(user.GetAncestor(user.GetForegroundWindow(), 2) or 0),
                'visible': bool(user.IsWindowVisible(hwnd)), 'minimized': bool(user.IsIconic(hwnd)),
                'cloaked': cloaked, 'maximized': bool(user.IsZoomed(hwnd)),
                'stable': (identity == _identity(user, hwnd) and client == _rect(user, hwnd, client=True)
                           and title == title_digest(_title(user, hwnd)) and dpi == user.GetDpiForWindow(hwnd))}
    except (OSError, RuntimeError) as exc:
        return {'error': str(exc)}
