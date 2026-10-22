"""View/state-aware saved-video analysis. Raw recordings are never rewritten."""
import csv
import json
import math
import time
from collections import Counter,defaultdict
from pathlib import Path
from .targeting import classify,frame_point
from .obs_geometry import project,fingerprint
from .media import Video,run
from .qa import event_seconds,spatial_report,temporal_report
from .review import load_review,validate_review,segment_at,paired_clicks,save_json
from .corrections import active_registration,corrected_target,corrected_mapping
from .viewport import viewport_sanity


class ResearchSession:
    def __init__(self,folder):
        self.folder=Path(folder)
        self.meta=json.loads((self.folder/'metadata.json').read_text(encoding='utf-8'))
        sync_path=self.folder/'sync.json'
        self.sync=json.loads(sync_path.read_text(encoding='utf-8')) if sync_path.exists() else {}
        self.timing_available='origin_ns' in self.sync
        self.video=Video(folder)
        self.review=load_review(folder,self.video.info['duration'])
        validate_review(self.review,self.video.info['duration'])
        self.transition_intervals=[]
        journal=self.folder/'calibration_observations.jsonl'
        if journal.exists():
            observations=[json.loads(line) for line in journal.read_text(encoding='utf-8').splitlines() if line.strip()]
            for previous,current in zip(observations,observations[1:]):
                # Unchanged failed viewport observations remain uncertain through normal
                # classification, but are not geometry transitions. A separately fitted
                # registration can repair that stable failure without erasing changes.
                if previous.get('state_id')!=current.get('state_id'):
                    self.transition_intervals.append([previous['observed_ns'],current['observed_ns']])
        self.events=[]
        with (self.folder/'events.jsonl').open(encoding='utf-8') as stream:
            for line_no,line in enumerate(stream,1):
                if not line.strip():continue
                e=json.loads(line)
                e['event_id']=str(e.get('event_id',line_no))
                e['raw_line']=line_no
                e['recorded_target']=e.get('target')
                self.events.append(e)
        self.by_id={e['event_id']:e for e in self.events}
        legacy=self.folder/'frame_mapping.json'
        self.legacy_mapping=json.loads(legacy.read_text()) if legacy.exists() else None
        self.reclassify()

    def time(self,e):
        return event_seconds(e,self.sync,self.review) if self.timing_available else None

    def reclassify(self):
        for e in self.events:
            if 'x' not in e:continue
            snapshot=e.get('target_observation') or {}
            e['target']=classify(e['x'],e['y'],self.meta.get('target_calibration'),snapshot)
            v=snapshot.get('viewport')
            if v and v.get('method')!='manual_visual_explicit_confirmation' and snapshot.get('client_rect'):
                if not viewport_sanity(v['rect'],snapshot['client_rect'])[0]:
                    e['target'].update(classification='uncertain',reason='recorded_viewport_fails_current_sanity_policy')
            correction=active_registration(e,self.time(e),self.review,self.video.fingerprint)
            if correction:e['target']=corrected_target(e,correction,(self.meta.get('target_calibration') or {}).get('identity'))
            if any(a<=e['monotonic_ns']<=b for a,b in self.transition_intervals):
                e['target'].update(classification='uncertain',reason='calibration_transition_between_poll_observations')
        ordered=sorted([(self.time(e),n,e) for n,e in enumerate(self.events) if self.time(e) is not None],key=lambda row:(row[0],row[1]))
        self.event_times=[row[0] for row in ordered];self.timed_events=[row[2] for row in ordered]

    def events_between(self,start,end):
        import bisect
        return self.timed_events[bisect.bisect_left(self.event_times,start):bisect.bisect_left(self.event_times,end)]


    def mapping(self,e):
        correction=active_registration(e,self.time(e),self.review,self.video.fingerprint)
        if correction:return corrected_mapping(correction,self.video.info['size'])
        s=e.get('target_observation') or {}
        mapping=s.get('capture_mapping')
        if mapping and list(mapping['output_size'])==self.video.info['size']:
            return mapping
        if self.legacy_mapping and e.get('target',{}).get('layout_key')==self.legacy_mapping['layout_key']:
            lm=self.legacy_mapping
            if lm['frame_size']!=self.video.info['size']:return None
            sx,sy,sw,sh=lm['source_rect'];x,y,w,h=lm['frame_rect']
            return {'status':'computed','matrix':[w/sw,0,x-sx*w/sw,0,h/sh,y-sy*h/sh],
                    'source_clip_ltrb':[sx,sy,sx+sw,sy+sh], 'output_size':lm['frame_size'],
                    'content_size':lm['content_size'],'id':fingerprint(lm),'method':'legacy_explicit_manual_mapping'}
        return None

    def predict(self,e):
        if e.get('target',{}).get('classification')!='inside':return None
        mapping=self.mapping(e)
        if not mapping:return None
        return project(mapping,e['target']['local'])

    def qa(self):
        measurements=[]
        for m in self.review['temporal_measurements'] if self.timing_available else []:
            if m.get('video_fingerprint')!=self.video.fingerprint or m['event_id'] not in self.by_id:continue
            e=self.by_id[m['event_id']]
            item=dict(m,estimated_seconds=event_seconds(e,self.sync),corrected_seconds=self.time(e))
            measurements.append(item)
        # Duplicate readings of one action do not constitute independent timing evidence.
        measurements=list({m['event_id']:m for m in measurements}.values())
        mappings={self.mapping(e)['id'] for e in self.events if self.mapping(e) and self.predict(e) is not None}
        per_mapping={}
        for mapping_id in mappings:
            ms=[m for m in self.review['spatial_measurements'] if m['mapping_id']==mapping_id]
            item=spatial_report(ms,self.video.info['size'],self.video.fingerprint)
            if item['status']=='computed' and mapping_id in self.review['visually_inspected_mapping_ids']:
                item['status']='visually_inspected_not_measured'
            per_mapping[mapping_id]=item
        spatial=list(per_mapping.values())[0].copy() if len(per_mapping)==1 else {'status':'computed' if mappings else 'unavailable'}
        if len(per_mapping)>1:
            statuses=[m['status'] for m in per_mapping.values()]
            if all(s=='experimentally_verified' for s in statuses):spatial['status']='experimentally_verified'
            elif 'experimentally_verified' in statuses:spatial['status']='partially_verified'
            elif 'failed' in statuses:spatial['status']='failed'
        spatial['per_mapping']=per_mapping
        truth=self.review.get('classification_labels',[])
        comparisons=[]
        for label in truth:
            e=self.by_id.get(str(label['event_id']))
            if e and 'target' in e:
                comparisons.append({'event_id':e['event_id'],'expected':label['expected'],'observed':e['target']['classification'],'reason':e['target']['reason']})
        classification_qa={'status':'operator_labeled' if comparisons else 'unverified',
            'environment':self.review.get('validation_environment','unverified'),'comparisons':comparisons,
            'false_positives':sum(p['expected']=='outside' and p['observed']=='inside' for p in comparisons),
            'false_negatives':sum(p['expected']=='inside' and p['observed']!='inside' for p in comparisons),
            'uncertain_observations':sum(p['observed']=='uncertain' for p in comparisons)}
        return {'classification':classification_qa,'spatial':spatial,'temporal':temporal_report(measurements,self.video.info['duration'],self.video.info['fps']),
                'video':self.video.info,'calibration':'computed' if self.meta.get('target_calibration') else 'unavailable',
                'timing_available':self.timing_available,'mapping_corrections':self.review.get('mapping_corrections',[]),
                'note':'Saved-video measurements are operator evidence, not automatic proof of accuracy'}

    def measure_spatial(self,event_id,frame,observed):
        e=self.by_id[str(event_id)]
        predicted=self.predict(e)
        mapping=self.mapping(e)
        if predicted is None:raise ValueError('Event has no valid, unclipped frame mapping')
        if frame['video_fingerprint']!=self.video.fingerprint:raise ValueError('Frame is from another video')
        a,b,c,d,f,g=mapping['matrix']; w,h=mapping['content_size']
        rect=[c,g,a*w,f*h]
        return {'event_id':e['event_id'],'mapping_id':mapping['id'],'predicted':predicted,
                'observed':list(observed),'error_px':math.dist(predicted,observed),
                'frame_index':frame['index'],'frame_seconds':frame['seconds'],
                'video_fingerprint':self.video.fingerprint,'viewport_frame_rect':rect}

    def export(self,smoothed=False):
        from PIL import Image,ImageDraw
        outroot=self.folder/'research_analysis'
        out=outroot/f'run-{time.time_ns()}'
        out.mkdir(parents=True,exist_ok=False)
        segments=defaultdict(list)
        counts=Counter(included=0,excluded=0,uncertain=0)
        rows=[]
        unknown=admin=0
        for e in self.events:
            if e.get('type') not in ('move','click','scroll'):continue
            t=self.time(e)
            seg,category=segment_at(t,self.review) if t is not None else (None,'timing_unavailable')
            c=e['target']['classification']
            counts[{'inside':'included','outside':'excluded','uncertain':'uncertain'}[c]]+=1
            if category=='unknown':unknown+=1
            if category=='administrative':admin+=1
            point=self.predict(e)
            mapping=self.mapping(e)
            rows.append({'event_id':e['event_id'],'raw_line':e['raw_line'],'monotonic_ns':e['monotonic_ns'],
                         'video_seconds':t,'type':e['type'],'pressed':e.get('pressed'),'button':e.get('button'),
                         'classification':c,'recorded_classification':(e.get('recorded_target') or {}).get('classification'),
                         'classification_derivation':e['target'].get('derivation','current_policy_replay'),'reason':e['target']['reason'],'activation':e.get('activation','not_identified'),
                         'interval_category':category,'segment_id':seg['id'] if seg else '',
                         'view':seg['view'] if seg else 'Unknown','state':seg['state'] if seg else 'Unknown',
                         'local_x':e['target'].get('local',[None,None])[0],'local_y':e['target'].get('local',[None,None])[1],
                         'frame_x':point[0] if point else None,'frame_y':point[1] if point else None,
                         'mapping_id':mapping['id'] if mapping else None,
                         'browser_title_digest':(e.get('target_observation') or {}).get('title_digest')})
            if c=='inside' and seg:segments[seg['id']].append(e)
        if rows:
            with (out/'events.csv').open('w',newline='',encoding='utf-8') as f:
                writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
        visual_suggestions=suggest_transitions(self.video,step=1,threshold=.035)
        metrics=[];views=defaultdict(lambda:{'dwell_seconds':0,'click_presses':0,'moves':0})
        for seg in self.review['segments']:
            selected=segments[seg['id']]
            start=max(seg['start'],self.review['analysis_interval'][0]);end=min(seg['end'],self.review['analysis_interval'][1])
            dwell=max(0,end-start)
            clicks=[e for e in selected if e['type']=='click' and e.get('pressed')]
            moves=[e for e in selected if e['type']=='move']
            distance=0
            for a,b in zip(moves,moves[1:]):
                if (self.time(b)-self.time(a)<=.5 and b['raw_line']==a['raw_line']+1 and a['target']['layout_key']==b['target']['layout_key']):
                    distance+=math.dist(a['target']['local'],b['target']['local'])
            ref_index=self.video.interval_index(seg.get('reference_seconds',seg['start']),seg['start'],seg['end'])
            clean_frame=self.video.frame(self.video.pts[ref_index])
            import shutil
            clean_name=f'segment-{seg["id"]}-original.png'
            shutil.copy2(clean_frame['path'],out/clean_name)
            item={'clean_frame':clean_name,'reference_frame':clean_frame,'id':seg['id'],'view':seg['view'],'state':seg['state'],'dwell_seconds':dwell,
                  'click_presses':len(clicks),'button_presses':len(clicks),'moves':len(moves),'movement_path_physical_px':distance,
                  'raw_event_ids':[e['event_id'] for e in selected], 'outputs':[]}
            views[seg['view']]['dwell_seconds']+=dwell;views[seg['view']]['click_presses']+=len(clicks);views[seg['view']]['moves']+=len(moves)
            mappings={self.mapping(e)['id'] for e in selected if self.mapping(e)}
            unmapped=sum(self.predict(e) is None for e in selected)
            item['unmapped_or_clipped_events']=unmapped
            visual_changes=[s for s in visual_suggestions['suggestions'] if seg['start']<s['seconds']<seg['end']]
            scroll_present=any(e['type']=='scroll' for e in selected)
            zoom_values={((e.get('target_observation') or {}).get('viewport') or {}).get('zoom_percent') for e in selected}
            item['visual_change_suggestions']=visual_changes
            item['scroll_or_detected_zoom_change']=scroll_present or len(zoom_values)>1
            stable_guard=(not item['scroll_or_detected_zoom_change'] and
                          (not visual_changes or seg.get('visual_suggestion_review')=='reviewed_no_spatial_change'))
            # No screenshot aggregation unless a researcher explicitly marked a stable state.
            if seg.get('stable') and stable_guard and len(mappings)==1 and not unmapped and selected:
                frame=clean_frame
                with Image.open(frame['path']) as image:
                    image=image.convert('RGB')
                prefix=f'segment-{seg["id"]}'
                for kind,items in [('click',clicks),('move',moves)]:
                    points=[self.predict(e) for e in items]
                    name=f'{prefix}-{kind}-density.png'
                    render_density(image,points,out/name,smoothed=False,settings=self.review.get('heatmap_settings'))
                    item['outputs'].append(name)
                    if smoothed:
                        name=f'{prefix}-{kind}-smoothed.png'
                        render_density(image,points,out/name,smoothed=True,settings=self.review.get('heatmap_settings'))
                        item['outputs'].append(name)
                from .heatmaps import cursor_time_points
                time_points,time_weights=cursor_time_points(self,selected)
                item['partial_cursor_time_seconds']=sum(time_weights)
                if time_points:
                    render_density(image,time_points,out/f'{prefix}-partial-cursor-time.png',settings=self.review.get('heatmap_settings'),weights=time_weights)
                drawing=ImageDraw.Draw(image)
                for n,e in enumerate(clicks,1):
                    x,y=self.predict(e);drawing.ellipse((x-6,y-6,x+6,y+6),outline='red',width=2);drawing.text((x+8,y),str(n),fill='red')
                name=f'{prefix}-numbered-clicks.png';image.save(out/name);item['outputs'].append(name)
                item['reference_frame']=frame
                item['warning']='Stable visual state is researcher-declared. No semantic/visual equivalence is inferred; small-click samples should use numbered overlay.'
            else:
                item['warning']='No static overlay: state not confirmed stable, visual/scroll/zoom change flagged, mapping changed, or events clipped/unmapped. Inspect per-click actual frames instead.'
            outlines=[a for a in self.review.get('aois',[]) if a['segment_id']==seg['id'] and a.get('reference_frame') and a['reference_frame'].get('video_fingerprint')==self.video.fingerprint and a['valid_interval'][0]<=clean_frame['seconds']<a['valid_interval'][1]]
            if outlines:
                with Image.open(clean_frame['path']) as source:region_image=source.convert('RGB')
                draw=ImageDraw.Draw(region_image)
                for region in outlines:
                    x,y,w,h=region['rect'];draw.rectangle((x,y,x+w,y+h),outline='cyan',width=2);draw.text((x+3,y+3),region['label'],fill='cyan',stroke_fill='black',stroke_width=1)
                item['region_outline_image']=f'segment-{seg["id"]}-regions.png';region_image.save(out/item['region_outline_image'])
            metrics.append(item)
        # Exact saved-video context per click, with at most a one-second preceding trajectory
        # from the same annotated segment/mapping. Unknown intervals never borrow another view's image.
        contextual=[]
        for e in self.events:
            if e['type']!='click' or not e.get('pressed') or self.predict(e) is None:continue
            t=self.time(e)
            if t is None or not 0<=t<=self.video.info['duration']:continue
            seg,category=segment_at(t,self.review) if t is not None else (None,'timing_unavailable')
            if category=='administrative':continue
            frame=self.video.frame(t)
            with Image.open(frame['path']) as image:image=image.convert('RGB')
            draw=ImageDraw.Draw(image)
            mapping=self.mapping(e)
            trajectory=[];previous_line=None
            for m in self.events:
                if m['type']!='move' or self.time(m) is None or not t-1<=self.time(m)<=t:continue
                ms,mc=segment_at(self.time(m),self.review)
                mm=self.mapping(m)
                p=self.predict(m)
                if p and mm and mm['id']==mapping['id'] and seg and ms and ms['id']==seg['id']:
                    if previous_line is not None and m['raw_line']!=previous_line+1:
                        if len(trajectory)>1:draw.line(trajectory,fill='cyan',width=2)
                        trajectory=[]
                    trajectory.append(tuple(p));previous_line=m['raw_line']
            if len(trajectory)>1:draw.line(trajectory,fill='cyan',width=2)
            x,y=self.predict(e);draw.ellipse((x-7,y-7,x+7,y+7),outline='red',width=3)
            draw.text((8,8),f'Event {e["event_id"]} @ frame PTS {frame["seconds"]:.3f}s — alignment/timing: see QA',fill='orange',stroke_fill='black',stroke_width=1)
            name=f'event-{e["raw_line"]:07d}.png';image.save(out/name)
            contextual.append({'event_id':e['event_id'],'video_seconds':t,'frame':frame,'image':name,
                               'segment_id':seg['id'] if seg else None,'view':seg['view'] if seg else 'Unknown'})
        from .regions import region_analysis
        regions=region_analysis(self)
        for region in regions['regions']:
            region['reference_exports']=None
            a=region['annotation'];ref=a.get('reference_frame')
            if ref and ref.get('video_fingerprint')==self.video.fingerprint:
                frame=self.video.frame(ref['seconds'])
                with Image.open(frame['path']) as source:region_image=source.convert('RGB')
                original=f'region-{a["id"]}-original.png';region_image.save(out/original)
                draw=ImageDraw.Draw(region_image);x,y,w,h=a['rect'];draw.rectangle((x,y,x+w,y+h),outline='cyan',width=2);draw.text((x+3,y+3),a['label'],fill='cyan',stroke_fill='black',stroke_width=1)
                annotated=f'region-{a["id"]}-labeled.png';region_image.save(out/annotated)
                region['reference_exports']={'original':original,'labeled':annotated,'frame':frame}
        save_json(out/'regions.json',regions)
        if regions['events']:
            with (out/'region-events.csv').open('w',newline='',encoding='utf-8') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(regions['events'][0]));writer.writeheader();writer.writerows({k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in row.items()} for row in regions['events'])
        if regions['regions']:
            with (out/'region-summary.csv').open('w',newline='',encoding='utf-8') as stream:
                writer=csv.DictWriter(stream,fieldnames=list(regions['regions'][0]));writer.writeheader();writer.writerows({k:json.dumps(v) if isinstance(v,(list,dict)) else v for k,v in row.items()} for row in regions['regions'])
        complete,unmatched=paired_clicks(self.events)
        report={'version':1,'output_base':out.name,'video_fingerprint':self.video.fingerprint,'classification':dict(counts),'classification_reasons':dict(Counter(row['reason'] for row in rows)),
                'calibration_transition_intervals_ns':self.transition_intervals,
                'unknown_events':unknown,'administrative_events':admin,'segments':metrics,'views':dict(views),
                'complete_global_click_pairs':len(complete),'unmatched_button_events':len(unmatched),
                'complete_inside_press_pairs':sum(a.get('target',{}).get('classification')=='inside' for a,b in complete),
                'unknown_dwell_seconds':max(0,self.review['analysis_interval'][1]-self.review['analysis_interval'][0]-sum(s['dwell_seconds'] for s in metrics)),
                'participant_interval_classification':dict(Counter(row['classification'] for row in rows if row['interval_category']!='administrative')),
                'contextual_clicks':contextual,'regions':regions,'qa':self.qa(),
                'timing_available':self.timing_available,'assignment_warning':None if self.timing_available else 'Mouse/video timing unavailable; no event-to-view or region assignment was invented',
                'annotation_schema':2,'mapping_corrections':self.review.get('mapping_corrections',[]),
                'heatmap_settings':self.review.get('heatmap_settings',{}),
                'density_metric':{'frame_size':self.video.info['size'],'grid_shape':[128,128],'units':'received events per 128x128 frame-space bin','normalization':'per-image maximum; compare counts, not color across images',
                                  'smoothing':'researcher-adjustable Gaussian sigma in bins, count-preserving; raw CSV and transparent layers retained',
                                  'interpretation':'mouse event density, not dwell time, gaze or visual attention'},
                'raw_files':['events.jsonl','metadata.json','sync.json'],'review_file':'review.json',
                'visual_change_suggestions':visual_suggestions,
                'aggregation_policy':'Separate per-segment stable states. Never aggregate repeated/different visual states automatically.'}
        save_json(out/'report.json',report)
        save_json(out/'qa.json',report['qa'])
        save_json(outroot/'qa.json',report['qa'])
        save_json(outroot/'report.json',report)
        legacy_path=self.folder/'analysis.json'
        analysis=json.loads(legacy_path.read_text(encoding='utf-8')) if legacy_path.exists() else {}
        if 'alignment' in analysis and 'legacy_alignment' not in analysis:analysis['legacy_alignment']=analysis['alignment']
        analysis['alignment']=dict(report['qa']['spatial'],qa_file='research_analysis/qa.json')
        analysis['research_analysis']={'report':'research_analysis/report.json','events':f'research_analysis/{out.name}/events.csv',
                                       'temporal_status':report['qa']['temporal']['status'],'segments':len(metrics)}
        save_json(legacy_path,analysis)
        return report


