import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from examples.synthetic_demo import create
from recorder.research import ResearchSession,suggest_transitions
from recorder.hotkeys import parse_hotkey


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg/ffprobe required for saved-video integration')
class SavedVideoTests(unittest.TestCase):
    def test_actual_decoding_view_separation_and_non_destructive_reanalysis(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            report=create(folder)
            self.assertEqual(len(report['contextual_clicks']),4)
            self.assertEqual(report['views']['Home']['click_presses'],2)
            self.assertEqual(report['views']['Editor']['click_presses'],2)
            self.assertEqual(report['qa']['temporal']['status'],'unverified')
            self.assertEqual(report['qa']['spatial']['status'],'computed')
            self.assertTrue(all(len(s['outputs'])==5 for s in report['segments']))
            for s in report['segments']:
                self.assertTrue(all((folder/'research_analysis'/report['output_base']/name).exists() for name in s['outputs']))
            digest=lambda:hashlib.sha256((folder/'events.jsonl').read_bytes()).hexdigest()
            before=digest();data=ResearchSession(folder)
            frame=data.video.frame(2.6)
            self.assertAlmostEqual(frame['seconds'],2.6)
            from PIL import Image
            with Image.open(frame['path']) as image:
                # Synthetic Editor click is at desktop (80,140), output (120,170).
                self.assertEqual(image.getpixel((120,170)),(255,255,0))
            second=data.export();self.assertEqual(digest(),before)
            self.assertNotEqual(second['output_base'],report['output_base'])
            self.assertTrue((folder/'research_analysis'/report['output_base']/'report.json').exists())
            self.assertTrue((folder/'research_analysis'/second['output_base']/'segment-home-original.png').exists())
            self.assertTrue((folder/'research_analysis'/second['output_base']/'segment-home-click-density-transparent.png').exists())
            suggestions=suggest_transitions(data.video,step=1,threshold=.01)
            self.assertTrue(suggestions['suggestions'])
            self.assertTrue(all(s['semantic_label'] is None for s in suggestions['suggestions']))
            # A changing/unreviewed state never gets a static background overlay.
            data.review['segments'][0]['stable']=False
            changing=data.export()
            self.assertEqual(changing['segments'][0]['outputs'],[])
            # A changed calibration discovered after the event invalidates the
            # between-poll interval in derived attribution, preserving raw bytes.
            from recorder.review import save_json
            journal=[{'state_id':'before','status':'computed','observed_ns':1_400_000_000},
                     {'state_id':'after','status':'computed','observed_ns':2_000_000_000}]
            (folder/'calibration_observations.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in journal))
            guarded=ResearchSession(folder)
            self.assertEqual(guarded.by_id['2']['target']['classification'],'uncertain')
            self.assertEqual(guarded.by_id['2']['target']['reason'],'calibration_transition_between_poll_observations')
            self.assertEqual(digest(),before)
            # Real saved VFR stream with one frame omitted; PTS must retain the gap.
            from recorder.media import run,Video
            from recorder.review import save_json
            run(['ffmpeg','-y','-v','error','-i',str(folder/'video.mkv'),'-vf','select=not(eq(n\\,5))',
                 '-fps_mode','vfr','-c:v','ffv1',str(folder/'gap.mkv')])
            metadata=data.meta.copy();metadata['video_file']='gap.mkv';save_json(folder/'metadata.json',metadata)
            gap=Video(folder)
            self.assertGreater(gap.info['large_frame_gaps'],0)
            self.assertAlmostEqual(gap.pts[gap.nearest(1.05)],1.2)
            self.assertEqual(gap.frame(1.05)['seconds'],1.2)


class ShortcutTests(unittest.TestCase):
    def test_only_explicit_triple_modifier_combos_allowed(self):
        self.assertEqual(parse_hotkey('Ctrl+Alt+Shift+F9'),(0x4007,0x78))
        for key in ('F9','Ctrl+F9','Ctrl+Alt+Shift+A','Ctrl+Alt+Shift+F13'):
            with self.assertRaises(ValueError):parse_hotkey(key)
