"""Local authenticated OBS v5 connection."""
import logging


def connect(password):
    import obsws_python
    # Upstream 1.8 logs constructor arguments (including password) at INFO.
    # Disable its per-client logger even if callers enable verbose root logging.
    logging.getLogger('obsws_python.baseclient.ObsClient').disabled = True
    return obsws_python.ReqClient(host='localhost', port=4455, password=password, timeout=10)
