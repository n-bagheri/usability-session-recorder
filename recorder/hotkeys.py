"""Opt-in Windows RegisterHotKey, no keyboard logging. Conflicts are reported."""
import threading


def parse_hotkey(text):
    parts=text.lower().split('+')
    modifiers={'ctrl':2,'alt':1,'shift':4}
    if len(parts)!=4 or set(parts[:-1])!=set(modifiers) or not parts[-1].startswith('f'):
        raise ValueError('Use an intentional Ctrl+Alt+Shift+F1..F12 combination; ordinary typing shortcuts are not allowed')
    number=int(parts[-1][1:])
    if not 1<=number<=12:raise ValueError('Function key must be F1..F12')
    return 0x4000|7,0x70+number-1  # MOD_NOREPEAT


class GlobalShortcuts:
    def __init__(self,bindings,callback):
        if len(set(bindings.values()))!=len(bindings):raise ValueError('Shortcut combinations must be distinct')
        self.bindings={k:parse_hotkey(v) for k,v in bindings.items()};self.callback=callback
        self.stop_event=threading.Event();self.ready=threading.Event();self.error=None

    def start(self):
        import ctypes
        from ctypes import wintypes
        def run():
            user=ctypes.windll.user32
            registered=[]
            try:
                for name,(mods,key) in self.bindings.items():
                    if not user.RegisterHotKey(None,name,mods,key):
                        raise RuntimeError('Windows reports a shortcut conflict/unavailable combination; choose another combination or disable shortcuts')
                    registered.append(name)
                self.ready.set()
                message=wintypes.MSG()
                while not self.stop_event.wait(.03):
                    while user.PeekMessageW(ctypes.byref(message),None,0,0,1):
                        if message.message==0x0312:self.callback(int(message.wParam))
            except Exception as exc:self.error=str(exc);self.ready.set()
            finally:
                for name in registered:user.UnregisterHotKey(None,name)
        self.thread=threading.Thread(target=run,daemon=True);self.thread.start()
        if not self.ready.wait(3):raise RuntimeError('Shortcut registration timed out')
        if self.error:raise RuntimeError(self.error)

    def stop(self):
        self.stop_event.set()
        if hasattr(self,'thread'):self.thread.join(timeout=1)
