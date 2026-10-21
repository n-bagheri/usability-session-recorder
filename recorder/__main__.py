"""Run with python -m recorder on Windows."""
import os
import sys
import threading
from pathlib import Path


def main():
    if sys.platform != 'win32':
        raise SystemExit('The recorder GUI requires Windows. Portable tests run on other platforms.')
    from .windows import enable_dpi_awareness, geometry, chrome_windows, target_snapshot
    from .targeting import calibrate, same_identity
    enable_dpi_awareness()
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog, simpledialog
    from .session import Session
    from .core import generate_heatmaps
    from .obs import connect as connect_obs

    root = tk.Tk()
    root.title('Usability Session Recorder')
    root.geometry('920x740')
    obs = None
    session = None
    busy = False
    targets = []
    target_calibration = None
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
                                     ('Legacy desktop rectangle (MapGen heatmaps use calibrated content instead)',rect,False)]:
        ttk.Label(frame,text=label).pack(anchor='w')
        ttk.Entry(frame,textvariable=variable,show='*' if secret else '').pack(fill='x',pady=(0,7))
    ttk.Combobox(frame,textvariable=mode,values=['in-person','zoom'],state='readonly').pack(anchor='w')
    ttk.Label(frame,text='Mode labels the session; configure microphone/desktop audio in OBS.').pack(anchor='w')
    buttons = []
    ttk.Label(frame,text='Target Chrome window (match the OBS Window Capture source):').pack(anchor='w',pady=(10,0))
    target_choice = ttk.Combobox(frame,state='readonly',width=100)
    target_choice.pack(fill='x')
    calibration_status = tk.StringVar(value='Select window, then pick MapGen CONTENT corners (exclude Chrome toolbar).')
    ttk.Label(frame,textvariable=calibration_status,wraplength=870).pack(anchor='w')
    def changed_target(_=None):
        nonlocal target_calibration
        target_calibration = None
        calibration_status.set('Content calibration required for this target.')
    target_choice.bind('<<ComboboxSelected>>',changed_target)
    def refresh_targets():
        nonlocal targets
        if busy or (session and session.active):
            return
        try:
            targets = chrome_windows()
            target_choice['values'] = [f'{w["title"]} | HWND {w["identity"]["hwnd"]} PID {w["identity"]["pid"]}' for w in targets]
            target_choice.set('')
            changed_target()
        except Exception as exc:
            messagebox.showerror('Targets',str(exc))
    def pick_content():
        nonlocal target_calibration
        if busy or (session and session.active):
            return
        index = target_choice.current()
        if index < 0:
            messagebox.showerror('Targets','Refresh windows and select the MapGen Chrome window first.')
            return
        identity = targets[index]['identity']
        target_calibration = None
        calibration_status.set('Waiting for new content calibration…')
        messagebox.showinfo('Calibrate content',
            'Keep MapGen visible and unchanged. Recorder will minimize. Within 30 seconds, click '
            'the TOP-LEFT content pixel, then the BOTTOM-RIGHT content pixel. '
            'Exclude tabs, address/bookmarks bars, side panels and window borders. '
            'These two clicks are delivered to Chrome. Do not move/resize the window between clicks.')
        root.iconify()
        def action():
            from pynput import mouse
            picks = []
            def clicked(x,y,button,pressed):
                if pressed:
                    picks.append((x,y,target_snapshot(identity['hwnd'],x,y)))
                    if len(picks) == 2:
                        return False
            listener = mouse.Listener(on_click=clicked)
            try:
                listener.start()
                listener.join(timeout=30)
            finally:
                listener.stop()
                root.after(0,root.deiconify)
            if len(picks) != 2:
                raise ValueError('Calibration timed out; select two content corners and retry.')
            a,b = picks
            for x,y,snapshot in picks:
                if (snapshot.get('error') or not snapshot.get('stable') or
                    not same_identity(identity,snapshot.get('identity',{})) or
                    snapshot.get('hit_root') != identity['hwnd'] or snapshot.get('possible_occluders')):
                    raise ValueError('Target changed or was covered during calibration. Retry with unobscured MapGen.')
            if a[2]['client_rect'] != b[2]['client_rect'] or a[2]['dpi'] != b[2]['dpi'] or a[2]['title_digest'] != b[2]['title_digest']:
                raise ValueError('Window/page changed between corners; retry.')
            return calibrate(a[2],a[:2],b[:2])
        def done(value):
            nonlocal target_calibration
            target_calibration = value
            calibration_status.set(f'Calibrated content: {value["reference_size"]} physical pixels at {value["dpi"]} DPI. Keep this tab selected.')
        work(action,done)
    target_row = ttk.Frame(frame)
    target_row.pack(anchor='w',pady=5)
    for title,command in [('Refresh Chrome windows',refresh_targets),('Pick content corners',pick_content)]:
        button = ttk.Button(target_row,text=title,command=command)
        button.pack(side='left')
        buttons.append(button)

    def work(action, success=None):
        nonlocal busy
        if busy:
            return
        busy = True
        target_choice.configure(state='disabled')
        for button in buttons:
            button.configure(state='disabled')
        def complete(result, error):
            nonlocal busy
            busy = False
            target_choice.configure(state='disabled' if session and session.active else 'readonly')
            for button in buttons:
                button.configure(state='normal')
            if error:
                if session and session.active:
                    status.set(f'OBS {session.meta["state"]}; input capture continues. Use Check OBS or Stop Session.')
                else:
                    status.set('Operation failed; inspect the error.')
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
        if busy:
            return
        if obs is None:
            messagebox.showerror('Recorder','Connect to OBS first.')
            return
        if session and session.active:
            return
        try:
            capture = [int(value.strip()) for value in rect.get().split(',')]
            if len(capture) != 4 or capture[2] <= 0 or capture[3] <= 0:
                raise ValueError('Enter left,top,width,height with positive width and height')
            if target_calibration is None:
                raise ValueError('Select a Chrome window and calibrate its MapGen content corners first.')
            session = Session(obs,output.get(),mode.get(),capture,geometry,
                              target=target_calibration,target_provider=target_snapshot)
            status.set('Starting OBS; waiting for recording confirmation (up to 10s plus a request timeout)…')
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
            def done(report):
                status.set(f'Heatmaps saved. Counts: {report.get("click_presses",{})}. Alignment: {report["alignment"]["status"]}')
            work(lambda:generate_heatmaps(folder),done)

    def check_obs():
        if session and session.active:
            status.set('Checking OBS recording confirmation; input capture continues…')
            work(session.confirm_recording,lambda _:status.set(f'Recording confirmed: {session.folder}'))

    def align_frame():
        if busy or (session and session.active):
            return
        import json
        from .calibration import save_frame_mapping
        folder = filedialog.askdirectory(title='Completed session (generate heatmaps first)')
        if not folder:
            return
        try:
            report = json.loads((Path(folder)/'analysis.json').read_text(encoding='utf-8'))
            keys = list(report['layouts'])
            if not keys:
                raise ValueError('No included MapGen events; validate window/content calibration first.')
            key = simpledialog.askstring('Frame layout','Choose exact layout: '+', '.join(keys),initialvalue=keys[0])
            if key is None:
                return
            width,height = report['layouts'][key]['content_size']
            image = filedialog.askopenfilename(title='Representative OBS frame/screenshot (PNG)',filetypes=[('PNG','*.png')])
            if not image:
                return
            source = simpledialog.askstring('Source content crop',
                'Visible MapGen-local crop in physical pixels: left,top,width,height. '
                'Use full content only if OBS displays all content.',initialvalue=f'0,0,{width},{height}')
            if source is None:
                return
            dest = simpledialog.askstring('Content bounds in frame',
                'Enter measured content bounds IN THE REFERENCE IMAGE: left,top,width,height. '
                'Exclude letterboxing and account for OBS crop/scale. No rotated/perspective mappings.')
            if dest is None:
                return
            source = [float(v.strip()) for v in source.split(',')]
            dest = [float(v.strip()) for v in dest.split(',')]
            def action():
                save_frame_mapping(folder,image,key,source,dest)
                return generate_heatmaps(folder)
            work(action,lambda report:status.set(f'Overlay saved; alignment: {report["alignment"]["status"]}. Visually verify before analysis.'))
        except Exception as exc:
            messagebox.showerror('Frame alignment',str(exc))

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
                          ('Generate Heatmaps',heatmaps),('Sync Marker',marker),('Check OBS',check_obs),('Align Frame',align_frame)]:
        button = ttk.Button(row,text=title,command=command)
        button.pack(side='left')
        buttons.append(button)
    ttk.Label(frame,textvariable=status,wraplength=870).pack(anchor='w',pady=8)
    ttk.Label(frame,textvariable=diagnostic,wraplength=870).pack(anchor='w')
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
            diagnostic.set(f'Global input counts: {dict(session.counts)} | Target: {dict(session.target_counts)}'
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
