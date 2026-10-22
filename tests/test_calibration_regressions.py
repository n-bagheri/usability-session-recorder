import unittest
from recorder.viewport import choose_document


class ViewportRegressionTests(unittest.TestCase):
    def test_reported_bottom_strip_and_narrow_candidates_are_rejected(self):
        for rect in ([0,1043,1920,84],[0,100,80,900],[0,0,1920,60],[0,900,1920,220],[-1,100,1920,900]):
            with self.subTest(rect=rect),self.assertRaises(ValueError):
                choose_document([{'rect':rect,'offscreen':False}],[0,0,1920,1127])

    def test_normal_viewports_at_scaled_and_negative_monitor_positions(self):
        for client,rect in (([0,0,1920,1127],[0,150,1920,977]),([-1920,-200,1920,1100],[-1920,-50,1920,950])):
            chosen=choose_document([{'rect':rect,'offscreen':False}],client)
            self.assertEqual(chosen['rect'],rect)
            self.assertIn('sanity',chosen)
