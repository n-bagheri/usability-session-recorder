import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from recorder.media import Video


class FrameCommandTests(unittest.TestCase):
    def test_single_frame_command_does_not_use_removed_vsync_option(self):
        with tempfile.TemporaryDirectory() as directory:
            v=object.__new__(Video);v.cache=Path(directory);v.path=Path(directory)/'saved.mkv';v.fingerprint='synthetic'
            v.pts=[0,.033,.100];v.info={'size':[100,100]}
            with patch('recorder.media.run',return_value=b'synthetic image bytes') as call:
                frame=v.frame(.09)
            command=call.call_args.args[0]
            self.assertNotIn('-vsync',command);self.assertIn('select=eq(n\\,2)',command)
            self.assertEqual(frame['seconds'],.100)

    def test_view_reference_never_borrows_a_frame_across_a_cut(self):
        v=object.__new__(Video);v.pts=[0,.1,.2,.5,.7]
        self.assertEqual(v.interval_index(.29,.15,.3),2)
        self.assertEqual(v.interval_index(.49,.21,.6),3)
        with self.assertRaisesRegex(ValueError,'no saved video frame'):
            v.interval_index(.35,.3,.5)
