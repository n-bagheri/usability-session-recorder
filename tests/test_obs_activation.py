import unittest
from types import SimpleNamespace
from unittest.mock import patch
from recorder.obs import wait_for_recording, RecordingConfirmationTimeout


def status(active=True,paused=False,duration=100):
    return SimpleNamespace(output_active=active,output_paused=paused,output_duration=duration)


class ConfirmationTests(unittest.TestCase):
    def test_delayed_and_inconsistent_status_requires_two_consecutive_valid_samples(self):
        responses = [status(False),status(),status(False),status(paused=True),
                     status(duration=300),status(duration=310)]
        history = []
        with patch('time.sleep'):
            result = wait_for_recording(lambda: responses.pop(0),history.append)
        self.assertEqual(len(history),6)
        self.assertEqual(result[2],310)

    def test_transient_request_error_is_observed_and_retried(self):
        from unittest.mock import Mock
        read = Mock(side_effect=[TimeoutError(),status(),status(duration=200)])
        history = []
        with patch('time.sleep'):
            wait_for_recording(read,history.append)
        self.assertEqual(history[0]['error_type'],'TimeoutError')
        self.assertEqual(read.call_count,3)

    def test_duration_regression_resets_confirmation(self):
        responses = [status(duration=300),status(duration=200),status(duration=210)]
        history = []
        with patch('time.sleep'):
            wait_for_recording(lambda: responses.pop(0),history.append)
        self.assertEqual(len(history),3)

    def test_timeout_is_bounded_and_does_not_send_start_requests(self):
        history = []
        with patch('time.monotonic',side_effect=[0,0,0.5,0.5,1.1]),patch('time.sleep'):
            with self.assertRaises(RecordingConfirmationTimeout):
                wait_for_recording(lambda:status(False),history.append,timeout=1)
        self.assertEqual(len(history),2)

    def test_stop_requires_settled_inactive_not_one_stale_status(self):
        from recorder.obs import wait_for_stopped
        responses=[status(False),status(True),status(False),status(False)]
        history=[]
        with patch('time.sleep'):
            wait_for_stopped(lambda:responses.pop(0),history.append)
        self.assertEqual(len(history),4)
