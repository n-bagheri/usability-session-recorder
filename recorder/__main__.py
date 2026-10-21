"""Run with python -m recorder on Windows; OBS remains the recording engine."""
import sys


def main():
    if sys.platform!='win32':
        raise SystemExit('The recorder GUI requires Windows. Portable tests and saved-video analysis run on other platforms.')
    from .windows import enable_dpi_awareness
    enable_dpi_awareness()  # Before any Tk window or input hook.
    import tkinter as tk
    from .gui import RecorderUI
    root=tk.Tk();RecorderUI(root);root.mainloop()


if __name__=='__main__':main()
