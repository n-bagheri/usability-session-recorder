"""Background automatic calibration, shared by input classification and saved-video mapping."""
import copy
import threading
import time
from .targeting import calibrate, same_identity
from .obs_geometry import read_obs_capture, read_obs_evidence, fingerprint


class CalibrationMonitor:
    def __init__(self, obs, selected, snapshot, viewport, windows, interval=.5):
        self.obs,self.selected = obs,selected
        self.snapshot,self.viewport,self.windows = snapshot,viewport,windows
        self.interval = interval
        self.latest = None
        self.stop_event = threading.Event()
        self.thread = None
        self.journal = None

    def refresh(self):
        started=time.perf_counter_ns()
        try:
            hwnd = self.selected['identity']['hwnd']
            s = self.snapshot(hwnd,0,0)
            if s.get('error') or not s.get('stable') or not same_identity(self.selected['identity'],s['identity']):
                raise ValueError('Selected window identity or geometry is no longer valid')
            v = self.viewport(hwnd,s['client_rect'])
            mapping = read_obs_capture(self.obs,self.selected,self.windows(),s,v)
            # Recheck window geometry after COM/OBS round trips.
            end = self.snapshot(hwnd,0,0)
            if any(s.get(k) != end.get(k) for k in ('identity','client_rect','dpi','maximized')):
                raise ValueError('Window changed during automatic calibration')
            result = {'viewport':v,'mapping':mapping,'client_rect':s['client_rect'],
                      'dpi':s['dpi'],'identity':s['identity'],'maximized':s.get('maximized'),
                      'monitor':s.get('monitor'),'status':'computed','observed_ns':time.perf_counter_ns()}
        except Exception as exc:
            result = {'status':'invalid','reason':str(exc),'observed_ns':time.perf_counter_ns(),
                      'viewport_detection_evidence':getattr(exc,'evidence',None),'window_observation':locals().get('s')}
        if result['status']=='invalid':
            try:result['obs_capture_evidence']=read_obs_evidence(self.obs,self.selected,self.windows())
            except Exception as exc:result['obs_evidence_error']=str(exc)
        result['measurement_interval_ns']=[started,time.perf_counter_ns()]
        if result['measurement_interval_ns'][1]-started>1_500_000_000:
            result.update(status='invalid',reason='Automatic calibration took over 1.5 seconds; measurement is not fresh enough')
        state={k:result.get(k) for k in ('viewport','mapping','client_rect','dpi','identity','monitor','status','reason')}
        if result['status']=='invalid':
            state['window_geometry']={k:(result.get('window_observation') or {}).get(k) for k in ('identity','client_rect','dpi','monitor','maximized')}
            state['obs_capture_evidence']=result.get('obs_capture_evidence')
        result['state_id']=fingerprint(state)
        self.latest = result
        try:self.write_journal(result)
        except OSError as exc:result.update(status='invalid',reason='Calibration journal write failed: '+str(exc))
        return result

    def write_journal(self,result):
        import json
        path=self.journal
        if path:
            with path.open('a',encoding='utf-8') as stream:stream.write(json.dumps(result)+'\n')

    def bind(self,folder):
        from pathlib import Path
        self.journal=Path(folder)/'calibration_observations.jsonl' if folder else None
        if self.latest:self.write_journal(self.latest)

    def start(self):
        def run():
            while not self.stop_event.is_set():
                self.refresh()
                self.stop_event.wait(self.interval)
        self.thread = threading.Thread(target=run,daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def observe(self, hwnd, x, y):
        s = self.snapshot(hwnd,x,y)
        latest = self.latest
        s['automatic_calibration'] = copy.deepcopy(latest)
        if (not latest or latest['status'] != 'computed' or
            time.perf_counter_ns()-latest['observed_ns'] > 1_500_000_000 or
            any(s.get(k) != latest.get(k) for k in ('identity','client_rect','dpi','maximized','monitor'))):
            s['viewport_error'] = 'Automatic calibration unavailable, stale or geometry changed; awaiting fresh measurement'
        else:
            s['viewport'] = latest['viewport']
            s['capture_mapping'] = latest['mapping']
        return s

    def calibration(self):
        result = self.refresh()
        if result['status'] != 'computed':
            raise ValueError(result['reason'])
        s = self.snapshot(self.selected['identity']['hwnd'],0,0)
        x,y,w,h = result['viewport']['rect']
        c = calibrate(s,(x,y),(x+w-1,y+h-1))
        c.update(method='automatic_uia_obs',viewport=result['viewport'],capture_mapping=result['mapping'],
                 validity='computed_not_experimentally_verified')
        return c
