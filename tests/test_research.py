import tempfile
import unittest
from pathlib import Path
from recorder.obs import install_correlated_requests
from recorder.qa import spatial_report,temporal_report,event_seconds
from recorder.review import segment_at,validate_review,paired_clicks
from recorder.media import Video
from types import SimpleNamespace
from unittest.mock import Mock
import json


class ResearchTests(unittest.TestCase):
    def test_sdk_stale_responses_cannot_be_mistaken_for_current_status(self):
        ws=Mock();sent=[]
        ws.send.side_effect=lambda payload:sent.append(json.loads(payload))
        responses=[{'op':7,'d':{'requestId':'stale','requestType':'StopRecord'}},
                   lambda:{'op':7,'d':{'requestId':sent[-1]['d']['requestId'],'requestType':'GetRecordStatus','responseData':{'outputActive':True}}}]
        ws.recv.side_effect=lambda:json.dumps((lambda v:v() if callable(v) else v)(responses.pop(0)))
        client=SimpleNamespace(base_client=SimpleNamespace(ws=ws))
        install_correlated_requests(client)
        response=client.base_client.req('GetRecordStatus')
        self.assertTrue(response['responseData']['outputActive'])
        self.assertEqual(ws.send.call_count,1)

    def test_temporal_measurements_offset_drift_and_unverified(self):
        self.assertEqual(temporal_report([],100)['status'],'unverified')
        samples=[{'estimated_seconds':t,'observed_seconds':t+.04,'corrected_seconds':t+.04} for t in (5,50,95)]
        r=temporal_report(samples,100)
        self.assertEqual(r['status'],'measured_pass')
        self.assertAlmostEqual(r['offset_ms'],40)
        samples=[{'estimated_seconds':t,'observed_seconds':t+.002*t} for t in (5,50,95)]
        r=temporal_report(samples,100)
        self.assertEqual(r['status'],'measured_fail')
        self.assertAlmostEqual(r['estimated_drift_ppm'],2000)
        self.assertEqual(event_seconds({'monotonic_ns':2_000_000_000},{'origin_ns':1_000_000_000},
                                       {'time_correction':{'offset_seconds':.02,'drift_ppm':1000}}),1.021)

    def test_spatial_computed_is_not_verified_and_five_independent_targets(self):
        self.assertEqual(spatial_report([],[1000,800],'video')['status'],'computed')
        points=[[100,80],[900,80],[500,400],[100,720],[900,720]]
        measures=[{'predicted':p,'observed':[p[0]+2,p[1]],'mapping_id':'one','event_id':str(n),'video_fingerprint':'video','reference_selection_uncertainty_px':2} for n,p in enumerate(points)]
        report=spatial_report(measures,[1000,800],'video')
        self.assertEqual(report['status'],'experimentally_verified')
        self.assertEqual(report['max_error_px'],2)
        measures[-1]['observed'][0]+=10
        self.assertEqual(spatial_report(measures,[1000,800],'video')['status'],'failed')

    def test_segments_repeat_views_preserve_unknown_and_exclude_setup(self):
        review={'analysis_interval':[2,20],'segments':[
            {'id':'a','view':'Editor','state':'panel closed','start':3,'end':8},
            {'id':'b','view':'Editor','state':'panel open','start':12,'end':18}]}
        validate_review(review,30)
        self.assertEqual(segment_at(1,review),(None,'administrative'))
        self.assertEqual(segment_at(10,review),(None,'unknown'))
        self.assertEqual(segment_at(12,review)[0]['state'],'panel open')
        review['segments'][1]['start']=7
        with self.assertRaises(ValueError):validate_review(review,30)

    def test_dropped_frame_clock_uses_pts_not_frame_number(self):
        video=object.__new__(Video);video.pts=[0,.033,.100,.133]
        self.assertEqual(video.nearest(.09),2)
        self.assertEqual(video.pts[video.nearest(.09)],.100)

    def test_button_pairs_preserve_unmatched_and_releases(self):
        events=[{'type':'click','button':'left','pressed':True},{'type':'click','button':'left','pressed':False},
                {'type':'click','button':'right','pressed':False}]
        pairs,unmatched=paired_clicks(events)
        self.assertEqual(len(pairs),1);self.assertEqual(len(unmatched),1)

    def test_dropped_frame_onset_resolution_cannot_claim_temporal_pass(self):
        rows=[{'estimated_seconds':t,'observed_seconds':t,'uncertainty_ms':200} for t in (5,50,95)]
        self.assertEqual(temporal_report(rows,100,30)['status'],'uncertain_measurement_resolution')
