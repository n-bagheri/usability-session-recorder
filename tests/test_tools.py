import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from recorder.tools import main


class ReportTests(unittest.TestCase):
    def test_report_and_derived_timeline_use_correction(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            sync = {'origin_ns':1_000_000_000,'manual_correction_ms':-20,
                    'samples':[{'origin_ns':1_000_000_000},{'origin_ns':1_002_000_000}],
                    'markers':[{'monotonic_ns':2_000_000_000,'number':1}]}
            (folder/'sync.json').write_text(json.dumps(sync))
            raw = json.dumps({'type':'move','monotonic_ns':3_000_000_000,'x':0,'y':0})+'\n'
            (folder/'events.jsonl').write_text(raw)
            output = io.StringIO()
            with patch('sys.argv',['report',directory]), contextlib.redirect_stdout(output):
                main()
            report = json.loads(output.getvalue())
            self.assertEqual(report['markers'][0]['estimated_video_seconds'],.98)
            self.assertEqual(report['sample_origin_spread_ms'],2)
            self.assertEqual(json.loads((folder/'timeline.jsonl').read_text())['estimated_video_seconds'],1.98)
            self.assertEqual((folder/'events.jsonl').read_text(),raw)
