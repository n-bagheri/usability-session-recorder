"""Windows physical-coordinate geometry. No application integration."""
import ctypes
from ctypes import wintypes


def api():
    user = ctypes.windll.user32
    user.GetForegroundWindow.restype = wintypes.HWND
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    user.GetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user.GetAwarenessFromDpiAwarenessContext.argtypes = [ctypes.c_void_p]
    return user


def enable_dpi_awareness():
    # Must execute before creating Tk windows or starting pynput.
    user = api()
    if not user.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
        # An already configured process is acceptable; check actual thread context.
        if not user.GetAwarenessFromDpiAwarenessContext(user.GetThreadDpiAwarenessContext()) == 2:
            raise RuntimeError('Per-monitor DPI awareness could not be enabled')


def geometry():
    user = api()
    desktop = [user.GetSystemMetrics(i) for i in (76, 77, 78, 79)]
    hwnd = user.GetForegroundWindow()
    rect = wintypes.RECT()
    if not user.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError()
    return {'desktop_rect': desktop, 'foreground': {
        'hwnd': int(hwnd), 'rect': [rect.left, rect.top, rect.right-rect.left, rect.bottom-rect.top]}}
