"""OBS lifecycle and global input capture; no audio/video encoding."""
import json
import shutil
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .core import estimate_origin


class Session:
    def __init__(self, obs, root, mode, rect, geometry_provider):
        self.obs, self.geometry = obs, geometry_provider
        self.folder = Path(root) / (datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
        self.folder.mkdir(parents=True)
        self.lock = threading.Lock()
        self.listener = None
        self.stream = None
        self.active = False
        self.counts = {}
        self.last_move = 0
        self.meta = {'schema_version': 1, 'mode': mode, 'capture_rect': rect,
                     'created_utc': datetime.now(timezone.utc).isoformat(),
                     'clock': 'time.perf_counter_ns', 'state': 'preparing',
                     'geometry_at_start': geometry_provider(),
                     'coordinate_space': 'physical desktop pixels',
                     'move_sampling_hz': 60,
                     'audio': 'Existing OBS configuration; mode is a label only'}
        self.sync = {'samples': [], 'markers': [], 'manual_correction_ms': 0,
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
            if kind == 'move' and now-self.last_move < 1e9/60:
                return
            if kind == 'move':
                self.last_move = now
            event = {'type': kind, 'monotonic_ns': now, **extra}
            if x is not None:
                event.update(x=x, y=y)
            try:
                event.update(self.geometry())
                self.stream.write(json.dumps(event)+'\n')
                self.stream.flush()
                self.counts[kind] = self.counts.get(kind, 0)+1
            except Exception as exc:
                self.meta['input_error'] = str(exc)

    def sample(self):
        before = time.perf_counter_ns()
        status = self.obs.get_record_status()
        after = time.perf_counter_ns()
        if not status.output_active or status.output_paused:
            raise RuntimeError('OBS recording is inactive or paused; do not pause externally')
        sample = dict(estimate_origin(before, after, status.output_duration),
                      before_ns=before, after_ns=after, output_duration_ms=status.output_duration)
        self.sync['samples'].append(sample)
        self.sync['origin_ns'] = min(self.sync['samples'], key=lambda s:s['half_rtt_ns'])['origin_ns']
        self.save()

    def start(self):
        from pynput import mouse
        if self.obs.get_record_status().output_active:
            raise RuntimeError('OBS is already recording; stop it before starting a session')
        self.stream = (self.folder/'events.jsonl').open('a', encoding='utf-8')
        self.active = True
        self.listener = mouse.Listener(
            on_move=lambda x,y:self.event('move',x,y),
            on_click=lambda x,y,b,p:self.event('click',x,y,button=str(b),pressed=p),
            on_scroll=lambda x,y,dx,dy:self.event('scroll',x,y,dx=dx,dy=dy))
        try:
            self.listener.start()
            self.listener.wait()
            self.meta['start_request_ns'] = time.perf_counter_ns()
            self.meta['owns_recording_attempt'] = True
            self.obs.start_record()
            self.meta['start_response_ns'] = time.perf_counter_ns()
            self.meta['state'] = 'recording'
            self.save()
            self.sample()
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
        if self.meta['state'] == 'recording':
            try:
                self.sample()
            except Exception as exc:
                self.meta['sync_warning'] = str(exc)
        # Do not close input capture until OBS acknowledges stop. Caller can retry.
        status = self.obs.get_record_status()
        if status.output_active:
            result = self.obs.stop_record()
            self.meta['obs_output_path'] = result.output_path
        self.meta['stop_response_ns'] = time.perf_counter_ns()
        self.active = False
        if self.listener:
            self.listener.stop()
            self.listener.join(timeout=3)
        with self.lock:
            if self.stream:
                self.stream.close()
        self.meta['event_counts'] = self.counts
        self.meta['state'] = 'stopped'
        self.save()
        source = self.meta.get('obs_output_path')
        if source:
            source = Path(source)
            if not source.is_file():
                raise RuntimeError(f'OBS video is not accessible: {source}. Copy it into {self.folder}')
            destination = self.folder / ('video'+source.suffix)
            if not destination.exists():
                partial = destination.with_suffix(destination.suffix+'.partial')
                shutil.copy2(source, partial)
                partial.replace(destination)
            self.meta['video_file'] = destination.name
        else:
            self.meta['video_warning'] = 'OBS was already stopped; recover video manually from OBS output folder'
        self.save()