def render_density(reference,points,path,smoothed=False,settings=None,weights=None):
    import numpy as np
    from PIL import ImageDraw
    from .heatmaps import density_layers
    settings=settings or {}
    sigma=settings.get('smoothing_sigma_bins',0) if not smoothed else max(1,settings.get('smoothing_sigma_bins',0))
    image,overlay,grid,shown=density_layers(reference,points,settings.get('opacity',.55),settings.get('intensity',1),sigma,weights)
    np.savetxt(Path(path).with_suffix('.csv'),grid,delimiter=',',fmt='%.8f' if weights is not None else '%.0f')
    if sigma:np.savetxt(Path(path).with_suffix('.smoothed-counts.csv'),shown,delimiter=',',fmt='%.8f')
    overlay.save(Path(path).with_name(Path(path).stem+'-transparent.png'))
    units='observed cursor seconds' if weights is not None else 'events'
    draw=ImageDraw.Draw(image)
    draw.text((8,image.height-24),f'{grid.sum():.3f} {units} | max {grid.max():.3f}/bin | spread {sigma:g}',fill='white',stroke_fill='black',stroke_width=1)
    image.save(path)


def suggest_transitions(video,step=2,threshold=.08):
    """Coarse visual differences only; no semantic state/URL inference."""
    import numpy as np
    raw=run(['ffmpeg','-v','error','-i',str(video.path),'-vf',f'fps=1/{step},scale=64:36,format=gray',
             '-f','rawvideo','pipe:1'])
    size=64*36
    frames=np.frombuffer(raw[:len(raw)//size*size],dtype=np.uint8).reshape((-1,36,64))
    suggestions=[]
    for n in range(1,len(frames)):
        score=float(np.abs(frames[n].astype(float)-frames[n-1]).mean()/255)
        if score>=threshold:suggestions.append({'seconds':n*step,'score':score,'uncertainty_seconds':step,
                                                'status':'suggestion_only','semantic_label':None})
    title_signals=[]
    sync_path=video.folder/'sync.json'
    sync=json.loads(sync_path.read_text(encoding='utf-8')) if sync_path.exists() else {}
    review=load_review(video.folder,video.info['duration'])
    previous=None
    with (video.folder/'events.jsonl').open(encoding='utf-8') as stream:
        for line in stream:
            if not line.strip():continue
            event=json.loads(line)
            digest=(event.get('target_observation') or {}).get('title_digest')
            if 'origin_ns' in sync and previous is not None and digest is not None and digest!=previous:
                title_signals.append({'seconds':event_seconds(event,sync,review),'signal':'browser_title_digest_changed','semantic_label':None})
            if digest is not None:previous=digest
    result={'browser_title_signals':title_signals,'method':'coarse mean absolute grayscale difference','step_seconds':step,'threshold':threshold,
            'warning':'Changes may be loading, animation, pan/zoom, scroll or another view. Researcher must correct boundaries and label states.',
            'suggestions':suggestions}
    save_json(video.folder/'review_suggestions.json',result)
    return result
