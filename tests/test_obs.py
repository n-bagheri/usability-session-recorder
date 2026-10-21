import io
import logging
import unittest
from unittest.mock import patch
from recorder.obs import connect


class OBSConnectionTests(unittest.TestCase):
    def test_local_connection_and_password_not_logged(self):
        import obsws_python.baseclient
        captured = io.StringIO()
        handler = logging.StreamHandler(captured)
        logger = logging.getLogger('obsws_python')
        old_level = logger.level
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        try:
            with patch.object(obsws_python.baseclient.websocket,'WebSocket') as socket, \
                 patch.object(obsws_python.baseclient.ObsClient,'authenticate',return_value={'negotiatedRpcVersion':1}):
                socket.return_value.recv.return_value = '{"op":0,"d":{"obsWebSocketVersion":"5.0.0","rpcVersion":1}}'
                client = connect('test-only-password')
                socket.return_value.connect.assert_called_once_with('ws://localhost:4455',timeout=10)
                self.assertEqual(client.base_client.password,'test-only-password')
                self.assertNotIn('test-only-password',captured.getvalue())
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)
