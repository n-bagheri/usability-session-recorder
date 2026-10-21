"""Local authenticated OBS v5 connection."""
import logging


def connect(password, port=4455):
    import obsws_python
    # Upstream 1.8 logs constructor arguments (including password) at INFO.
    # Disable its per-client logger even if callers enable verbose root logging.
    logging.getLogger('obsws_python.baseclient.ObsClient').disabled = True
    client = obsws_python.ReqClient(host='localhost', port=port, password=password, timeout=10)
    install_correlated_requests(client)
    return client


class RecordingConfirmationTimeout(RuntimeError):
    pass


def wait_for_recording(read_status, observe, timeout=10, interval=0.15):
    """Two consecutive active/unpaused, nondecreasing-duration observations.

    Never sends StartRecord. Deadline bounds retries; an in-flight request can
    additionally consume the client's configured socket timeout (10 seconds).
    """
    import time
    import math
    deadline = time.monotonic() + timeout
    previous_duration = None
    message = ('OBS activation not confirmed before deadline. Recording may be running; '
               'input capture continues. Use Check OBS or Stop Session; do not start again.')
    while True:
        if time.monotonic() >= deadline:
            raise RecordingConfirmationTimeout(message)
        before = time.perf_counter_ns()
        try:
            status = read_status()
            after = time.perf_counter_ns()
            active, paused = status.output_active, status.output_paused
            duration = status.output_duration
            valid = (active is True and paused is False and
                     isinstance(duration, (int, float)) and math.isfinite(duration) and duration >= 0)
            observe({'before_ns': before, 'after_ns': after,
                     'active': active, 'paused': paused, 'duration_ms': duration})
            if valid and previous_duration is not None and duration >= previous_duration:
                return before, after, duration
            previous_duration = duration if valid else None
        except Exception as exc:
            observe({'before_ns': before, 'after_ns': time.perf_counter_ns(),
                     'error_type': type(exc).__name__})
            previous_duration = None
        remaining = deadline-time.monotonic()
        if remaining <= 0:
            raise RecordingConfirmationTimeout(message)
        time.sleep(min(interval, remaining))


class SerializedOBS:
    def __init__(self, client):
        import threading
        self.client = client
        self.lock = threading.RLock()

    def __getattr__(self, name):
        value = getattr(self.client,name)
        if not callable(value):
            return value
        def call(*args,**kwargs):
            with self.lock:
                return value(*args,**kwargs)
        return call


def install_correlated_requests(client):
    """SDK 1.8 reads one response without checking requestId. Ignore stale responses
    after a timeout instead of attributing them to the next start/status/stop call.
    """
    import json
    import time
    import uuid
    def request(request_type, data=None):
        request_id=uuid.uuid4().hex
        body={'requestType':request_type,'requestId':request_id}
        if data is not None:body['requestData']=data
        ws=client.base_client.ws
        deadline=time.monotonic()+10
        ws.settimeout(10)
        ws.send(json.dumps({'op':6,'d':body}))
        while True:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('OBS response deadline exceeded; state uncertain')
            ws.settimeout(remaining)
            message=json.loads(ws.recv())
            if message.get('op')==7 and message.get('d',{}).get('requestId')==request_id:
                response=message['d']
                if response.get('requestType')!=request_type:raise RuntimeError('OBS response type mismatch')
                return response
    client.base_client.req=request


def wait_for_stopped(read_status,observe,timeout=10,interval=.15):
    import time
    deadline=time.monotonic()+timeout;consecutive=0
    while time.monotonic()<deadline:
        before=time.perf_counter_ns()
        try:
            status=read_status()
            active=status.output_active
            observe({'before_ns':before,'after_ns':time.perf_counter_ns(),'active':active})
            consecutive=consecutive+1 if active is False else 0
            if consecutive>=2:return
        except Exception as exc:
            observe({'before_ns':before,'after_ns':time.perf_counter_ns(),'error_type':type(exc).__name__})
            consecutive=0
        time.sleep(min(interval,max(0,deadline-time.monotonic())))
    raise RuntimeError('OBS stop acknowledgement received, but inactive state is not confirmed; input capture remains open. Retry Stop confirmation.')
