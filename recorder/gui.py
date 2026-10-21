"""Basic/Advanced workflow built around the existing recording Session engine."""
import copy
import json
import os
import queue
import threading
import time
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox,filedialog
from PIL import Image,ImageTk,ImageDraw
from .windows import chrome_windows,target_snapshot,geometry
from .viewport import read_viewport
from .capture import CalibrationMonitor
from .obs import connect,SerializedOBS
from .session import Session
from .media import Video
from .review import load_review,write_review
from .qa import event_seconds
from .review_ui import ReviewWindow
from .hotkeys import GlobalShortcuts


class RecorderUI:
    def __init__(self,root):
        self.root=root;root.title('Usability Session Recorder');root.geometry('870x680')
        self.obs=None;self.session=None;self.monitor=None;self.calibration=None;self.targets=[]
        self.busy=False;self.jobs=queue.Queue();self.shortcuts=None;self.buttons=[]
        self.status=tk.StringVar(value='Not ready — select the MapGen Chrome window.')
        self.readiness=tk.StringVar(value='OBS disconnected | calibration unavailable | spatial/timing UNVERIFIED')
        self.password=tk.StringVar(value=os.environ.get('OBS_WEBSOCKET_PASSWORD',''))
        self.port=tk.StringVar(value='4455');self.output=tk.StringVar(value=str(Path('sessions').resolve()))
        self.mode=tk.StringVar(value='in-person');self.hotkey=tk.StringVar(value='Ctrl+Alt+Shift+F9')
        self.taskkey=tk.StringVar(value='Ctrl+Alt+Shift+F10');self.armed=tk.BooleanVar(value=False)
        self.countdown=tk.StringVar(value='0');self.allow_unverified=tk.BooleanVar(value=False)
        self.diagnostics=tk.StringVar(value='No recording. Raw global input is always retained.')
        tabs=ttk.Notebook(root);tabs.pack(fill='both',expand=True,padx=12,pady=12)
        basic=ttk.Frame(tabs,padding=12);advanced=ttk.Frame(tabs,padding=12)
        tabs.add(basic,text='Basic session workflow');tabs.add(advanced,text='Advanced / diagnostics')
        ttk.Label(basic,textvariable=self.readiness,wraplength=800).pack(fill='x',pady=10)
        ttk.Label(basic,text='1. Select MapGen Chrome Window').pack(anchor='w')
        row=ttk.Frame(basic);row.pack(fill='x')
        self.target=ttk.Combobox(row,state='readonly');self.target.pack(side='left',fill='x',expand=True)
        self.target.bind('<<ComboboxSelected>>',lambda _:self.invalidate())
        self.button(row,'Refresh windows',self.refresh).pack(side='left')
        ttk.Label(basic,text='2. Connect and validate OBS').pack(anchor='w',pady=(12,0))
        row=ttk.Frame(basic);row.pack(fill='x')
        ttk.Label(row,text='OBS password:').pack(side='left');ttk.Entry(row,textvariable=self.password,show='*',width=30).pack(side='left')
        self.button(row,'Connect OBS',self.connect).pack(side='left',padx=8)
        ttk.Label(basic,text='3. Auto-Calibrate and Verify (webpage viewport + OBS saved-frame mapping)').pack(anchor='w',pady=(12,0))
        row=ttk.Frame(basic);row.pack(fill='x')
        for label,command in [('Auto-Calibrate',self.auto_calibrate),('Preview boundary',self.preview),('Verify Alignment…',self.verify)]:
            self.button(row,label,command).pack(side='left',padx=3)
        row=ttk.Frame(basic);row.pack(fill='x',pady=18)
        for label,command in [('4. Start Session',self.start),('5. Stop Session',self.stop),('6. Review / Generate Analysis',self.review)]:
            self.button(row,label,command).pack(side='left',padx=4)
        self.button(basic,'Begin / End Participant Task (optional)',self.task_boundary).pack(anchor='w')
        ttk.Label(basic,text='Task intervals can also be set after recording. The participant does not need to use this interface.',wraplength=790).pack(anchor='w',pady=6)
        ttk.Label(basic,textvariable=self.status,wraplength=800).pack(fill='x',pady=12)
        ttk.Label(basic,textvariable=self.diagnostics,wraplength=800).pack(fill='x')
        self.entry(advanced,'Private sessions folder',self.output)
        self.entry(advanced,'OBS WebSocket port (localhost only)',self.port)
        ttk.Combobox(advanced,textvariable=self.mode,values=['in-person','zoom'],state='readonly').pack(anchor='w')
        ttk.Label(advanced,text='Audio is configured and recorded by OBS. Mode is a label, not an audio-source switch.').pack(anchor='w')
        self.entry(advanced,'Optional start countdown seconds (0–10)',self.countdown)
        self.entry(advanced,'Global start/stop combination',self.hotkey)
        self.entry(advanced,'Global participant-task begin/end combination',self.taskkey)
        ttk.Checkbutton(advanced,text='ARM registered shortcuts (default OFF; only deliberate triple-modifier combinations)',variable=self.armed).pack(anchor='w')
        row=ttk.Frame(advanced);row.pack(anchor='w')
        self.button(row,'Register + check conflicts',self.enable_hotkeys).pack(side='left')
        self.button(row,'Disable shortcuts',self.disable_hotkeys).pack(side='left')
        self.button(advanced,'Manual viewport fallback — visual guide + explicit confirmation',self.manual).pack(anchor='w',pady=8)
        ttk.Checkbutton(advanced,text='Allow raw recording without valid calibration (all attribution stays uncertain)',variable=self.allow_unverified).pack(anchor='w')
        row=ttk.Frame(advanced);row.pack(anchor='w',pady=8)
        self.button(row,'Check OBS recording confirmation',self.check_obs).pack(side='left')
        self.button(row,'Calibration details',self.details).pack(side='left')
        ttk.Label(advanced,text='Corrections, independent spatial/timing measurements, video frames and view/state segments are in Review.\nNo settings containing passwords or window identifiers are reused across sessions.',wraplength=800).pack(anchor='w')
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(100,self.drain);root.after(200,self.refresh);root.after(500,self.poll)

    def button(self,parent,text,command):
        b=ttk.Button(parent,text=text,command=command);self.buttons.append(b);return b

    def entry(self,parent,label,variable):
        ttk.Label(parent,text=label).pack(anchor='w');ttk.Entry(parent,textvariable=variable,width=65).pack(fill='x',pady=(0,6))

    def work(self,action,done=None):
        if self.busy:return
        self.busy=True
        for b in self.buttons:b.configure(state='disabled')
        self.target.configure(state='disabled')
        def run():
            try:self.jobs.put((done,action(),None))
            except Exception as exc:self.jobs.put((done,None,exc))
        threading.Thread(target=run,daemon=True).start()

    def drain(self):
        try:
            job=self.jobs.get_nowait()
            if job[0]=='shortcut':
                if self.armed.get() and not self.busy:
                    if job[1]==1:
                        self.stop() if self.session and self.session.active else self.start()
                    elif job[1]==2:self.task_boundary()
            else:
                done,result,error=job;self.busy=False
                for b in self.buttons:b.configure(state='normal')
                self.target.configure(state='disabled' if self.session and self.session.active else 'readonly')
                if error:
                    self.root.deiconify()
                    self.status.set(('Error / recording state uncertain; raw capture continues. Use Check OBS or Stop. ' if self.session and self.session.active else 'Not ready / error. ')+str(error))
                    messagebox.showerror('Recorder',str(error),parent=self.root)
                elif done:done(result)
        except queue.Empty:pass
        self.root.after(100,self.drain)

    def selected(self):
        i=self.target.current()
        if i<0:raise ValueError('Select the intended MapGen Chrome window first')
        return self.targets[i]

    def invalidate(self):
        if self.monitor:self.monitor.stop()
        self.monitor=None;self.calibration=None
        self.readiness.set('OBS '+('connected' if self.obs else 'disconnected')+' | auto-calibration needed | spatial/timing UNVERIFIED')

    def refresh(self):
        if self.busy or self.session and self.session.active:return
        def done(windows):
            self.targets=windows;self.target['values']=[f'{w["title"]} | HWND {w["identity"]["hwnd"]}' for w in windows]
            if len(windows)==1:self.target.current(0)
            else:self.target.set('')
            self.invalidate()
        self.work(chrome_windows,done)

    def connect(self):
        if self.session and self.session.active:return
        try:port=int(self.port.get())
        except ValueError:messagebox.showerror('Port','Use a valid port');return
        secret=self.password.get();self.status.set('Connecting to OBS…')
        def done(client):
            self.obs=SerializedOBS(client);self.password.set('');self.invalidate()
            self.status.set('OBS connected. Auto-Calibrate validates the associated Window Capture source and transform.')
        self.work(lambda:connect(secret,port),done)

    def new_monitor(self,viewport_reader=read_viewport):
        if not self.obs:raise ValueError('Connect OBS first')
        if self.monitor:self.monitor.stop()
        return CalibrationMonitor(self.obs,self.selected(),target_snapshot,viewport_reader,chrome_windows)

    def auto_calibrate(self):
        if self.session and self.session.active:return
        try:monitor=self.new_monitor()
        except Exception as exc:messagebox.showerror('Calibration',str(exc));return
        self.status.set('Measuring webpage Document via Windows UIA and reading real OBS source/scene/output settings…')
        def action():
            c=monitor.calibration()
            # Capture a nonpersistent preview while the source is unchanged.
            return c
        def done(calibration):
            self.monitor=monitor;self.calibration=calibration;monitor.start()
            self.status.set('Calibration computed. Inspect boundary; use a recorded QA trial to measure real spatial/timing errors.')
            self.readiness.set(f'OBS source: {calibration["capture_mapping"]["source_name"]} | webpage {calibration["reference_size"]} physical px | computed, NOT experimentally verified')
            self.preview()
        self.work(action,done)

    def preview(self):
        if not self.calibration or self.busy:return
        from PIL import ImageGrab
        try:
            snapshot=target_snapshot(self.calibration['identity']['hwnd'],0,0)
            client=snapshot['client_rect'];v=(self.monitor.latest or {}).get('viewport')
            if not v:raise ValueError('Viewport measurement is invalid; recalibrate')
            image=ImageGrab.grab(bbox=(client[0],client[1],client[0]+client[2],client[1]+client[3]),all_screens=True)
            x,y,w,h=v['rect'];draw=ImageDraw.Draw(image)
            draw.rectangle((x-client[0],y-client[1],x-client[0]+w-1,y-client[1]+h-1),outline='lime',width=4)
            self.image_window(image,'Computed webpage boundary — inspect all edges, exclude Chrome controls')
        except Exception as exc:messagebox.showerror('Preview',str(exc))

    def image_window(self,image,title):
        window=tk.Toplevel(self.root);window.title(title)
        scale=min(1100/image.width,650/image.height,1)
        display=image.resize((int(image.width*scale),int(image.height*scale)))
        photo=ImageTk.PhotoImage(display);label=ttk.Label(window,image=photo);label.image=photo;label.pack()
        ttk.Label(window,text='This desktop preview is NOT evidence of saved-video alignment. Measure independent targets after recording.',wraplength=1000).pack()

    def verify(self):
        self.preview()
        if messagebox.askyesno('Verify using saved video',
            'Verification requires a recorded trial with five independent targets at corners and center. '
            'Open the included standalone calibration board in Chrome? It is separate from MapGen; no code is injected into MapGen. '
            'Use the same selected Chrome window and OBS setup, then recalibrate if the window changes. '
            'After recording, Review → select each click → Measure target position; step to visible onset → Mark visible action time.'):
            webbrowser.open((Path(__file__).resolve().parent.parent/'calibration_board.html').as_uri(),new=0)

    def manual(self):
        if self.session and self.session.active:return
        try:
            selected=self.selected();snapshot=target_snapshot(selected['identity']['hwnd'],0,0)
            if snapshot.get('error'):raise ValueError(snapshot['error'])
        except Exception as exc:messagebox.showerror('Manual fallback',str(exc));return
        messagebox.showinfo('Visual fallback','Put the selected Chrome window unobscured on screen. Recorder will minimize, capture a preview, then let you draw the webpage boundary. This is a manual, unverified fallback; use automatic UIA whenever available.')
        from PIL import ImageGrab
        self.root.iconify()
        def grab():
            time.sleep(.7)
            c=snapshot['client_rect']
            for u,v in ((.05,.05),(.95,.05),(.5,.5),(.05,.95),(.95,.95)):
                check=target_snapshot(selected['identity']['hwnd'],c[0]+int(c[2]*u),c[1]+int(c[3]*v))
                if check.get('hit_root')!=selected['identity']['hwnd'] or check.get('possible_occluders') or check.get('client_rect')!=c:
                    raise ValueError('Manual screenshot must show the unchanged selected Chrome window unobscured. Move covering windows and retry.')
            return ImageGrab.grab(bbox=(c[0],c[1],c[0]+c[2],c[1]+c[3]),all_screens=True)
        def done(image):
            self.root.deiconify();window=tk.Toplevel(self.root);window.title('MANUAL FALLBACK — draw content boundary and explicitly confirm')
            scale=min(1100/image.width,650/image.height,1);photo=ImageTk.PhotoImage(image.resize((int(image.width*scale),int(image.height*scale))))
            canvas=tk.Canvas(window,width=photo.width(),height=photo.height());canvas.pack();canvas.create_image(0,0,image=photo,anchor='nw');canvas.photo=photo
            points=[];text=tk.StringVar(value='Click top-left, then bottom-right page-content pixel in this image. Exclude all browser controls.')
            ttk.Label(window,textvariable=text,wraplength=1000).pack()
            def click(e):
                if len(points)==2:points.clear();canvas.delete('guide')
                points.append([int(e.x/scale),int(e.y/scale)])
                canvas.create_line(e.x,0,e.x,photo.height(),fill='cyan',tags='guide');canvas.create_line(0,e.y,photo.width(),e.y,fill='cyan',tags='guide')
                if len(points)==2:
                    canvas.create_rectangle(points[0][0]*scale,points[0][1]*scale,points[1][0]*scale,points[1][1]*scale,outline='lime',width=3,tags='guide')
                    text.set(f'Manual bounds: {points}. Check all edges; click again to redraw.')
            canvas.bind('<Button-1>',click)
            def confirm():
                if len(points)!=2:return
                from .targeting import calibrate
                try:
                    c=snapshot['client_rect'];a,b=points
                    manual=calibrate(snapshot,[c[0]+a[0],c[1]+a[1]],[c[0]+b[0],c[1]+b[1]])
                    def reader(hwnd,client):
                        now=target_snapshot(hwnd,0,0)
                        if client[2:]!=c[2:] or now.get('dpi')!=snapshot['dpi'] or now.get('title_digest')!=snapshot['title_digest'] or now.get('maximized')!=snapshot.get('maximized'):
                            raise ValueError('Manual fallback invalidated by size/DPI/title/window-mode change')
                        return {'rect':[client[0]+a[0],client[1]+a[1],b[0]-a[0]+1,b[1]-a[1]+1],
                                'method':'manual_visual_explicit_confirmation','zoom_monitoring':'unavailable_keep_fixed','status':'unverified'}
                    monitor=self.new_monitor(reader)
                    def accepted(value):
                        self.monitor=monitor;self.calibration=value;monitor.start()
                        self.readiness.set('MANUAL fallback computed — not experimentally verified. Record and measure five-target QA trial.')
                    self.work(monitor.calibration,accepted);window.destroy()
                except Exception as exc:messagebox.showerror('Fallback',str(exc),parent=window)
            ttk.Button(window,text='I confirm the visual boundary (unverified fallback)',command=confirm).pack()
        self.work(grab,done)

    def start(self):
        if self.busy or self.session and self.session.active:return
        try:
            if not self.obs:raise ValueError('Connect OBS first')
            selected=self.selected();calibration=copy.deepcopy(self.calibration)
            if not calibration and not self.allow_unverified.get():raise ValueError('Auto-calibrate first, or explicitly allow unverified raw recording in Advanced')
            if calibration and (not self.monitor or (self.monitor.latest or {}).get('status')!='computed'):
                raise ValueError('Calibration is stale/invalid. Recalibrate before recording.')
            seconds=int(self.countdown.get())
            if not 0<=seconds<=10:raise ValueError('Countdown must be 0–10 seconds')
            if calibration is None:
                s=target_snapshot(selected['identity']['hwnd'],0,0)
                calibration={'identity':selected['identity'],'method':'unverified','dpi':s.get('dpi',96)}
            self.session=Session(self.obs,self.output.get(),self.mode.get(),geometry()['desktop_rect'],geometry,
                                 target=calibration,target_provider=self.monitor.observe if self.monitor else target_snapshot)
            if self.monitor:self.monitor.bind(self.session.folder)
            self.session.meta['calibration_initial']=self.monitor.latest if self.monitor else {'status':'unverified'}
            self.session.meta['shortcut_configuration']={'enabled':self.shortcuts is not None,'armed':self.armed.get(),'toggle':self.hotkey.get(),'task':self.taskkey.get()}
            self.status.set('Starting — countdown / awaiting two settled OBS status responses…')
        except Exception as exc:messagebox.showerror('Start',str(exc));return
        def action():
            if seconds:time.sleep(seconds)
            self.session.start()
        self.work(action,lambda _:self.status.set(f'Recording — {self.session.folder}. Participant interval can be marked now or adjusted in Review.'))

    def stop(self):
        if not self.session or self.busy:return
        self.status.set('Stopping — waiting for OBS acknowledgement, copying and decoding finalized video…')
        session=self.session
        def action():
            session.stop()
            if self.monitor:self.monitor.bind(None)
            video=Video(session.folder)
            if not video.pts:raise ValueError('Finalized video has no frames')
            session.meta['finalization']={'status':'saved_video_decoded','frames':len(video.pts),'video_signature':video.signature}
            session.save()
            review=load_review(session.folder,video.info['duration'])
            if 'analysis_begin_ns' in session.meta and 'origin_ns' in session.sync:
                begin=event_seconds({'monotonic_ns':session.meta['analysis_begin_ns']},session.sync)
                end=event_seconds({'monotonic_ns':session.meta.get('analysis_end_ns',session.meta['stop_response_ns'])},session.sync)
                if 0<=begin<end<=video.info['duration']:review['analysis_interval']=[begin,end]
            write_review(session.folder,review,video.info['duration'])
            return video
        def done(video):
            self.status.set(f'Complete — finalized video: {len(video.pts)} frames; mouse {session.counts}; filtering {session.target_counts}. Spatial/timing: UNVERIFIED until measured; segmentation: review required.')
        self.work(action,done)

    def task_boundary(self):
        if self.busy or not self.session or not self.session.active:return
        beginning='analysis_begin_ns' not in self.session.meta or 'analysis_end_ns' in self.session.meta
        if beginning:self.session.meta.pop('analysis_end_ns',None)
        self.session.task_boundary(beginning)
        self.status.set('Recording — participant task '+('BEGIN' if beginning else 'END')+' marker saved (adjustable after recording).')

    def check_obs(self):
        if self.session and self.session.active:self.work(self.session.confirm_recording,lambda _:self.status.set('Recording confirmed by settled OBS status samples.'))

    def review(self):
        if self.session and self.session.active:return
        folder=filedialog.askdirectory(title='Select completed session folder',initialdir=str(self.session.folder if self.session else self.output.get()))
        if folder:ReviewWindow(self.root,folder)

    def details(self):
        messagebox.showinfo('Calibration evidence',json.dumps(self.monitor.latest if self.monitor else {'status':'unavailable'},indent=2)[:9000])

    def enable_hotkeys(self):
        self.armed.set(False)
        if self.shortcuts:self.shortcuts.stop()
        self.shortcuts=None
        try:
            keys=GlobalShortcuts({1:self.hotkey.get(),2:self.taskkey.get()},lambda key:self.jobs.put(('shortcut',key,None)))
            def done(_):
                self.shortcuts=keys;self.status.set('Windows shortcut registration succeeded. ARM explicitly to enable. OS registration detects global conflicts, not every browser/application binding.')
            self.work(keys.start,done)
        except Exception as exc:messagebox.showerror('Shortcuts',str(exc))

    def disable_hotkeys(self):
        self.armed.set(False)
        if self.shortcuts:self.shortcuts.stop()
        self.shortcuts=None;self.status.set('Global shortcuts disabled.')

    def poll(self):
        if self.session:
            self.diagnostics.set(f'Raw callbacks: {self.session.counts} | target classification: {self.session.target_counts}'+
                                 (' | WRITE ERROR '+self.session.meta['input_error'] if self.session.meta.get('input_error') else ''))
        if self.monitor and self.monitor.latest and self.monitor.latest['status']=='computed':
            v=self.monitor.latest['viewport']
            self.readiness.set(f'OBS {self.monitor.latest["mapping"]["source_name"]} | viewport {v["rect"][2:]} physical px | computed, NOT experimentally verified | zoom: {v.get("zoom_monitoring","unknown")}')
        if self.monitor and self.monitor.latest and self.monitor.latest['status']=='invalid':
            self.readiness.set('Calibration INVALID: '+self.monitor.latest['reason']+' — raw input remains available; attribution/overlays uncertain')
        self.root.after(500,self.poll)

    def close(self):
        if self.busy or self.session and self.session.active:
            messagebox.showinfo('Recorder','Finish operation and stop the live session before closing.');return
        if self.monitor:self.monitor.stop()
        self.disable_hotkeys();self.root.destroy()
