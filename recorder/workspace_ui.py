"""Researcher-facing saved-session workspace; recording/advanced QA remain separate."""
import copy
import json
import os
import uuid
from pathlib import Path
import tkinter as tk
from tkinter import ttk,messagebox,simpledialog
from PIL import Image,ImageTk,ImageDraw
from .review_ui import ReviewWindow
from .review import write_review,segment_at
from .annotations import new_aoi,stamp,validate_annotations,split_view,merge_views,delete_view
from .corrections import geometry_key,fit_registration
from .regions import region_analysis
from .heatmaps import density_layers
from .ui_helpers import table,details,scroll_page


class AnalysisWorkspace(ReviewWindow):
    def __init__(self,parent,folder):
        # Retain the existing decoder, async worker, frame stepping and optional QA methods.
        self.root=tk.Toplevel(parent);self.root.title('Analyze a recorded session')
        self.root.geometry(f'{min(1250,self.root.winfo_screenwidth()-80)}x{min(900,self.root.winfo_screenheight()-100)}');self.root.minsize(660,480)
        self.data=None;self.current=None;self.current_event=None;self.measuring=False
        self.busy=False;self.playing=False;self.pending_click=None;self.frame_photo=None;self.frame_scale=1;self.offset=(0,0)
        import queue
        self.jobs=queue.Queue();self.closed=False;self.draw_mode=None;self.drag_start=None;self.draw_rect=None;self.redraw_id=None
        self.registration_anchors=[];self.registration_page=None;self.mark_registration=False;self.pending_start=None
        self.event_page=0;self._refreshing=False;self.region_results=None
        self.status=tk.StringVar(value='Opening recording…');self.quality=tk.StringVar(value='Video review is available without connecting OBS.')
        self.time=tk.DoubleVar(value=0);self.kind=tk.StringVar(value='Button presses');self.location=tk.StringVar(value='All locations')
        self.event_count=tk.StringVar();self.layer=tk.StringVar(value='Original image')
        self.show_clicks=tk.BooleanVar(value=True);self.show_moves=tk.BooleanVar(value=False);self.show_aois=tk.BooleanVar(value=True)
        self.opacity=tk.DoubleVar(value=.55);self.intensity=tk.DoubleVar(value=1);self.spread=tk.DoubleVar(value=0)
        top=ttk.Frame(self.root,padding=5);top.pack(fill='x')
        for label,action in [('Play / Pause',self.play),('Previous frame',lambda:self.step(-1)),('Next frame',lambda:self.step(1)),('Open video with audio',self.external),('Open session folder',self.open_folder)]:
            ttk.Button(top,text=label,command=action).pack(side='left',padx=2)
        ttk.Label(self.root,textvariable=self.quality,wraplength=1000).pack(fill='x',padx=8)
        pane=ttk.Panedwindow(self.root,orient='vertical');pane.pack(fill='both',expand=True)
        video=ttk.Frame(pane);lower=ttk.Frame(pane);pane.add(video,weight=3);pane.add(lower,weight=2)
        self.canvas=tk.Canvas(video,bg='#222',height=220,highlightthickness=0);self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Button-1>',self.canvas_click);self.canvas.bind('<B1-Motion>',self.drag);self.canvas.bind('<ButtonRelease-1>',self.release)
        overlay=ttk.Frame(video);overlay.pack(fill='x')
        for label,var in [('Clicks',self.show_clicks),('Mouse trail',self.show_moves),('Labeled regions',self.show_aois)]:
            ttk.Checkbutton(overlay,text=label,variable=var,command=self.repaint).pack(side='left')
        self.layer_choice=ttk.Combobox(overlay,textvariable=self.layer,values=['Original image','Movement density','Button-press density'],state='readonly',width=22)
        self.layer_choice.pack(side='left',padx=5);self.layer_choice.bind('<<ComboboxSelected>>',lambda _:self.heatmap_preview())
        self.slider=ttk.Scale(video,from_=0,to=1,variable=self.time);self.slider.pack(fill='x');self.slider.bind('<ButtonRelease-1>',lambda _:self.seek())
        self.timeline=tk.Canvas(video,height=30,bg='#555',highlightthickness=0);self.timeline.pack(fill='x');self.timeline.bind('<Button-1>',self.timeline_seek);self.timeline.bind('<Configure>',lambda _:self.draw_timeline())
        ttk.Label(video,textvariable=self.status,wraplength=1100).pack(fill='x')
        tabs=ttk.Notebook(lower);tabs.pack(fill='both',expand=True)
        event_tab=ttk.Frame(tabs,padding=5);view_tab=ttk.Frame(tabs,padding=5);region_tab=ttk.Frame(tabs,padding=5)
        heat_outer,heat_tab=scroll_page(tabs);advanced_outer,advanced=scroll_page(tabs)
        for frame,title in [(event_tab,'1. Review events'),(view_tab,'2. Define views'),(region_tab,'3. Label regions'),(heat_outer,'4. Heatmaps & export'),(advanced_outer,'Advanced Validation')]:tabs.add(frame,text=title)
        filters=ttk.Frame(event_tab);filters.pack(fill='x')
        for variable,options in [(self.kind,['Button presses','Button releases','Mouse movements','Scrolling','All mouse events']),
                                 (self.location,['All locations','Inside MapGen','Outside MapGen','Uncertain'])]:
            box=ttk.Combobox(filters,textvariable=variable,values=options,state='readonly',width=20);box.pack(side='left',padx=2);box.bind('<<ComboboxSelected>>',lambda _:self.filter_events())
        ttk.Button(filters,text='Previous 500',command=lambda:self.page(-1)).pack(side='left');ttk.Button(filters,text='Next 500',command=lambda:self.page(1)).pack(side='left')
        ttk.Label(event_tab,textvariable=self.event_count).pack(anchor='w')
        frame,self.clicks=table(event_tab,('Event','Time','Recorded action','Inferred location','Researcher region'),height=5);frame.pack(fill='both',expand=True)
        self.clicks.bind('<<TreeviewSelect>>',self.select_click)
        frame,self.segments=table(view_tab,('Start','End','View','Visual state','Layout stable'),height=4,selectmode='extended');frame.pack(fill='both',expand=True)
        self.segments.bind('<<TreeviewSelect>>',self.choose_view)
        self.actions(view_tab,[('Mark view start',self.mark_start),('Finish view here',self.finish_view),('Add / edit view',self.edit_segment),('Use this frame as reference',self.set_reference),('Split at playhead',self.split),('Merge selected views',self.merge),('Delete view',self.delete_segment)])
        ttk.Label(view_tab,text='Choose a view to show its saved reference frame. Repeated visits may reuse labels; unknown gaps stay unclassified.',wraplength=1000).pack(anchor='w')
        frame,self.aoi_tree=table(region_tab,('Region label','View','Valid from','Valid until','Status'),height=4);frame.pack(fill='both',expand=True)
        self.aoi_tree.bind('<<TreeviewSelect>>',self.select_region)
        self.actions(region_tab,[('Draw region',self.draw_region),('Edit region',self.edit_region),('Duplicate',self.duplicate_region),('Copy to current view',self.copy_region),('Delete region',self.delete_region),('Interaction summary',self.region_summary)])
        ttk.Label(region_tab,text='Regions are researcher-defined visual areas, not automatically identified page elements. Choose a view, then drag a rectangle on its frame.',wraplength=1000).pack(anchor='w')
        for label,var,maximum in [('Opacity',self.opacity,1),('Intensity',self.intensity,3),('Spread (0 = raw samples)',self.spread,4)]:
            row=ttk.Frame(heat_tab);row.pack(fill='x');ttk.Label(row,text=label,width=26).pack(side='left');ttk.Scale(row,from_=.1 if var is self.intensity else 0,to=maximum,variable=var,command=lambda _:self.repaint()).pack(side='left',fill='x',expand=True)
        self.actions(heat_tab,[('Save display settings',self.save_heat_settings),('Export images & reports',self.export),('Open exports folder',self.open_exports)])
        ttk.Label(heat_tab,text='Movement density counts received samples. Partial cursor-time estimates exclude long gaps; neither metric measures gaze or attention. Each stable view uses its own recorded frame.',wraplength=1000).pack(anchor='w',pady=8)
        ttk.Label(advanced,text='Optional quality measurements and corrections. Missing verification does not block qualitative review.',wraplength=1000).pack(anchor='w')
        self.actions(advanced,[('Measure target position',self.measure),('Mark visible action time',self.temporal),('Mark mapping visually inspected',self.inspected),('Apply measured time offset',self.apply_offset),('Quality details',self.summary),('Label expected event class',self.label_class)])
        self.actions(advanced,[('Participant start here',lambda:self.interval(True)),('Participant end here',lambda:self.interval(False)),('Suggest view changes',self.suggest)])
        ttk.Separator(advanced).pack(fill='x',pady=8)
        ttk.Label(advanced,text='Fix shifted click overlays: select two or more widely separated raw clicks in ONE view; mark each real position on its saved frame. Then draw the visible webpage boundary and apply. Original evidence is unchanged.',wraplength=1000).pack(anchor='w')
        self.registration_status=tk.StringVar(value='No correction references marked.')
        ttk.Label(advanced,textvariable=self.registration_status).pack(anchor='w')
        self.actions(advanced,[('Mark selected click position',self.mark_anchor),('Draw webpage area in video',self.draw_page),('Apply correction to this view',self.apply_registration),('Undo corrections in this view',self.undo_registration)])
        self.root.protocol('WM_DELETE_WINDOW',self.close);self.root.after(100,self.drain)
        from .research import ResearchSession
        self.work(lambda:ResearchSession(folder),self.loaded)

    def actions(self,parent,actions):
        frame=ttk.Frame(parent);frame.pack(fill='x',pady=4)
        for n,(label,action) in enumerate(actions):
            ttk.Button(frame,text=label,command=action).grid(row=n//3,column=n%3,sticky='ew',padx=2,pady=2)
        for n in range(3):frame.columnconfigure(n,weight=1)

    def loaded(self,data):
        self.data=data;self.slider.configure(to=data.video.info['duration'])
        settings=data.review.get('heatmap_settings',{})
        self.opacity.set(settings.get('opacity',.55));self.intensity.set(settings.get('intensity',1));self.spread.set(settings.get('smoothing_sigma_bins',0))
        self.refresh_lists();self.seek(0)

    def selected_view(self):
        if not self.data:return None
        selected=self.segments.selection()
        if selected:return next((s for s in self.data.review['segments'] if s['id']==selected[0]),None)
        if self.current:return segment_at(self.current['seconds'],self.data.review)[0]
        return None

    def choose_view(self,_=None):
        if self._refreshing or self.busy:return
        s=self.selected_view()
        if s:
            self.playing=False;self.draw_mode=None;self.layer.set('Original image');self.seek_reference(s)

    def seek_reference(self,s):
        try:self.seek(self.data.video.pts[self.data.video.interval_index(s.get('reference_seconds',s['start']),s['start'],s['end'])])
        except ValueError as exc:self.status.set(str(exc))

    def refresh_lists(self):
        if not self.data:return
        self._refreshing=True;selected=self.segments.selection();region_selection=self.aoi_tree.selection()
        for tree in (self.segments,self.aoi_tree):
            for row in tree.get_children():tree.delete(row)
        for s in self.data.review['segments']:
            self.segments.insert('','end',iid=s['id'],values=(f'{s["start"]:.2f}',f'{s["end"]:.2f}',s['view'],s['state'],'Confirmed' if s.get('stable') else 'Needs review'))
        for a in self.data.review.get('aois',[]):
            s=next(s for s in self.data.review['segments'] if s['id']==a['segment_id'])
            self.aoi_tree.insert('','end',iid=a['id'],values=(a['label'],s['view'],*a['valid_interval'],'Confirmed by researcher' if a.get('layout_confirmed') else 'Needs confirmation'))
        for row in selected:
            if self.segments.exists(row):self.segments.selection_add(row)
        for row in region_selection:
            if self.aoi_tree.exists(row):self.aoi_tree.selection_add(row)
        self.region_results=None
        self.root.after(200,self.update_assignments)
        self.refresh_events();self.draw_timeline()
        timing='unverified' if self.data.timing_available else 'unavailable — event times cannot yet be matched to video'
        self.quality.set('Recording facts and researcher annotations are separate. Alignment: review recommended. Timing: '+timing+'. Qualitative review remains available.')
        self._refreshing=False

    def refresh_events(self):
        if not self.data:return
        for row in self.clicks.get_children():self.clicks.delete(row)
        labels={r['event_id']:r['aoi_label'] or r['reason'].replace('_',' ') for r in (self.region_results or {}).get('events',[])}
        matches=[]
        class_key={'Inside MapGen':'inside','Outside MapGen':'outside','Uncertain':'uncertain'}.get(self.location.get())
        for e in self.data.events:
            if e['type'] not in ('move','click','scroll'):continue
            kind=self.kind.get()
            if kind=='Button presses' and not (e['type']=='click' and e.get('pressed')):continue
            if kind=='Button releases' and not (e['type']=='click' and not e.get('pressed')):continue
            if kind=='Mouse movements' and e['type']!='move':continue
            if kind=='Scrolling' and e['type']!='scroll':continue
            if class_key and e['target']['classification']!=class_key:continue
            matches.append(e)
        maximum=max(0,(len(matches)-1)//500);self.event_page=min(self.event_page,maximum)
        for e in matches[self.event_page*500:(self.event_page+1)*500]:
            t=self.data.time(e);action=e['type']
            if action=='click':action=e.get('button','Mouse').replace('Button.','').capitalize()+(' press' if e.get('pressed') else ' release')
            self.clicks.insert('','end',iid=e['event_id'],values=(e['event_id'],f'{t:.3f}s' if t is not None else 'Unknown',action,e['target']['classification'],labels.get(e['event_id'],'Unlabeled')))
        self.event_count.set(f'{len(matches)} matching recorded events. Page {self.event_page+1}/{maximum+1}; classifications are inferred, region labels are researcher annotations.')

    def filter_events(self):self.event_page=0;self.refresh_events()
    def page(self,delta):self.event_page=max(0,self.event_page+delta);self.refresh_events()

    def draw_timeline(self):
        if not self.data:return
        self.timeline.delete('all');width=max(1,self.timeline.winfo_width());duration=self.data.video.info['duration']
        for n,s in enumerate(self.data.review['segments']):
            x1,x2=width*s['start']/duration,width*s['end']/duration
            self.timeline.create_rectangle(x1,0,x2,28,fill=('#407690','#627442')[n%2],outline='white');self.timeline.create_text(x1+4,4,anchor='nw',text=s['view'],fill='white')
        x=width*self.time.get()/duration;self.timeline.create_line(x,0,x,30,fill='red',width=2)

    def timeline_seek(self,e):
        if self.data and not self.busy:self.playing=False;self.seek(e.x/max(1,self.timeline.winfo_width())*self.data.video.info['duration'])

    def show_frame(self,frame):
        self.current=frame;self.time.set(frame['seconds']);self.draw_timeline()
        self.repaint()
        if self.pending_click is not None:
            self.current_event=self.data.by_id[self.pending_click];self.pending_click=None
            t=self.data.time(self.current_event)
            if t is not None:self.seek(t)
            return
        if self.playing:self.root.after(180,self.play_next)

    def repaint(self):
        if not self.current or not self.data:return
        frame=self.current
        with Image.open(frame['path']) as source:image=source.convert('RGB')
        s=self.selected_view();draw=ImageDraw.Draw(image);preview_warning=None
        if self.layer.get()!='Original image' and s and s['start']<=frame['seconds']<s['end']:
            selected=[e for e in self.data.events_between(s['start'],s['end']) if e.get('target',{}).get('classification')=='inside' and segment_at(self.data.time(e),self.data.review)[1]!='administrative']
            ids={self.data.mapping(e)['id'] for e in selected if self.data.mapping(e)}
            suggestions=self.data.folder/'review_suggestions.json'
            changes=json.loads(suggestions.read_text(encoding='utf-8')).get('suggestions',[]) if suggestions.exists() else []
            changed=any(s['start']<c['seconds']<s['end'] for c in changes) and s.get('visual_suggestion_review')!='reviewed_no_spatial_change'
            zoom={((e.get('target_observation') or {}).get('viewport') or {}).get('zoom_percent') for e in selected}
            if s.get('stable') and len(ids)==1 and selected and not changed and len(zoom)<=1 and not any(e['type']=='scroll' or self.data.predict(e) is None for e in selected):
                kind='move' if self.layer.get()=='Movement density' else 'click'
                points=[self.data.predict(e) for e in selected if e['type']==kind and (kind!='click' or e.get('pressed'))]
                image,_,_,_=density_layers(image,points,self.opacity.get(),self.intensity.get(),self.spread.get());draw=ImageDraw.Draw(image)
            else:preview_warning='Heatmap needs one confirmed stable layout with valid mapping and no unresolved changes. Original image shown.'
        if self.show_moves.get() and not self.measuring and not self.mark_registration and not self.draw_mode:
            previous=None
            for e in self.data.events_between(frame['seconds']-.75,frame['seconds']+1e-9):
                t=self.data.time(e)
                p=self.data.predict(e)
                if e['type']=='move' and p is not None:
                    if previous and e['raw_line']==previous[0]+1:draw.line((tuple(previous[1]),tuple(p)),fill='cyan',width=2)
                    previous=(e['raw_line'],p)
                else:previous=None
        if self.show_clicks.get() and not self.measuring and not self.mark_registration and not self.draw_mode:
            for e in self.data.events_between(frame['seconds']-2/self.data.video.info['fps'],frame['seconds']+2/self.data.video.info['fps']):
                t=self.data.time(e)
                if e['type']=='click' and e.get('pressed') and t is not None and abs(t-frame['seconds'])<=2/self.data.video.info['fps']:
                    p=self.data.predict(e)
                    if p:x,y=p;draw.ellipse((x-6,y-6,x+6,y+6),outline='red',width=2)
        if self.show_aois.get() and not self.measuring and not self.mark_registration:
            for a in self.data.review.get('aois',[]):
                if s and a['segment_id']==s['id'] and a['valid_interval'][0]<=frame['seconds']<a['valid_interval'][1]:
                    x,y,w,h=a['rect'];color='cyan' if a.get('layout_confirmed') else 'orange'
                    draw.rectangle((x,y,x+w,y+h),outline=color,width=2);draw.text((x+3,y+3),a['label'],fill=color,stroke_fill='black',stroke_width=1)
        self.frame_scale=min(max(100,self.canvas.winfo_width())/image.width,max(100,self.canvas.winfo_height())/image.height)
        size=(max(1,int(image.width*self.frame_scale)),max(1,int(image.height*self.frame_scale)))
        self.frame_photo=ImageTk.PhotoImage(image.resize(size));self.canvas.delete('all');self.canvas.create_image(0,0,image=self.frame_photo,anchor='nw')
        mode='Draw a rectangle on this saved frame.' if self.draw_mode else 'Click the independent visible position.' if self.measuring or self.mark_registration else 'Original saved video; overlay positions may be unverified.'
        self.status.set(f'{frame["seconds"]:.3f}s / {self.data.video.info["duration"]:.2f}s — {preview_warning or mode}')

    def select_click(self,_=None):
        if not self.data or not self.clicks.selection():return
        if self.busy:self.pending_click=self.clicks.selection()[0];return
        self.current_event=self.data.by_id[self.clicks.selection()[0]];self.measuring=False;self.playing=False;self.draw_mode=None
        t=self.data.time(self.current_event)
        if t is None:self.status.set('Recorded event retained, but timing is unavailable. Browse the video qualitatively; no frame match is invented.');return
        self.layer.set('Original image');self.seek(t)

    def commit_review(self,value):
        if not self.data or self.busy:
            self.status.set('Please wait for the current decoding or analysis operation before saving annotations.')
            return False
        old=self.data.review
        try:
            validate_annotations(value,self.data.video.info['duration'],self.data.video.info['size'])
            self.data.review=value;self.data.reclassify()
            write_review(self.data.folder,value,self.data.video.info['duration'])
        except Exception as exc:
            self.data.review=old;self.data.reclassify();messagebox.showerror('Save annotations',str(exc),parent=self.root);return False
        self.refresh_lists();self.repaint();return True

    def mark_start(self):
        if self.current:self.pending_start=self.current['seconds'];self.status.set('View start marked. Seek to its end, then choose Finish view here.')

    def finish_view(self):
        if self.current and self.pending_start is not None:
            self.edit_bounds=(self.pending_start,self.current['seconds']);self.edit_segment();self.pending_start=None

    def edit_segment(self):
        # Reuse the existing plain time/label editor; numerical clock diagnostics stay advanced.
        if getattr(self,'edit_bounds',None):
            a,b=self.edit_bounds;self.edit_bounds=None
            if b<=a:messagebox.showerror('View','The end must be after the marked start.');return
            label=simpledialog.askstring('Name this view','View label (for example Home or Map editor):',parent=self.root)
            if not label:return
            state=simpledialog.askstring('Visual state','State label (for example panel closed):',initialvalue=label,parent=self.root)
            if not state:return
            stable=messagebox.askyesno('Layout consistency','Do the interface elements stay in the same positions throughout this interval? Use separate states for scrolling/panels/layout changes.',parent=self.root)
            review=copy.deepcopy(self.data.review);review['segments'].append({'id':uuid.uuid4().hex[:12],'start':a,'end':b,'view':label,'state':state,'stable':stable,'reference_seconds':a})
            self.commit_review(review);return
        super().edit_segment()

    def set_reference(self):
        s=self.selected_view()
        if not s or not self.current:return
        if not s['start']<=self.current['seconds']<s['end']:messagebox.showerror('Reference frame','Seek inside the selected view first.');return
        review=copy.deepcopy(self.data.review);next(v for v in review['segments'] if v['id']==s['id'])['reference_seconds']=self.current['seconds'];self.commit_review(review)

    def split(self):
        if not self.current or not self.selected_view():return
        try:self.commit_review(split_view(self.data.review,self.selected_view()['id'],self.current['seconds']))
        except ValueError as exc:messagebox.showerror('Split view',str(exc))

    def merge(self):
        if not self.data:return
        if messagebox.askyesno('Merge views','Merge the selected adjacent intervals? Their regions will need layout confirmation again.',parent=self.root):
            try:self.commit_review(merge_views(self.data.review,list(self.segments.selection()),True))
            except ValueError as exc:messagebox.showerror('Merge views',str(exc))

    def delete_segment(self):
        s=self.selected_view()
        if s and messagebox.askyesno('Delete view','Delete this view and its region/correction annotations? Raw evidence and annotation history are retained.',parent=self.root):self.commit_review(delete_view(self.data.review,s['id']))

    def draw_region(self,reset=True):
        if reset:self.redraw_id=None
        s=self.selected_view()
        if not s or not self.current:messagebox.showinfo('Define a view','Create/select a view first, then choose its representative frame.');return
        if not s['start']<=self.current['seconds']<s['end']:self.seek_reference(s);return
        self.playing=False;self.layer.set('Original image');self.draw_mode='aoi';self.measuring=False;self.mark_registration=False;self.repaint()

    def draw_page(self):
        if self.current:self.playing=False;self.draw_mode='page';self.layer.set('Original image');self.repaint()

    def canvas_click(self,event):
        if self.busy or not self.current:return
        x,y=event.x/self.frame_scale,event.y/self.frame_scale
        if not 0<=x<self.current['size'][0] or not 0<=y<self.current['size'][1]:return
        if self.draw_mode:self.drag_start=[x,y];return
        if self.mark_registration:
            e=self.current_event;s=e.get('target_observation') or {}
            if not s.get('client_rect'):messagebox.showerror('Correction','This event has no Chrome geometry to support reconstruction.');return
            self.registration_anchors.append({'event_id':e['event_id'],'desktop':[e['x'],e['y']],'observed':[x,y],
                'geometry_key':geometry_key(s),'client_rect':s['client_rect'],'frame':copy.deepcopy(self.current),'uncertainty_px':max(2,1/self.frame_scale)})
            self.mark_registration=False;self.registration_status.set(f'{len(self.registration_anchors)} reference clicks marked. Draw the webpage boundary, then apply to the selected view.');self.repaint();return
        super().canvas_click(event)

    def drag(self,event):
        if not self.drag_start or not self.draw_mode:return
        self.canvas.delete('selection');a,b=self.drag_start
        self.canvas.create_rectangle(a*self.frame_scale,b*self.frame_scale,event.x,event.y,outline='lime',width=2,tags='selection')

    def release(self,event):
        if not self.drag_start or not self.draw_mode:return
        w,h=self.current['size'];x,y=self.drag_start;u=max(0,min(w,event.x/self.frame_scale));v=max(0,min(h,event.y/self.frame_scale))
        rect=[min(x,u),min(y,v),abs(u-x),abs(v-y)];mode=self.draw_mode;self.drag_start=None;self.draw_mode=None
        if min(rect[2:])<2:self.status.set('Draw a region at least two image pixels wide/high.');return
        if mode=='page':self.registration_page=rect;self.registration_status.set('Webpage boundary marked. Apply after marking two separated reference clicks.');self.repaint();return
        old=next((a for a in self.data.review['aois'] if a['id']==self.redraw_id),None);self.redraw_id=None
        label=simpledialog.askstring('Label region','What interface area does this rectangle represent?',initialvalue=old['label'] if old else '',parent=self.root)
        if not label:self.repaint();return
        confirmed=messagebox.askyesno('Region validity','Does this rectangle cover the same interface element throughout this view? If it moves, scrolls or changes, define separate views or narrow the region time range.',parent=self.root)
        review=copy.deepcopy(self.data.review);item=new_aoi(self.selected_view(),label,rect,self.current,confirmed)
        if old:
            item.update(id=old['id'],semantic_id=old['semantic_id'],created_utc=old['created_utc'],valid_interval=old['valid_interval'],priority=old.get('priority',0))
            if not item['valid_interval'][0]<=self.current['seconds']<item['valid_interval'][1]:item['layout_confirmed']=False
            review['aois']=[a for a in review['aois'] if a['id']!=old['id']]
        review['aois'].append(item);self.commit_review(review)

    def chosen_region(self):
        return next((a for a in self.data.review['aois'] if self.aoi_tree.selection() and a['id']==self.aoi_tree.selection()[0]),None) if self.data else None

    def select_region(self,_=None):
        if self._refreshing or self.busy:return
        a=self.chosen_region()
        if a and a.get('reference_frame'):
            self.segments.selection_set(a['segment_id']);self.seek(a['reference_frame']['seconds'])

    def edit_region(self):
        a=self.chosen_region()
        if not a:return
        window=tk.Toplevel(self.root);window.title('Edit visual region');fields={}
        for key,default in [('label',a['label']),('semantic_id',a['semantic_id']),('start',a['valid_interval'][0]),('end',a['valid_interval'][1]),('priority',a.get('priority',0))]:
            ttk.Label(window,text={'semantic_id':'Reusable region ID (for future comparisons)','start':'Valid from (video seconds)','end':'Valid until (video seconds)'}.get(key,key)).pack(anchor='w')
            fields[key]=tk.StringVar(value=str(default));ttk.Entry(window,textvariable=fields[key],width=50).pack(fill='x')
        confirmed=tk.BooleanVar(value=a.get('layout_confirmed',False));ttk.Checkbutton(window,text='I confirm this region stays on the same visual element',variable=confirmed).pack()
        def save():
            try:
                review=copy.deepcopy(self.data.review);item=next(v for v in review['aois'] if v['id']==a['id'])
                item.update(label=fields['label'].get(),semantic_id=fields['semantic_id'].get(),valid_interval=[float(fields['start'].get()),float(fields['end'].get())],priority=int(fields['priority'].get()),layout_confirmed=confirmed.get(),updated_utc=stamp())
                if self.current and item['valid_interval'][0]<=self.current['seconds']<item['valid_interval'][1]:item['reference_frame']=copy.deepcopy(self.current)
                if self.commit_review(review):window.destroy()
            except ValueError as exc:messagebox.showerror('Region',str(exc),parent=window)
        self.actions(window,[('Save region',save),('Redraw on current frame',lambda:self.redraw_region(a,window))])

    def redraw_region(self,a,window):
        self.redraw_id=a['id'];window.destroy();self.draw_region(reset=False)

    def delete_region(self,confirm=True):
        a=self.chosen_region()
        if a and (not confirm or messagebox.askyesno('Delete region','Delete this annotation? Recording evidence stays unchanged.')):
            review=copy.deepcopy(self.data.review);review['aois']=[v for v in review['aois'] if v['id']!=a['id']];self.commit_review(review)

    def duplicate_region(self):self.copy_region(same_view=True)

    def copy_region(self,same_view=False):
        a=self.chosen_region();s=self.selected_view()
        if not a or not s or not self.current:return
        review=copy.deepcopy(self.data.review);item=copy.deepcopy(a);item.update(id=uuid.uuid4().hex[:12],label=a['label']+' copy',updated_utc=stamp())
        if not same_view:
            if not s['start']<=self.current['seconds']<s['end']:messagebox.showinfo('Copy region','Show a frame in the destination view first.');return
            item.update(segment_id=s['id'],valid_interval=[s['start'],s['end']],reference_frame=copy.deepcopy(self.current),layout_confirmed=False)
        review['aois'].append(item);self.commit_review(review)

    def update_assignments(self):
        if self.closed:return
        if self.busy:self.root.after(200,self.update_assignments);return
        if not self.data:return
        self.work(lambda:region_analysis(self.data),lambda result:self.assignments_ready(result))

    def assignments_ready(self,result):
        self.region_results=result;self.refresh_events()

    def region_summary(self):
        if not self.data or self.busy:return
        def display(result):
            window=tk.Toplevel(self.root);window.title('Region interaction summary')
            window.geometry(f'{min(1150,window.winfo_screenwidth()-100)}x{min(600,window.winfo_screenheight()-150)}')
            frame,tree=table(window,('Region','Assigned presses','Complete pairs','Move samples','Observed cursor seconds','First interaction','Status'),height=10)
            frame.pack(fill='both',expand=True)
            for r in result['regions']:
                tree.insert('','end',values=(r['label'],r['button_presses'],r['complete_button_pairs_from_presses'],r['movement_samples'],f'{r["bounded_cursor_occupancy_seconds"]:.3f}',r['first_interaction_seconds'],r['warning'] or 'Researcher-confirmed region; mapping review recommended'))
            text='Observed cursor time is partial: gaps over 0.25 seconds are unknown. Button pairs can include dragging. '+result['quality']
            ttk.Label(window,text=text,wraplength=1000).pack(fill='x',padx=8,pady=8)
        self.work(lambda:region_analysis(self.data),display)

    def mark_anchor(self):
        if not self.current_event or not self.current:return
        if self.current_event.get('type')!='click' or not self.current_event.get('pressed'):
            messagebox.showinfo('Reference click','Select a recorded button press whose real position is identifiable in the saved video.');return
        s=self.selected_view();t=self.data.time(self.current_event)
        if not s or t is None or not s['start']<=t<s['end']:messagebox.showinfo('Reference click','Select a recorded click in the intended view first.');return
        self.mark_registration=True;self.measuring=False;self.layer.set('Original image');self.playing=False;self.repaint()

    def apply_registration(self):
        s=self.selected_view()
        if not s or self.registration_page is None:messagebox.showinfo('Correction','Select a view, mark reference clicks and draw the webpage boundary first.');return
        try:
            for a in self.registration_anchors:
                t=self.data.time(self.data.by_id[a['event_id']])
                if t is None or not s['start']<=t<s['end']:raise ValueError('All reference clicks must be in this view')
            correction=fit_registration(s,self.registration_anchors,self.registration_page,self.data.video.fingerprint)
            review=copy.deepcopy(self.data.review)
            for c in review['mapping_corrections']:
                if c['segment_id']==s['id']:c['confirmed']=False
            review['mapping_corrections'].append(correction)
            if self.commit_review(review):self.registration_anchors=[];self.registration_page=None;self.registration_status.set('Correction saved in annotations. It is not independent proof of accuracy.')
        except ValueError as exc:messagebox.showerror('Correction',str(exc),parent=self.root)

    def undo_registration(self):
        s=self.selected_view()
        if not s:return
        review=copy.deepcopy(self.data.review)
        for c in review['mapping_corrections']:
            if c['segment_id']==s['id']:c['confirmed']=False
        self.commit_review(review)

    def heatmap_preview(self):
        s=self.selected_view()
        if not s:self.layer.set('Original image');messagebox.showinfo('Choose a view','Define/select a stable view first.');return
        if self.layer.get()!='Original image':self.seek_reference(s)
        else:self.repaint()

    def save_heat_settings(self):
        if not self.data:return
        review=copy.deepcopy(self.data.review);review['heatmap_settings']={'opacity':self.opacity.get(),'intensity':self.intensity.get(),'smoothing_sigma_bins':self.spread.get()};self.commit_review(review)

    def export(self):
        if not self.data or self.busy:return
        self.save_heat_settings();self.status.set('Exporting original view images, region reports and transparent/composited heatmaps…')
        def done(r):
            self.status.set(f'Export saved in research_analysis/{r["output_base"]}. Open exports folder to inspect images and reports.');self.root.after(200,self.update_assignments)
        self.work(lambda:self.data.export(smoothed=False),done)

    def summary(self):
        if not self.data:return
        qa=copy.deepcopy(self.data.qa());qa['video']['pts']=f'{len(self.data.video.pts)} presentation timestamps in review_cache/video_index.json'
        details(self.root,'Quality details — optional measurements',qa)

    def suggest(self):
        if not self.data or self.busy:return
        from .research import suggest_transitions
        self.work(lambda:suggest_transitions(self.data.video),lambda result:details(self.root,'Suggested transitions — researcher review required',result))

    def open_folder(self):
        if self.data and os.name=='nt':os.startfile(self.data.folder)

    def open_exports(self):
        if self.data and os.name=='nt':
            path=self.data.folder/'research_analysis'
            if path.exists():os.startfile(path)
