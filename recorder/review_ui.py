"""Post-session editor: actual decoded frames, segments, independent QA and export."""
import copy
import json
import os
import queue
import threading
import uuid
from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox,simpledialog
from PIL import Image,ImageTk,ImageDraw
from .research import ResearchSession,suggest_transitions
from .review import write_review,save_json


class ReviewWindow:
    def __init__(self,parent,folder):
        self.root=tk.Toplevel(parent);self.root.title('Session Review — saved video / view states / QA')
        self.root.geometry('1250x900')
        self.data=None;self.current=None;self.current_event=None;self.measuring=False
        self.busy=False;self.playing=False;self.pending_click=None;self.frame_photo=None;self.frame_scale=1;self.offset=(0,0)
        self.jobs=queue.Queue();self.closed=False
        self.status=tk.StringVar(value='Indexing saved video presentation timestamps…')
        self.time=tk.DoubleVar(value=0)
        toolbar=ttk.Frame(self.root);toolbar.pack(fill='x')
        for title,action in [('Play / Pause (muted)',self.play),('Open original video + audio',self.external),
            ('Suggest visual transitions',self.suggest),('Generate view-aware analysis',self.export),('Save review',self.save)]:
            ttk.Button(toolbar,text=title,command=action).pack(side='left')
        self.canvas=tk.Canvas(self.root,width=1000,height=500,bg='#222');self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Button-1>',self.canvas_click)
        self.slider=ttk.Scale(self.root,from_=0,to=1,variable=self.time,command=self.scrub)
        self.slider.pack(fill='x');self.slider.bind('<ButtonRelease-1>',lambda _:self.seek())
        ttk.Label(self.root,textvariable=self.status,wraplength=1200).pack(fill='x')
        controls=ttk.Frame(self.root);controls.pack(fill='x')
        for title,action in [('Prev frame',lambda:self.step(-1)),('Next frame',lambda:self.step(1)),
            ('Set analysis START here',lambda:self.interval(True)),('Set analysis END here',lambda:self.interval(False)),
            ('Add / Edit segment',self.edit_segment),('Delete segment',self.delete_segment),
            ('Measure target position',self.measure),('Mark visible action time',self.temporal)]:
            ttk.Button(controls,text=title,command=action).pack(side='left')
        secondary=ttk.Frame(self.root);secondary.pack(fill='x')
        for title,action in [('Mark mapping visually inspected',self.inspected),('Apply measured median time offset',self.apply_offset),
                             ('Show QA / end-of-session summary',self.summary),('Label expected click class',self.label_class)]:
            ttk.Button(secondary,text=title,command=action).pack(side='left')
        panes=ttk.Panedwindow(self.root,orient='horizontal');panes.pack(fill='both',expand=False)
        self.segments=ttk.Treeview(panes,columns=('start','end','view','state','stable'),show='headings',height=6)
        for col in self.segments['columns']:self.segments.heading(col,text=col);self.segments.column(col,width=100)
        self.clicks=ttk.Treeview(panes,columns=('id','time','class','local','activation'),show='headings',height=6)
        for col in self.clicks['columns']:self.clicks.heading(col,text=col);self.clicks.column(col,width=95)
        self.clicks.bind('<<TreeviewSelect>>',self.select_click)
        panes.add(self.segments,weight=1);panes.add(self.clicks,weight=1)
        self.root.protocol('WM_DELETE_WINDOW',self.close)
        self.root.after(100,self.drain)
        self.work(lambda:ResearchSession(folder),self.loaded)

    def close(self):
        self.closed=True;self.playing=False;self.root.destroy()

    def work(self,action,done=None):
        if self.busy:return
        self.busy=True
        def run():
            try:self.jobs.put((done,action(),None))
            except Exception as exc:self.jobs.put((done,None,exc))
        threading.Thread(target=run,daemon=True).start()

    def drain(self):
        if self.closed:return
        try:
            done,result,error=self.jobs.get_nowait();self.busy=False
            if error:
                self.playing=False;self.status.set('Unverified / failed: '+str(error));messagebox.showerror('Review',str(error),parent=self.root)
            elif done:done(result)
        except queue.Empty:pass
        self.root.after(100,self.drain)

    def loaded(self,data):
        self.data=data;self.slider.configure(to=data.video.info['duration']);self.refresh_lists();self.seek(0)

    def refresh_lists(self):
        if not self.data:return
        for tree in (self.segments,self.clicks):
            for child in tree.get_children():tree.delete(child)
        for s in self.data.review['segments']:
            self.segments.insert('', 'end',iid=s['id'],values=(round(s['start'],3),round(s['end'],3),s['view'],s['state'],s.get('stable',False)))
        for e in self.data.events:
            if e['type']=='click' and e.get('pressed'):
                self.clicks.insert('','end',iid=e['event_id'],values=(e['event_id'],round(self.data.time(e),3),e['target']['classification'],e['target'].get('local'),e.get('activation','unknown')))

    def scrub(self,_=None):
        # Slider motion itself does not queue expensive decodes. Release to seek.
        pass

    def seek(self,seconds=None):
        if not self.data or self.busy:return
        seconds=float(self.time.get() if seconds is None else seconds)
        self.work(lambda:self.data.video.frame(seconds),self.show_frame)

    def show_frame(self,frame):
        self.current=frame;self.time.set(frame['seconds'])
        with Image.open(frame['path']) as image:image=image.convert('RGB')
        # Selected click is shown only near its time. Never paint every click on every view.
        if self.current_event and not self.measuring and abs(self.data.time(self.current_event)-frame['seconds'])<=2/self.data.video.info['fps']:
            p=self.data.predict(self.current_event)
            if p:
                draw=ImageDraw.Draw(image);x,y=p;draw.ellipse((x-7,y-7,x+7,y+7),outline='red',width=3)
        self.frame_scale=min(max(self.canvas.winfo_width(),100)/image.width,max(self.canvas.winfo_height(),100)/image.height)
        size=(max(1,int(image.width*self.frame_scale)),max(1,int(image.height*self.frame_scale)))
        image=image.resize(size);self.frame_photo=ImageTk.PhotoImage(image)
        self.canvas.delete('all');self.canvas.create_image(0,0,image=self.frame_photo,anchor='nw')
        self.status.set(f'Saved frame {frame["index"]} | actual PTS {frame["seconds"]:.3f}s | '
                        + ('MEASURING: click the independent visible target center; predicted ring is hidden.' if self.measuring else 'Timing/spatial accuracy: see QA. Playback muted; original video retains audio.'))
        if self.pending_click is not None:
            self.current_event=self.data.by_id[self.pending_click];self.pending_click=None
            self.seek(self.data.time(self.current_event));return
        if self.playing:self.root.after(180,self.play_next)

    def play(self):
        self.playing=not self.playing
        if self.playing:self.play_next()

    def play_next(self):
        if not self.playing or not self.data:return
        if self.busy:self.root.after(180,self.play_next);return
        t=self.time.get()+.2
        if t>self.data.video.info['duration']:self.playing=False;return
        self.seek(t)

    def step(self,delta):
        self.playing=False
        if self.current and not self.busy:
            index=min(max(self.current['index']+delta,0),len(self.data.video.pts)-1)
            self.seek(self.data.video.pts[index])

    def select_click(self,_=None):
        if not self.data or not self.clicks.selection():return
        if self.busy:
            self.pending_click=self.clicks.selection()[0];return
        self.current_event=self.data.by_id[self.clicks.selection()[0]];self.measuring=False;self.playing=False
        self.seek(self.data.time(self.current_event))

    def interval(self,begin):
        if not self.current or self.busy:return
        proposed=copy.deepcopy(self.data.review)
        proposed['analysis_interval'][0 if begin else 1]=self.current['seconds']
        self.commit_review(proposed)

    def commit_review(self,value):
        try:
            write_review(self.data.folder,value,self.data.video.info['duration']);self.data.review=value
            self.refresh_lists();self.status.set('Review saved; raw events unchanged. Re-export analysis for updated results.')
            return True
        except Exception as exc:messagebox.showerror('Review',str(exc),parent=self.root)

    def edit_segment(self):
        if not self.current or self.busy:return
        selected=self.segments.selection()
        existing=next((s for s in self.data.review['segments'] if selected and s['id']==selected[0]),None)
        window=tk.Toplevel(self.root);window.title('Named view / visual state segment')
        values={}
        defaults={'start':self.current['seconds'],'end':min(self.current['seconds']+10,self.data.video.info['duration']),
                  'view':'Other','state':'Unclassified state','reference_seconds':self.current['seconds']}
        for key in defaults:
            ttk.Label(window,text=key).pack(anchor='w');var=tk.StringVar(value=str((existing or {}).get(key,defaults[key])))
            ttk.Entry(window,textvariable=var,width=55).pack(fill='x');values[key]=var
        stable=tk.BooleanVar(value=(existing or {}).get('stable',False))
        ttk.Checkbutton(window,text='I reviewed this entire interval: one spatially stable visual state',variable=stable).pack()
        reviewed=tk.BooleanVar(value=(existing or {}).get('visual_suggestion_review')=='reviewed_no_spatial_change')
        ttk.Checkbutton(window,text='I reviewed visual suggestions: animation only, no spatial-state change',variable=reviewed).pack()
        ttk.Label(window,text='Panning, scrolling, panels, loading, zoom or layout changes need separate states. Unknown gaps are retained.',wraplength=450).pack()
        def accept():
            try:
                s={k:(float(v.get()) if k in ('start','end','reference_seconds') else v.get()) for k,v in values.items()}
                s.update(id=existing['id'] if existing else uuid.uuid4().hex[:8],stable=stable.get(),
                         visual_suggestion_review='reviewed_no_spatial_change' if reviewed.get() else 'not_reviewed')
                review=copy.deepcopy(self.data.review)
                review['segments']=[item for item in review['segments'] if item['id']!=s['id']]+[s]

                if self.commit_review(review):window.destroy()
            except Exception as exc:messagebox.showerror('Segment',str(exc),parent=window)
        ttk.Button(window,text='Save segment',command=accept).pack()

    def delete_segment(self):
        if not self.data or self.busy or not self.segments.selection():return
        review=copy.deepcopy(self.data.review);chosen=self.segments.selection()[0]
        review['segments']=[s for s in review['segments'] if s['id']!=chosen];self.commit_review(review)

    def measure(self):
        if not self.current_event or not self.current or self.busy:return
        self.measuring=True;self.show_frame(self.current)

    def canvas_click(self,event):
        if not self.measuring or self.busy:return
        try:
            x,y=event.x/self.frame_scale,event.y/self.frame_scale
            if not (0<=x<self.current['size'][0] and 0<=y<self.current['size'][1]):return
            m=self.data.measure_spatial(self.current_event['event_id'],self.current,[x,y])
            m['reference_selection_uncertainty_px']=max(2,1/self.frame_scale)
            if messagebox.askyesno('Independent target measurement',f'Observed error: {m["error_px"]:.2f} recorded pixels. Save this measurement?\nUse actual target landmarks, not painted overlay rings.',parent=self.root):
                review=copy.deepcopy(self.data.review)
                review['spatial_measurements']=[old for old in review['spatial_measurements'] if old['event_id']!=m['event_id']]+[m]
                self.commit_review(review)
            self.measuring=False;self.show_frame(self.current)
        except Exception as exc:messagebox.showerror('Measurement',str(exc),parent=self.root)

    def temporal(self):
        if not self.current_event or not self.current or self.busy:return
        if not messagebox.askyesno('Timing reference',
            'Is this the FIRST saved-video frame showing the independently identifiable action for the selected raw click? '
            'Use beginning/middle/end actions. Do not use a generated ring as evidence.',parent=self.root):return
        m={'event_id':self.current_event['event_id'],'observed_seconds':self.current['seconds'],
           'frame_index':self.current['index'],'video_fingerprint':self.data.video.fingerprint,
           'uncertainty_ms':1000*max(1/self.data.video.info['fps'],self.current['seconds']-self.data.video.pts[max(0,self.current['index']-1)])}
        review=copy.deepcopy(self.data.review)
        review['temporal_measurements']=[old for old in review['temporal_measurements'] if old['event_id']!=m['event_id']]+[m]
        self.commit_review(review)

    def inspected(self):
        if not self.current_event or self.busy:return
        mapping=self.data.mapping(self.current_event)
        if not mapping:return
        review=copy.deepcopy(self.data.review)
        review['visually_inspected_mapping_ids']=list(set(review['visually_inspected_mapping_ids']+[mapping['id']]))
        self.commit_review(review)

    def label_class(self):
        if not self.current_event or self.busy:return
        expected=simpledialog.askstring('Controlled trial ground truth','Expected class for this known click: inside / outside / uncertain. Use the trial notes, not the classifier output.',parent=self.root)
        if expected not in ('inside','outside','uncertain'):return
        review=copy.deepcopy(self.data.review)
        labels=review.get('classification_labels',[])
        review['classification_labels']=[m for m in labels if m['event_id']!=self.current_event['event_id']]+[{'event_id':self.current_event['event_id'],'expected':expected}]
        self.commit_review(review)

    def apply_offset(self):
        if not self.data or self.busy:return
        qa=self.data.qa()['temporal']
        if 'suggested_offset_seconds' not in qa:return
        if messagebox.askyesno('Time correction',f'Apply measured median offset {qa["offset_ms"]:.2f} ms to derived timeline only? Drift is diagnostic and is not automatically corrected.',parent=self.root):
            review=copy.deepcopy(self.data.review);review['time_correction']={'offset_seconds':qa['suggested_offset_seconds'],'drift_ppm':0}
            self.commit_review(review)

    def summary(self):
        if not self.data or self.busy:return
        qa=self.data.qa()
        text=f'Video: {len(self.data.video.pts)} decoded frame timestamps\nMouse: {len(self.data.events)} raw events\nSpatial: {qa["spatial"]["status"]}\nTemporal: {qa["temporal"]["status"]}\nSegments: {len(self.data.review["segments"])}; unknown gaps preserved\n'
        messagebox.showinfo('Evidence summary',text+json.dumps(qa,indent=2)[:2400],parent=self.root)

    def save(self):
        if self.data and not self.busy:self.commit_review(copy.deepcopy(self.data.review))

    def suggest(self):
        if not self.data:return
        self.status.set('Scanning for coarse visual-change suggestions; no semantic labels will be assigned…')
        def done(result):
            messagebox.showinfo('Suggestions only',json.dumps(result,indent=2)[:6000],parent=self.root)
            self.status.set('Suggestions saved to review_suggestions.json; create/correct segments manually.')
        self.work(lambda:suggest_transitions(self.data.video),done)

    def export(self):
        if not self.data:return
        smooth=messagebox.askyesno('Density outputs','Also export OPTIONAL smoothed versions? Raw counts and numbered clicks are always retained.',parent=self.root)
        self.status.set('Exporting per-state saved-video overlays, CSV and QA in background…')
        self.work(lambda:self.data.export(smoothed=smooth),lambda r:self.status.set(f'Export complete: research_analysis | {len(r["segments"])} segments | spatial {r["qa"]["spatial"]["status"]} | timing {r["qa"]["temporal"]["status"]}'))

    def external(self):
        if self.data:
            if os.name=='nt':os.startfile(self.data.video.path)
            else:messagebox.showinfo('Video path',str(self.data.video.path),parent=self.root)
