import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image
from recorder.analysis import target_events, validate_mapping
from recorder.calibration import save_frame_mapping
from recorder.core import generate_heatmaps
from recorder.session import Session
from test_targeting import calibration, observation


class AnalysisTests(unittest.TestCase):
    def test_four_mapgen_clicks_raw_preservation_and_reference_overlay(self):
        with tempfile.TemporaryDirectory() as directory:
            # Real event writer, simulated Windows observations and OBS clock.
            current = [observation()]
            session = Session(None,directory,'in-person',[-1200,20,1000,800],lambda:{},
                              target=calibration(),target_provider=lambda *_: current[0])
            session.active = True
            session.stream = (session.folder/'events.jsonl').open('a',encoding='utf-8')
            inside_points = [(-1100,220),(-700,420),(-300,720)]
            for x,y in inside_points:
                session.event('click',x,y,pressed=True)
            current[0] = observation(hit_root=99,foreground_root=99)
            for _ in range(3):
                session.event('click',-700,420,pressed=True)
            current[0] = observation()
            session.event('click',-1000,520,pressed=True)
            current[0] = observation(stable=False)
            session.event('click',-600,420,pressed=True)
            # Two immediate moves must both survive, even with observation failures.
            current[0] = {'error':'window unavailable'}
            session.event('move',-600,420)
            session.event('move',-601,421)
            session.stream.close()
            session.active = False
            raw_path = session.folder/'events.jsonl'
            raw = raw_path.read_bytes()
            events = [json.loads(line) for line in raw.splitlines()]
            self.assertEqual(len(events),10)
            self.assertEqual([e['target']['classification'] for e in events[:8]],
                             ['inside']*3+['outside']*3+['inside','uncertain'])
            self.assertTrue(all('monotonic_ns' in e for e in events))
            report = generate_heatmaps(session.folder)
            self.assertEqual(report['click_presses'],{'included':4,'excluded':3,'uncertain':1})
            self.assertEqual(report['mouse_events'],{'included':4,'excluded':3,'uncertain':3})
            self.assertEqual(report['alignment']['status'],'unverified')
            # This image is synthetic test data, never a participant screenshot.
            frame = Path(directory)/'synthetic.png'
            Image.new('RGB',(1200,900),'white').save(frame)
            save_frame_mapping(session.folder,frame,'1000x700-dpi96',[0,0,1000,700],[100,100,1000,700])
            report = generate_heatmaps(session.folder)
            self.assertEqual(report['alignment']['plotted_clicks'],4)
            with Image.open(session.folder/'mapgen_click_overlay.png') as overlay:
                self.assertEqual(overlay.size,(1200,900))
                # First local click (100,100) -> frame (200,200), ring at x+7.
                self.assertEqual(overlay.getpixel((207,200)),(255,0,0))
                # Occluded-only position is also an inside location here; no extra count.
            self.assertEqual(raw_path.read_bytes(),raw)
            groups,_ = target_events(events,calibration())
            self.assertEqual([e['x'] for e in groups['1000x700-dpi96']],[100,500,900,200])
            from recorder.core import density
            self.assertEqual(int(density(groups['1000x700-dpi96'],[0,0,1000,700],'click').sum()),4)

    def test_separate_resized_layouts_and_uncalibrated_legacy_data(self):
        events = []
        for snap in (observation(),observation(client_rect=[0,0,1200,900])):
            events.append({'type':'click','x':snap['client_rect'][0]+50,'y':snap['client_rect'][1]+150,
                           'pressed':True,'target_observation':snap})
        events.append({'type':'click','x':0,'y':0,'pressed':True})
        groups,report = target_events(events,calibration())
        self.assertEqual(set(groups),{'1000x700-dpi96','1200x800-dpi96'})
        self.assertEqual(report['click_presses'],{'included':2,'excluded':0,'uncertain':1})

    def test_no_silent_out_of_bounds_or_nonfinite_frame_mapping(self):
        mapping = {'content_size':[100,100],'source_rect':[0,0,100,100],
                   'frame_rect':[10,10,100,100],'frame_size':[120,120]}
        validate_mapping(mapping,[120,120])
        with self.assertRaises(ValueError):
            validate_mapping(dict(mapping,frame_rect=[10,10,200,100]),[120,120])
        with self.assertRaises(ValueError):
            validate_mapping(dict(mapping,source_rect=[0,0,float('nan'),100]),[120,120])
        with self.assertRaises(ValueError):
            validate_mapping(mapping,[200,200])

    def test_overlay_reports_clicks_removed_by_explicit_source_crop(self):
        from recorder.analysis import click_overlay
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            Image.new('RGB',(200,200),'white').save(folder/'frame.png')
            mapping = {'frame_file':'frame.png','frame_size':[200,200],
                       'layout_key':'100x100-dpi96','content_size':[100,100],
                       'source_rect':[50,0,50,100],'frame_rect':[25,25,100,150]}
            events = [{'type':'click','pressed':True,'x':x,'y':25,'content_size':[100,100]} for x in (25,75)]
            report = click_overlay(folder,events,mapping)
            self.assertEqual(report['plotted_clicks'],1)
            self.assertEqual(report['clicks_outside_source_crop'],1)
