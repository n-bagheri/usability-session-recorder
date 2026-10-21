"""Run with python -m recorder on Windows."""
import os
import sys
import threading
from pathlib import Path


def main():
    if sys.platform != 'win32':
        raise SystemExit('The recorder GUI requires Windows. Portable tests run on other platforms.')
    from .windows import enable_dpi_awareness, geometry
    enable_dpi_awareness()
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
    from .session import Session
    from .core import generate_heatmaps
    from .obs import connect as connect_obs

    root = tk.Tk()
    root.title('Usability Session Recorder')
    root.geometry('670x490')
    obs = None
    session = None
    busy = False
    password = tk.StringVar(value=os.environ.get('OBS_WEBSOCKET_PASSWORD', ''))
    mode = tk.StringVar(value='in-person')
    rect = tk.StringVar(value=','.join(map(str, geometry()['desktop_rect'])))
    output = tk.StringVar(value=str(Path('sessions').resolve()))
    status = tk.StringVar(value='Disconnected')
    diagnostic = tk.StringVar(value='Input counts appear during recording. No keys are recorded.')
    correction = tk.StringVar(value='0')
    frame = ttk.Frame(root, padding=16)
    frame.pack(fill='both', expand=True)
    for label, variable, secret in [('OBS password (not saved)',password,True),
                                     ('Sessions folder',output,False),
                                     ('Capture rectangle: left,top,width,height',rect,False)]:
        ttk.Label(frame,text=label).pack(anchor='w')
        ttk.Entry(frame,textvariable=variable,show='*' if secret else '').pack(fill='x',pady=(0,7))
    ttk.Combobox(frame,textvariable=mode,values=['in-person','zoom'],state='readonly').pack(anchor='w')
    ttk.Label(frame,text='Mode labels the session; configure microphone/desktop audio in OBS.').pack(anchor='w')
    buttons = []

    def work(action, success=None):
        nonlocal busy
        if busy:
            return
        busy = True
        for button in buttons:
            button.configure(state='disabled')
        def complete(result, error):
            nonlocal busy
            busy = False
            for button in buttons:
                button.configure(state='normal')
            if error:
                status.set('Operation failed — inspect error; retry Stop if OBS may be recording')
                messagebox.showerror('Recorder', str(error))
            elif success:
                success(result)
        def run():
            try:
                result, error = action(), None
            except Exception as exc:
                result, error = None, exc
            root.after(0, complete, result, error)
        threading.Thread(target=run, daemon=True).start()

    def connect():
        if session and session.active:
            messagebox.showerror('Recorder','Stop the current session before reconnecting.')
            return
        secret = password.get()
        def done(client):
            nonlocal obs
            obs = client
            password.set('')
            status.set('Connected to OBS websocket v5 on localhost:4455')
        work(lambda: connect_obs(secret), done)

    def start():
        nonlocal session
        if obs is None:
            messagebox.showerror('Recorder','Connect to OBS first.')
            return
        if session and session.active:
            return
        try:
            capture = [int(value.strip()) for value in rect.get().split(',')]
            if len(capture) != 4 or capture[2] <= 0 or capture[3] <= 0:
                raise ValueError('Enter left,top,width,height with positive width and height')
            session = Session(obs,output.get(),mode.get(),capture,geometry)
        except Exception as exc:
            messagebox.showerror('Recorder',str(exc))
            return
        work(session.start,lambda _:status.set(f'Recording: {session.folder}'))

    def stop():
        if session:
            work(session.stop,lambda _:status.set(f'Stopped; files saved in {session.folder}'))

    def heatmaps():
        if session and session.active:
            messagebox.showerror('Recorder','Stop the recording before generating heatmaps.')
            return
        folder = filedialog.askdirectory(title='Select a completed session folder')
        if folder:
            work(lambda:generate_heatmaps(folder),lambda _:status.set(f'Heatmaps saved in {folder}'))

    def marker():
        if not session or not session.active or busy:
            return
        # Marker request precedes Tk rendering; this delay is part of manual validation.
        session.marker()
        popup = tk.Toplevel(root)
        popup.title('SYNC')
        popup.attributes('-topmost',True)
        popup.configure(bg='magenta')
        tk.Label(popup,text=f'SYNC {len(session.sync["markers"])}',font=('Arial',48),bg='magenta').pack(padx=30,pady=30)
        popup.after(800,popup.destroy)

    row = ttk.Frame(frame)
    row.pack(fill='x',pady=12)
    for title,command in [('Connect to OBS',connect),('Start Session',start),('Stop Session',stop),
                          ('Generate Heatmaps',heatmaps),('Sync Marker',marker)]:
        button = ttk.Button(row,text=title,command=command)
        button.pack(side='left')
        buttons.append(button)
    ttk.Label(frame,textvariable=status,wraplength=620).pack(anchor='w',pady=8)
    ttk.Label(frame,textvariable=diagnostic,wraplength=620).pack(anchor='w')
    ttk.Label(frame,text='Measured sync correction (ms): actual video time minus estimated time').pack(anchor='w',pady=(12,0))
    ttk.Entry(frame,textvariable=correction,width=15).pack(anchor='w')
    def save_correction():
        if session and not busy:
            try:
                value = float(correction.get())
                import math
                if not math.isfinite(value):
                    raise ValueError('Correction must be finite')
                session.sync['manual_correction_ms'] = value
                session.save()
            except Exception as exc:
                messagebox.showerror('Recorder',str(exc))
    ttk.Button(frame,text='Save correction',command=save_correction).pack(anchor='w')

    def poll():
        if session:
            diagnostic.set(f'Global input counts: {dict(session.counts)}'
                           + (' | INPUT ERROR: '+session.meta['input_error'] if 'input_error' in session.meta else ''))
        root.after(500,poll)
    def close():
        if busy or (session and session.active):
            messagebox.showinfo('Recorder','Finish the current operation and stop the session before closing.')
        else:
            root.destroy()
    root.protocol('WM_DELETE_WINDOW',close)
    poll()
    root.mainloop()


if __name__ == '__main__':
    main()
