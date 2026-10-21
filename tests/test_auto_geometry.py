import unittest
from recorder.viewport import choose_document
from recorder.obs_geometry import compute_mapping,project,associate
from test_targeting import observation,calibration
from recorder.targeting import classify


class AutoGeometryTests(unittest.TestCase):
    def test_unique_viewport_nested_docs_and_ambiguous_panels(self):
        doc = {'rect':[-1000,120,900,600],'offscreen':False}
        nested = {'rect':[-900,200,100,100],'offscreen':False}
        self.assertEqual(choose_document([nested,doc],[-1000,0,1000,800]),doc)
        with self.assertRaises(ValueError):
            choose_document([nested,{'rect':[-700,200,100,100]}],[-1000,0,1000,800])
        with self.assertRaises(ValueError):
            choose_document([{'rect':[-1000,0,1000,2000]}],[-1000,0,1000,800])

    def test_obs_crop_bounds_letterbox_and_output_scaling(self):
        t = {'sourceWidth':1000,'sourceHeight':800,'positionX':100,'positionY':50,'alignment':5,
             'scaleX':1,'scaleY':1,'cropLeft':100,'cropRight':100,'cropTop':0,'cropBottom':0,
             'boundsType':'OBS_BOUNDS_SCALE_INNER','boundsWidth':800,'boundsHeight':600,'boundsAlignment':0}
        m = compute_mapping([-1000,0,1000,800],[-1000,100,1000,700],t,[1000,800],[2000,1600])
        # Cropped 800x800 scales .75; centered in 800x600 adds 100px horizontal letterbox.
        self.assertEqual(project(m,[100,0]),[400,250])
        self.assertEqual(project(m,[500,300]),[1000,700])
        self.assertIsNone(project(m,[0,0]))
        with self.assertRaises(ValueError):
            compute_mapping([-1000,0,1000,800],[-1000,100,1000,700],dict(t,rotation=45),[1000,800],[1000,800])

    def test_window_association_rejects_identical_titles(self):
        w = {'identity':observation()['identity'],'title':'MapGen'}
        settings = {'window':'MapGen:Chrome_WidgetWin_1:chrome.exe'}
        self.assertEqual(associate(settings,w,[w]),'unique_title_class_executable')
        with self.assertRaises(ValueError):
            associate(settings,w,[w,dict(w,identity=dict(w['identity'],hwnd=99))])

    def test_automatic_viewport_uses_fresh_geometry_not_fixed_toolbar_insets(self):
        c = dict(calibration(),method='automatic_uia_obs')
        s = observation(viewport={'rect':[-1200,155,1000,665]})
        self.assertEqual(classify(-1100,140,c,s)['classification'],'outside')
        self.assertEqual(classify(-1100,160,c,s)['local'],[100,5])
        s['viewport_error'] = 'stale'
        self.assertEqual(classify(-1100,160,c,s)['classification'],'uncertain')

    def test_monitor_invalidates_stale_geometry_and_journals_observations(self):
        import tempfile
        import json
        from pathlib import Path
        from unittest.mock import patch
        from recorder.capture import CalibrationMonitor
        s=observation(monitor=1)
        selected={'identity':s['identity'],'title':'MapGen'}
        viewport=lambda *_:{'rect':[-1200,120,1000,700],'zoom_monitoring':'unavailable_keep_browser_zoom_fixed'}
        monitor=CalibrationMonitor(None,selected,lambda *_:dict(s),viewport,lambda:[selected])
        with patch('recorder.capture.read_obs_capture',return_value={'id':'one','source_name':'capture'}),tempfile.TemporaryDirectory() as directory:
            c=monitor.calibration();monitor.bind(directory)
            self.assertEqual(c['method'],'automatic_uia_obs')
            fresh=monitor.observe(42,-1100,200)
            self.assertIn('viewport',fresh)
            s['client_rect']=[0,0,1000,800]
            stale=monitor.observe(42,100,200)
            self.assertIn('viewport_error',stale)
            observations=[json.loads(line) for line in (Path(directory)/'calibration_observations.jsonl').read_text().splitlines()]
            self.assertEqual(len(observations),1)

    def test_full_obs_read_uses_real_scene_source_profile_and_output_settings(self):
        from types import SimpleNamespace as S
        from recorder.obs_geometry import read_obs_capture
        selected={'identity':observation()['identity'],'title':'MapGen'}
        t={'sourceWidth':1000,'sourceHeight':800,'positionX':0,'positionY':0,'alignment':5,'scaleX':1,'scaleY':1}
        item={'sourceName':'Chrome Capture','sceneItemId':3,'sceneItemIndex':0,'sceneItemEnabled':True}
        obs=S(get_current_program_scene=lambda:S(current_program_scene_name='Scene'),
              get_scene_item_list=lambda _:S(scene_items=[item]),
              get_input_settings=lambda _:S(input_kind='window_capture',input_settings={'window':'MapGen:Chrome_WidgetWin_1:chrome.exe','client_area':True}),
              get_scene_item_transform=lambda *_:S(scene_item_transform=t),
              get_profile_parameter=lambda *_:S(parameter_value='Simple'),get_source_filter_list=lambda _:S(filters=[]),
              get_video_settings=lambda:S(base_width=1000,base_height=800,output_width=500,output_height=400))
        result=read_obs_capture(obs,selected,[selected],observation(),{'rect':[-1200,120,1000,700]})
        self.assertEqual(result['source_name'],'Chrome Capture')
        self.assertEqual(project(result,[200,100]),[100,100])
        t['rotation']=90
        with self.assertRaises(ValueError):read_obs_capture(obs,selected,[selected],observation(),{'rect':[-1200,120,1000,700]})

    def test_stretch_and_center_anchor(self):
        capture=[0,0,1000,800];viewport=[0,100,1000,700]
        transform={'sourceWidth':1000,'sourceHeight':800,'scaleX':1,'scaleY':1,
                   'positionX':500,'positionY':400,'alignment':0,'boundsType':'OBS_BOUNDS_NONE'}
        mapping=compute_mapping(capture,viewport,transform,[1000,800],[1000,800])
        self.assertEqual(project(mapping,[200,100]),[200,200])
        transform.update(positionX=10,positionY=20,alignment=5,boundsType='OBS_BOUNDS_STRETCH',boundsWidth=500,boundsHeight=200)
        mapping=compute_mapping(capture,viewport,transform,[1000,800],[1000,800])
        self.assertEqual(project(mapping,[200,100]),[110,70])

    def test_profile_defaults_are_read_from_obs_not_invented(self):
        from types import SimpleNamespace as S
        from recorder.obs_geometry import profile_value
        obs=S(get_profile_parameter=lambda *_:S(parameter_value=None,default_parameter_value='Simple'))
        self.assertEqual(profile_value(obs,'Output','Mode'),'Simple')
        obs.get_profile_parameter=lambda *_:S(parameter_value=None,default_parameter_value=None)
        with self.assertRaises(ValueError):profile_value(obs,'Output','Mode')
