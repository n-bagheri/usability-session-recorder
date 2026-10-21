import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from recorder.session import Session


class FakeOBS:
    def __init__(self,path):
        self.active = True
        self.path = str(path)
    def get_record_status(self):
        return SimpleNamespace(output_active=self.active,output_paused=False,output_duration=1000)
    def stop_record(self):
        self.active = False
        return SimpleNamespace(output_path=self.path)


class SessionTests(unittest.TestCase):
    def test_record_events_sync_stop_and_copy(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'obs.mkv'
            source.write_bytes(b'fake video fixture')
            obs = FakeOBS(source)
            session = Session(obs,directory,'zoom',[0,0,100,100],lambda:{'desktop_rect':[0,0,100,100]})
            session.stream = (session.folder/'events.jsonl').open('a')
            session.active = True
            session.meta['owns_recording_attempt'] = True
            session.meta['state'] = 'recording'
            with patch('recorder.session.time.perf_counter_ns', side_effect=[1_990_000_000,2_010_000_000]):
                session.sample()
            self.assertEqual(session.sync['origin_ns'],1_000_000_000)
            session.event('click',10,20,pressed=True,button='Button.left')
            session.event('scroll',10,20,dx=0,dy=-1)
            session.marker()
            session.stop()
            self.assertFalse(session.active)
            self.assertEqual((session.folder/'video.mkv').read_bytes(),source.read_bytes())
            events = [json.loads(line) for line in (session.folder/'events.jsonl').read_text().splitlines()]
            self.assertEqual([e['type'] for e in events],['click','scroll','sync_marker'])
            self.assertEqual(events[0]['x'],10)
            self.assertIn('monotonic_ns',events[0])
            self.assertEqual(json.loads((session.folder/'metadata.json').read_text())['state'],'stopped')

    def test_failed_stop_preserves_capture_for_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            obs = FakeOBS('unused')
            session = Session(obs,directory,'in-person',[0,0,1,1],lambda:{})
            session.active = True
            session.meta['owns_recording_attempt'] = True
            with patch.object(obs,'stop_record',side_effect=TimeoutError('timeout')):
                with self.assertRaises(TimeoutError):
                    session.stop()
            self.assertTrue(session.active)

    def test_paused_recording_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            obs = FakeOBS('unused')
            obs.get_record_status = lambda:SimpleNamespace(output_active=True,output_paused=True,output_duration=0)
            session = Session(obs,directory,'zoom',[0,0,1,1],lambda:{})
            with self.assertRaises(RuntimeError):
                session.sample()

    def test_start_hooks_before_obs_and_persists_startup_sample(self):
        import sys
        calls = []
        class Listener:
            def __init__(self, **callbacks):
                self.callbacks = callbacks
            def start(self):
                calls.append('hook')
            def wait(self):
                pass
            def stop(self):
                pass
            def join(self, timeout=None):
                pass
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'original.mkv'
            source.write_bytes(b'test')
            obs = FakeOBS(source)
            obs.active = False
            def start_record():
                calls.append('obs')
                obs.active = True
            obs.start_record = start_record
            session = Session(obs,directory,'in-person',[0,0,100,100],lambda:{})
            with patch.dict(sys.modules, {'pynput':SimpleNamespace(mouse=SimpleNamespace(Listener=Listener))}):
                session.start()
                self.assertEqual(calls,['hook','obs'])
                self.assertEqual(session.meta['state'],'recording')
                self.assertGreaterEqual(session.meta['start_response_ns'],session.meta['start_request_ns'])
                self.assertEqual(len(session.sync['samples']),1)
                session.stop()

    def test_no_ownership_does_not_stop_existing_recording(self):
        with tempfile.TemporaryDirectory() as directory:
            obs = FakeOBS('unused')
            session = Session(obs,directory,'zoom',[0,0,1,1],lambda:{})
            with self.assertRaises(RuntimeError):
                session.stop()
            self.assertTrue(obs.active)

    def test_partial_copy_can_be_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'obs.mkv'
            source.write_bytes(b'complete video')
            obs = FakeOBS(source)
            session = Session(obs,directory,'zoom',[0,0,100,100],lambda:{})
            session.meta['owns_recording_attempt'] = True
            with patch('recorder.session.shutil.copy2',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    session.stop()
            self.assertFalse((session.folder/'video.mkv').exists())
            session.stop()
            self.assertEqual((session.folder/'video.mkv').read_bytes(),source.read_bytes())

    def test_start_timeout_keeps_input_until_recovery_stop(self):
        import sys
        class Listener:
            def __init__(self, **kwargs):
                pass
            def start(self):
                pass
            def wait(self):
                pass
            def stop(self):
                pass
            def join(self, timeout=None):
                pass
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'obs.mkv'
            source.write_bytes(b'video')
            obs = FakeOBS(source)
            obs.active = False
            def ambiguous_start():
                obs.active = True
                raise TimeoutError('response lost')
            obs.start_record = ambiguous_start
            session = Session(obs,directory,'zoom',[0,0,1,1],lambda:{})
            with patch.dict(sys.modules,{'pynput':SimpleNamespace(mouse=SimpleNamespace(Listener=Listener))}):
                with self.assertRaises(TimeoutError):
                    session.start()
            self.assertTrue(session.active)
            self.assertEqual(session.meta['state'],'start_uncertain')
            session.stop()
            self.assertFalse(obs.active)
            self.assertFalse(session.active)

    def test_confirmation_timeout_keeps_events_and_blocks_duplicate_start(self):
        from recorder.obs import RecordingConfirmationTimeout
        import sys
        class Listener:
            def __init__(self, **kwargs):
                pass
            def start(self):
                pass
            def wait(self):
                pass
            def stop(self):
                pass
            def join(self, timeout=None):
                pass
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'video.mkv'
            source.write_bytes(b'test video')
            obs = FakeOBS(source)
            obs.active = False
            from unittest.mock import Mock
            obs.start_record = Mock()
            session = Session(obs,directory,'in-person',[0,0,100,100],lambda:{})
            with patch.dict(sys.modules,{'pynput':SimpleNamespace(mouse=SimpleNamespace(Listener=Listener))}), \
                 patch('recorder.session.wait_for_recording',side_effect=RecordingConfirmationTimeout('delayed')):
                with self.assertRaises(RecordingConfirmationTimeout):
                    session.start()
            session.event('click',5,6,pressed=True)
            with self.assertRaises(RuntimeError):
                session.start()
            obs.start_record.assert_called_once()
            self.assertTrue(session.active)
            self.assertEqual(session.meta['state'],'start_uncertain')
            # Even a stale inactive status must not suppress the actual StopRecord.
            obs.stop_record = Mock(return_value=SimpleNamespace(output_path=str(source)))
            session.stop()
            obs.stop_record.assert_called_once()
            self.assertFalse(session.active)
            self.assertEqual(len((session.folder/'events.jsonl').read_text().splitlines()),1)

    def test_geometry_failure_does_not_drop_raw_mouse_event(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory:
            provider = Mock(side_effect=[{},OSError('foreground inaccessible')])
            session = Session(None,directory,'zoom',[0,0,10,10],provider)
            session.active = True
            session.stream = (session.folder/'events.jsonl').open('a')
            session.event('move',3,4)
            session.stream.close()
            event = json.loads((session.folder/'events.jsonl').read_text())
            self.assertEqual(event['x'],3)
            self.assertIn('geometry_error',event)
            self.assertEqual(event['target']['classification'],'uncertain')

    def test_session_confirms_delayed_activation_without_resending_start(self):
        import sys
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as directory:
            obs = FakeOBS('unused')
            inactive = SimpleNamespace(output_active=False,output_paused=False,output_duration=0)
            paused = SimpleNamespace(output_active=True,output_paused=True,output_duration=0)
            ready = SimpleNamespace(output_active=True,output_paused=False,output_duration=200)
            obs.get_record_status = Mock(side_effect=[inactive,inactive,paused,ready,ready])
            obs.start_record = Mock()
            listener = Mock()
            mouse = SimpleNamespace(Listener=Mock(return_value=listener))
            session = Session(obs,directory,'in-person',[0,0,100,100],lambda:{})
            with patch.dict(sys.modules,{'pynput':SimpleNamespace(mouse=mouse)}),patch('time.sleep'):
                session.start()
            self.assertEqual(session.meta['state'],'recording')
            self.assertEqual(len(session.sync['startup_observations']),4)
            obs.start_record.assert_called_once()
            with self.assertRaises(RuntimeError):
                session.start()
            self.assertTrue(session.active)
            session.active = False
            session.stream.close()
