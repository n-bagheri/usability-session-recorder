import copy
import unittest
from recorder.corrections import fit_registration,geometry_key,corrected_target,corrected_mapping,active_registration
from recorder.obs_geometry import project
from test_targeting import observation


class MappingCorrectionTests(unittest.TestCase):
    def fixtures(self):
        s=observation();s['client_rect']=[0,0,320,240];s['viewport']={'rect':[0,210,320,30]}
        segment={'id':'home','start':0,'end':2,'view':'Home','state':'Home'}
        anchors=[]
        for i,(x,y) in enumerate(((50,80),(260,190))):
            anchors.append({'event_id':str(i),'desktop':[x,y],'observed':[x+40,y+30],
                'geometry_key':geometry_key(s),'client_rect':s['client_rect'],
                'frame':{'seconds':.5+i,'video_fingerprint':'synthetic'},'uncertainty_px':2})
        correction=fit_registration(segment,anchors,[40,50,320,220],'synthetic')
        return s,correction

    def test_bad_viewport_is_reconstructed_but_other_windows_remain_outside(self):
        s,c=self.fixtures();e={'x':50,'y':80,'target_observation':s}
        target=corrected_target(e,c)
        self.assertEqual(target['classification'],'inside')
        self.assertEqual(project(corrected_mapping(c,[400,300]),target['local']),[90,110])
        s['hit_root']=999
        self.assertEqual(corrected_target(e,c)['classification'],'outside')
        self.assertEqual(c['status'],'researcher_adjusted_unverified');self.assertGreater(c['reference_uncertainty_px'],0)

    def test_correction_scope_geometry_hash_and_undo(self):
        s,c=self.fixtures();review={'mapping_corrections':[c]};event={'target_observation':s}
        self.assertEqual(active_registration(event,1,review,'synthetic'),c)
        self.assertIsNone(active_registration(event,3,review,'synthetic'))
        changed=copy.deepcopy(s);changed['dpi']=144
        self.assertIsNone(active_registration({'target_observation':changed},1,review,'synthetic'))
        c['confirmed']=False
        self.assertIsNone(active_registration(event,1,review,'synthetic'))

    def test_annotation_boundary_band_remains_uncertain(self):
        s,c=self.fixtures()
        self.assertEqual(corrected_target({'x':1,'y':30,'target_observation':s},c)['classification'],'uncertain')

    def test_raw_source_changes_in_failed_detection_invalidate_registration(self):
        s,c=self.fixtures()
        s['automatic_calibration']={'obs_capture_evidence':{'scene_transform':{'scaleX':1}}}
        c['geometry_key']=geometry_key(s)
        review={'mapping_corrections':[c]}
        self.assertIsNotNone(active_registration({'target_observation':s},1,review,'synthetic'))
        s['automatic_calibration']['obs_capture_evidence']['scene_transform']['scaleX']=2
        self.assertIsNone(active_registration({'target_observation':s},1,review,'synthetic'))

    def test_correction_does_not_override_original_target_identity(self):
        s,c=self.fixtures();expected=copy.deepcopy(s['identity']);expected['pid']+=1
        result=corrected_target({'x':50,'y':80,'target_observation':s},c,expected)
        self.assertNotEqual(result['classification'],'inside')
