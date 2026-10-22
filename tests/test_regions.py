import copy
import tempfile
import unittest
from types import SimpleNamespace as S
from recorder.annotations import new_aoi,validate_annotations,split_view,merge_views,delete_view
from recorder.review import load_review,write_review
from recorder.regions import region_analysis
from recorder.heatmaps import density_layers
from PIL import Image


def fixture():
    view={'id':'home','start':0,'end':2,'view':'Home','state':'panel closed','stable':True,'reference_seconds':.1}
    frame={'seconds':.1,'index':3,'video_fingerprint':'synthetic','size':[100,100]}
    aoi=new_aoi(view,'Search field',[0,0,50,50],frame,True)
    review={'version':2,'analysis_interval':[0,3],'segments':[view],'aois':[aoi],'mapping_corrections':[]}
    events=[]
    for t,kind,pressed,classification in [( .1,'move',None,'inside'),(.12,'click',True,'inside'),(.17,'click',False,'inside'),(.3,'move',None,'inside'),(1.5,'move',None,'inside'),(1.6,'click',True,'outside'),(2.5,'move',None,'inside')]:
        events.append({'event_id':str(len(events)+1),'raw_line':len(events)+1,'t':t,'type':kind,'pressed':pressed,'button':'left','point':[10,10],
                       'target':{'classification':classification},'monotonic_ns':round(t*1e9)})
    data=S(events=events,review=review,video=S(fingerprint='synthetic'),timing_available=True,
           time=lambda e:e['t'],predict=lambda e:e['point'] if e['target']['classification']=='inside' else None,
           mapping=lambda e:{'id':'mapping'},qa=lambda:{'spatial':{'status':'computed'},'temporal':{'status':'unverified'}})
    data.events_between=lambda a,b:[e for e in events if a<=e['t']<b]
    return data,aoi,view


class RegionTests(unittest.TestCase):
    def test_presses_pairs_samples_and_partial_cursor_time(self):
        data,aoi,_=fixture();result=region_analysis(data);stats=result['regions'][0]
        self.assertEqual(stats['button_presses'],1);self.assertEqual(stats['button_releases'],1)
        self.assertEqual(stats['complete_button_pairs_from_presses'],1);self.assertEqual(stats['movement_samples'],3)
        self.assertAlmostEqual(stats['bounded_cursor_occupancy_seconds'],.2)
        self.assertAlmostEqual(result['long_same_region_gaps_not_extrapolated_seconds'],1.2)
        self.assertEqual(result['events'][-2]['aoi_id'],None)
        self.assertEqual(result['events'][-1]['reason'],'unclassified_view')

    def test_overlap_is_unassigned_unless_explicit_priority_chosen(self):
        data,aoi,_=fixture();other=copy.deepcopy(aoi);other.update(id='other',label='Navigation',priority=1)
        data.review['aois'].append(other)
        result=region_analysis(data)
        self.assertEqual(sum(r['button_presses'] for r in result['regions']),0)
        self.assertEqual(result['events'][1]['reason'],'overlapping_regions_unassigned')
        data.review['aoi_overlap_policy']='priority'
        result=region_analysis(data)
        self.assertEqual(sum(r['button_presses'] for r in result['regions']),1)
        self.assertEqual(result['events'][1]['aoi_id'],aoi['id'])

    def test_region_time_bounds_scroll_and_unconfirmed_layout(self):
        data,aoi,_=fixture();aoi['valid_interval']=[0,.2]
        result=region_analysis(data)
        self.assertIsNone(result['events'][3]['aoi_id'])
        aoi['layout_confirmed']=False
        self.assertEqual(region_analysis(data)['regions'][0]['button_presses'],0)
        aoi['layout_confirmed']=True;data.events[0]['type']='scroll'
        self.assertEqual(region_analysis(data)['regions'][0]['warning'],'scroll_in_region_interval_define_separate_states')

    def test_observed_zoom_change_blocks_static_region_identity(self):
        data,_,_=fixture()
        for e in data.events:e['target_observation']={'viewport':{'zoom_percent':100 if e['t']<.3 else 125}}
        result=region_analysis(data)
        self.assertEqual(result['regions'][0]['warning'],'zoom_changed_in_region_interval')
        self.assertEqual(result['regions'][0]['button_presses'],0)

    def test_split_merge_and_delete_preserve_explicit_region_scopes(self):
        data,aoi,_=fixture();split=split_view(data.review,'home',1)
        self.assertEqual(len(split['segments']),2);self.assertEqual(len(split['aois']),2)
        validate_annotations(split,3,[100,100])
        right=next(a for a in split['aois'] if a['segment_id']!='home')
        self.assertFalse(right['layout_confirmed']);self.assertIsNone(right['reference_frame'])
        merged=merge_views(split,[s['id'] for s in split['segments']],True)
        self.assertEqual(len(merged['segments']),1);self.assertTrue(all(not a['layout_confirmed'] for a in merged['aois']))
        self.assertEqual(delete_view(merged,'home')['aois'],[])
        with self.assertRaises(ValueError):merge_views(split,[s['id'] for s in split['segments']])

    def test_v1_review_migrates_in_memory_and_edits_remain_separate(self):
        import json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'review.json';original=json.dumps({'version':1,'analysis_interval':[0,3],'segments':[],'custom_note':'keep'})
            p.write_text(original)
            review=load_review(directory,3)
            self.assertEqual(review['version'],2);self.assertEqual(review['aois'],[])
            self.assertEqual(p.read_text(),original);self.assertEqual(review['custom_note'],'keep')
            write_review(directory,review,3)
            self.assertTrue(list((Path(directory)/'review_history').glob('*.json')))

    def test_density_transparency_settings_and_count_preserving_spread(self):
        import numpy as np
        image=Image.new('RGB',(200,100),'white')
        composed,overlay,raw,spread=density_layers(image,[[10,10],[10,10]],opacity=.4,sigma=1)
        self.assertEqual(overlay.mode,'RGBA');self.assertEqual(raw.sum(),2);self.assertAlmostEqual(spread.sum(),2)
        self.assertLessEqual(np.asarray(overlay)[:,:,3].max(),int(.4*255))
        _,empty,_,_=density_layers(image,[],opacity=.4)
        self.assertEqual(np.asarray(empty)[:,:,3].sum(),0)
        self.assertEqual(image.getpixel((10,10)),(255,255,255))
