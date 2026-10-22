import copy
import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from examples.synthetic_demo import create
from recorder.research import ResearchSession
from recorder.review import write_review
from recorder.corrections import geometry_key,fit_registration


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'saved-video tools unavailable')
class RecordFirstAnalysisTests(unittest.TestCase):
    def test_regions_corrections_reopen_and_all_original_evidence_immutable(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);report=create(folder)
            self.assertEqual(sum(r['button_presses'] for r in report['regions']['regions']),4)
            self.assertTrue(all(r['reference_exports'] for r in report['regions']['regions']))
            # Model the user's bad recorded viewport as fixture input, then freeze evidence.
            raw=folder/'events.jsonl';events=[json.loads(line) for line in raw.read_text().splitlines()]
            for e in events:
                e['target_observation']['viewport']['rect']=[0,210,320,30]
            raw.write_text(''.join(json.dumps(e)+'\n' for e in events))
            (folder/'calibration_observations.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in [{'state_id':'same','status':'invalid','observed_ns':0},{'state_id':'same','status':'invalid','observed_ns':5_000_000_000}]))
            originals=['video.mkv','events.jsonl','metadata.json','sync.json','calibration_observations.jsonl']
            hashes={name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in originals}
            data=ResearchSession(folder)
            self.assertEqual(data.by_id['2']['target']['classification'],'uncertain')
            anchors=[]
            for event_id in ('2','5'):
                e=data.by_id[event_id];s=e['target_observation']
                anchors.append({'event_id':event_id,'desktop':[e['x'],e['y']],'observed':[e['x']+40,e['y']+30],
                    'geometry_key':geometry_key(s),'client_rect':s['client_rect'],'frame':data.video.frame(data.time(e)),'uncertainty_px':2})
            c=fit_registration(data.review['segments'][0],anchors,[40,50,320,220],data.video.fingerprint)
            data.review['mapping_corrections'].append(c);write_review(folder,data.review,4)
            reopened=ResearchSession(folder)
            self.assertEqual(reopened.by_id['2']['target']['classification'],'inside')
            self.assertEqual(reopened.predict(reopened.by_id['2']),[90,110])
            exported=reopened.export()
            self.assertEqual(exported['annotation_schema'],2)
            self.assertTrue((folder/'research_analysis'/exported['output_base']/'region-summary.csv').exists())
            for name in originals:self.assertEqual(hashlib.sha256((folder/name).read_bytes()).hexdigest(),hashes[name],name)
            # Undo is only an annotation change; the old raw calibration remains available.
            reopened.review['mapping_corrections'][0]['confirmed']=False;reopened.reclassify()
            self.assertEqual(reopened.by_id['2']['target']['classification'],'uncertain')
            # A real observed state change remains uncertain even with a fitted correction.
            reopened.review['mapping_corrections'][0]['confirmed']=True
            write_review(folder,reopened.review,4)
            (folder/'calibration_observations.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in [
                {'state_id':'before','status':'invalid','observed_ns':0},
                {'state_id':'after','status':'invalid','observed_ns':5_000_000_000}]))
            changed=ResearchSession(folder)
            self.assertEqual(changed.by_id['2']['target']['reason'],'calibration_transition_between_poll_observations')

    def test_optional_timing_and_corrupt_cache_do_not_block_qualitative_review(self):
        from recorder.media import Video
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);create(folder)
            (folder/'sync.json').unlink()
            data=ResearchSession(folder)
            self.assertFalse(data.timing_available);self.assertIsNone(data.time(data.events[0]))
            self.assertIsNotNone(data.video.frame(.6))
            report=data.export()
            self.assertFalse(report['timing_available'])
            self.assertTrue(all(r['reason']=='timing_unavailable' for r in report['regions']['events']))
            frame=data.video.frame(.6);Path(frame['path']).write_bytes(b'interrupted derived cache')
            restored=data.video.frame(.6)
            from PIL import Image
            with Image.open(restored['path']) as image:image.verify()
            (folder/'review_cache'/'video_index.json').write_text('{interrupted')
            self.assertTrue(Video(folder).pts)
