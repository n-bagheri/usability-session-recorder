"""OBS lifecycle and global input capture; no audio/video encoding."""
import json
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .core import estimate_origin
from .obs import wait_for_recording, wait_for_stopped
from .targeting import classify


class Session:
    def __init__(self, obs, root, mode, rect, geometry_provider, target=None, target_provider=None):
        self.obs, self.geometry = obs, geometry_provider
        self.target, self.target_provider = target, target_provider
        self.start_lock = threading.Lock()
        self.folder = Path(root) / (datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
        self.folder.mkdir(parents=True)
        self.lock = threading.Lock()
        self.listener = None
        self.stream = None
        self.active = False
        self.sequence = 0
        self.previous_foreground = None
        self.counts = {}
        self.target_counts = {"inside": 0, "outside": 0, "uncertain": 0}
        self.meta = {'schema_version': 2, 'target_calibration': target, 'mode': mode, 'capture_rect': rect,
                     'created_utc': datetime.now(timezone.utc).isoformat(),
                     'clock': 'time.perf_counter_ns',
                     'clock_domains': {'input':'Python hook-callback perf_counter_ns, not hardware event time','obs':'outputDuration milliseconds, request midpoint estimate','video':'saved stream presentation timestamps relative first video PTS','accuracy':'unverified until measured against saved frames'}, 'state': 'preparing',
                     'geometry_at_start': geometry_provider(),
                     'coordinate_space': 'physical desktop pixels',
                     'move_sampling_hz': None, 'input_policy': 'All mouse callbacks retained; no target filtering at capture',
                     'audio': 'Existing OBS configuration; mode is a label only'}
        self.sync = {'samples': [], 'markers': [], 'manual_correction_ms': 0, 'startup_observations': [],
                     'method': 'OBS outputDuration midpoint estimate; not frame accurate',
                     'correction_convention': 'video_seconds=(event_ns-origin_ns)/1e9+manual_correction_ms'}
        self.save()

    def save(self):
        for name, data in [('metadata', self.meta), ('sync', self.sync)]:
            path = self.folder/f'{name}.json'
            temp = path.with_suffix('.tmp')
            temp.write_text(json.dumps(data, indent=2), encoding='utf-8')
            temp.replace(path)

    def event(self, kind, x=None, y=None, **extra):
        now = time.perf_counter_ns()
        with self.lock:
            if not self.active:
                return
            self.sequence += 1
            event = {'event_id': str(self.sequence), 'type': kind, 'monotonic_ns': now, **extra}
            if x is not None:
                event.update(x=x, y=y)
            try:
                event.update(self.geometry())
            except Exception as exc:
                event['geometry_error'] = str(exc)
            if x is not None:
                snapshot = None
                observed_before = time.perf_counter_ns()
                if self.target and self.target_provider:
                    try:
                        snapshot = self.target_provider(self.target['identity']['hwnd'], x, y)
                    except Exception as exc:
                        snapshot = {'error': str(exc)}
                event['target_observation'] = snapshot
                event['observation_interval_ns'] = [observed_before, time.perf_counter_ns()]
                try:
                    event['target'] = classify(x, y, self.target, snapshot)
                except Exception as exc:
                    event['target'] = {'classification':'uncertain','reason':'classification_error','error':str(exc)}
                if event['observation_interval_ns'][1]-now > 100_000_000:
                    if snapshot is not None:snapshot['observation_delayed']=True
                    event['target'].update(classification='uncertain',reason='geometry_observation_delayed_over_100ms')
                current_foreground = (snapshot or {}).get('foreground_root')
                if kind=='click' and extra.get('pressed') and self.target:
                    event['activation'] = 'possible_activation_click' if self.previous_foreground not in (None,self.target['identity']['hwnd']) else 'not_identified'
                    event['previous_observed_foreground'] = self.previous_foreground
                    event['activation_note'] = 'Prior observed focus is not proof of OS dispatch; an inside activation click is retained'
                self.previous_foreground = current_foreground
            try:
                self.stream.write(json.dumps(event)+'\n')
                self.stream.flush()
                self.counts[kind] = self.counts.get(kind, 0)+1
                if 'target' in event:
                    self.target_counts[event['target']['classification']] += 1
            except Exception as exc:
                self.meta['input_error'] = str(exc)

    def sample(self):
        before = time.perf_counter_ns()
        status = self.obs.get_record_status()
        after = time.perf_counter_ns()
        if not status.output_active or status.output_paused:
            raise RuntimeError('OBS recording is inactive or paused; do not pause externally')
        self._add_sample(before, after, status.output_duration)

    def _add_sample(self, before, after, duration):
        sample = dict(estimate_origin(before, after, duration),
                      before_ns=before, after_ns=after, output_duration_ms=duration)
        self.sync['samples'].append(sample)
        self.sync['origin_ns'] = min(self.sync['samples'], key=lambda s:s['half_rtt_ns'])['origin_ns']
        self.save()

    def confirm_recording(self):
        def observe(data):
            self.sync['startup_observations'].append(data)
            self.save()
        if not self.active or not self.meta.get('owns_recording_attempt'):
            raise RuntimeError('No live recording attempt to confirm')
        try:
            before, after, duration = wait_for_recording(self.obs.get_record_status, observe)
        except Exception:
            self.meta['state'] = 'status_uncertain'
            self.save()
            raise
        self._add_sample(before, after, duration)
        self.meta['state'] = 'recording'
        self.save()

    def start(self):
        if not self.start_lock.acquire(blocking=False):
            raise RuntimeError('Start is already in progress')
        try:
            if self.meta.get('owns_recording_attempt') or self.active:
                raise RuntimeError('Start was already attempted. Check OBS or stop this session; no duplicate request sent.')
            return self._start()
        finally:
            self.start_lock.release()

    def _start(self):
        from pynput import mouse
        if self.obs.get_record_status().output_active:
            raise RuntimeError('OBS is already recording; stop it before starting a session')
        self.stream = (self.folder/'events.jsonl').open('a', encoding='utf-8')
        self.active = True
        try:
            self.listener = mouse.Listener(
                on_move=lambda x,y:self.event('move',x,y),
                on_click=lambda x,y,b,p:self.event('click',x,y,button=str(b),pressed=p),
                on_scroll=lambda x,y,dx,dy:self.event('scroll',x,y,dx=dx,dy=dy))
            self.listener.start()
            wait_listener_ready(self.listener)
            self.meta['start_request_ns'] = time.perf_counter_ns()
            self.meta['owns_recording_attempt'] = True
            self.obs.start_record()
            self.meta['start_response_ns'] = time.perf_counter_ns()
            self.meta['state'] = 'starting'
            self.save()
            self.confirm_recording()
        except Exception as exc:
            self.meta['error'] = str(exc)
            # StartRecord may have succeeded even if its response was lost.
            # Keep capture alive until explicit Stop/recovery; never silently orphan OBS.
            self.meta['state'] = 'start_uncertain'
            if not self.meta.get('owns_recording_attempt'):
                self.active = False
                if self.listener:
                    self.listener.stop()
                self.stream.close()
                self.meta['state'] = 'failed'
            self.save()
            raise

    def marker(self):
        now = time.perf_counter_ns()
        self.event('sync_marker', marker_number=len(self.sync['markers'])+1)
        self.sync['markers'].append({'monotonic_ns': now, 'number': len(self.sync['markers'])+1})
        self.save()

    def stop(self):
        if not self.meta.get('owns_recording_attempt'):
            raise RuntimeError('This session has not attempted to start OBS; no recording was stopped')
        if self.meta['state'] != 'stopped':
            try:
                self.sample()
            except Exception as exc:
                self.meta['sync_warning'] = str(exc)
        # One StopRecord, followed by settled inactive confirmation. A lost/late
        # confirmation must not send a second stop against an already stopping output.
        if self.meta['state'] != 'stopped':
            try:
                if not self.meta.get('stop_acknowledged'):
                    self.meta['state']='stopping'
                    result = self.obs.stop_record()
                    self.meta['obs_output_path'] = result.output_path
                    self.meta['stop_acknowledged']=True
                    self.save()
                def observe(data):
                    self.sync.setdefault('stop_observations',[]).append(data)
                    self.save()
                wait_for_stopped(self.obs.get_record_status,observe)
            except Exception:
                self.meta['state'] = 'stop_uncertain'
                self.save()
                raise
        self.meta['stop_response_ns'] = time.perf_counter_ns()
        self.active = False
        if self.listener:
            self.listener.stop()
            self.listener.join(timeout=3)
        with self.lock:
            if self.stream:
                self.stream.close()
        self.meta['event_counts'] = self.counts
        self.meta['target_counts'] = self.target_counts
        self.meta['state'] = 'stopped'
        self.save()
        source = self.meta.get('obs_output_path')
        if source:
            source = Path(source)
            wait_for_stable_file(source)
            destination = self.folder / ('video'+source.suffix)
            if not destination.exists():
                partial = destination.with_suffix(destination.suffix+'.partial')
                shutil.copy2(source, partial)
                partial.replace(destination)
            self.meta['video_file'] = destination.name
            self.meta['finalization'] = 'copied_pending_saved_video_decode_check'
        else:
            self.meta['video_warning'] = 'OBS was already stopped; recover video manually from OBS output folder'
        self.save()


    def task_boundary(self, beginning=True):
        self.event('analysis_boundary',boundary='begin' if beginning else 'end')
        self.meta['analysis_'+('begin' if beginning else 'end')+'_ns']=time.perf_counter_ns()
        self.save()


def wait_listener_ready(listener,timeout=3):
    ready=threading.Event();errors=[]
    def wait():
        try:listener.wait()
        except Exception as exc:errors.append(exc)
        finally:ready.set()
    threading.Thread(target=wait,daemon=True).start()
    if not ready.wait(timeout):raise RuntimeError('Windows mouse hook did not become ready before deadline; OBS was not started')
    if errors:raise errors[0]


def wait_for_stable_file(path,timeout=5):
    deadline=time.monotonic()+timeout;previous=None;stable=0
    while time.monotonic()<deadline:
        try:
            stat=path.stat();current=(stat.st_size,stat.st_mtime_ns)
            stable=stable+1 if current==previous and stat.st_size>0 else 0
            if stable>=2:return
            previous=current
        except FileNotFoundError:stable=0
        time.sleep(.15)
    raise RuntimeError(f'OBS video is missing, empty or still changing: {path}. Preserve original and retry copy.')
