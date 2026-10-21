import json
import tempfile
import unittest
from pathlib import Path
from recorder.core import estimate_origin, video_seconds, relative_point, density, generate_heatmaps


class TimelineTests(unittest.TestCase):
    def test_startup_delay_and_midpoint(self):
        # Start request at 0, actual recording starts at 2 seconds.
        sample = estimate_origin(3_990_000_000,4_010_000_000,2000)
        self.assertEqual(sample['origin_ns'],2_000_000_000)
        self.assertEqual(sample['half_rtt_ns'],10_000_000)
        self.assertEqual(video_seconds(5_000_000_000,sample['origin_ns'],25),3.025)
        self.assertLess(video_seconds(1_000_000_000,sample['origin_ns']),0)

    def test_invalid_sample(self):
        with self.assertRaises(ValueError):
            estimate_origin(2,1,0)
        with self.assertRaises(ValueError):
            estimate_origin(1,2,-1)


class CoordinateTests(unittest.TestCase):
    def test_negative_monitor_origin_and_edges(self):
        rect = [-1920,-100,1920,1080]
        self.assertEqual(relative_point(-1920,-100,rect),(0,0,True))
        self.assertEqual(relative_point(-960,440,rect),(.5,.5,True))
        self.assertFalse(relative_point(0,0,rect)[2])
        self.assertFalse(relative_point(-1921,0,rect)[2])
        with self.assertRaises(ValueError):
            relative_point(0,0,[0,0,0,10])

    def test_bins_orientation_and_click_release(self):
        events = [{'type':'click','x':-100,'y':-50,'pressed':True},
                  {'type':'click','x':99,'y':49,'pressed':True},
                  {'type':'click','x':0,'y':0,'pressed':False},
                  {'type':'click','x':100,'y':0,'pressed':True}]
        grid = density(events,[-100,-50,200,100],'click',2)
        self.assertEqual(grid.tolist(),[[1,0],[0,1]])
        self.assertEqual(int(grid.sum()),2)

    def test_png_generation_and_empty_moves(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder/'metadata.json').write_text(json.dumps({'capture_rect':[-100,0,200,100]}))
            (folder/'events.jsonl').write_text(json.dumps({'type':'click','x':0,'y':50,'pressed':True})+'\n')
            generate_heatmaps(folder)
            from PIL import Image
            for kind in ('move','click'):
                with Image.open(folder/f'{kind}_heatmap.png') as image:
                    image.verify()
                self.assertGreater((folder/f'{kind}_heatmap.png').stat().st_size,1000)
