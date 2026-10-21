"""Local authenticated OBS v5 connection."""
import logging


def connect(password):
    import obsws_python
    # Upstream 1.8 logs constructor arguments (including password) at INFO.
    # Disable its per-client logger even if callers enable verbose root logging.
    logging.getLogger('obsws_python.baseclient.ObsClient').disabled = True
    return obsws_python.ReqClient(host='localhost', port=4455, password=password, timeout=10)


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
