import copy
import unittest
from recorder.targeting import calibrate, classify, content_rect, frame_point, same_identity, title_digest


def observation(**changes):
    data = {'identity': {'hwnd': 42, 'pid': 100, 'process_started': 123,
                         'class_name': 'Chrome_WidgetWin_1', 'executable': 'chrome.exe'},
            'client_rect': [-1200, 20, 1000, 800], 'window_rect': [-1208, 12, 1016, 816],
            'dpi': 96, 'title_digest': title_digest('MapGen'), 'stable': True,
            'visible': True, 'minimized': False, 'cloaked': False,
            'hit_root': 42, 'hit_hwnd': 43, 'capture_root': 0,
            'foreground_root': 42, 'possible_occluders': []}
    data.update(changes)
    return data


def calibration():
    return calibrate(observation(), (-1200, 120), (-201, 819))


class TargetTests(unittest.TestCase):
    def test_identity_uses_handle_pid_start_and_class_not_title(self):
        expected = calibration()['identity']
        self.assertTrue(same_identity(expected, copy.deepcopy(expected)))
        for key in ('hwnd', 'pid', 'process_started', 'class_name'):
            actual = dict(expected)
            actual[key] = 'different'
            self.assertFalse(same_identity(expected, actual))
            self.assertEqual(classify(-1100,200,calibration(),observation(identity=actual))['classification'],'uncertain')
        self.assertFalse(same_identity({}, {}))

    def test_content_excludes_browser_toolbar_and_half_open_edges(self):
        for point in [(-1200,120), (-201,819), (-700,400)]:
            self.assertEqual(classify(*point,calibration(),observation())['classification'],'inside')
        for point in [(-1200,119), (-200,200), (-1201,200), (-400,820)]:
            self.assertEqual(classify(*point,calibration(),observation())['classification'],'outside')

    def test_foreground_is_not_the_only_test(self):
        # Hover/scroll over unobscured Chrome while another app is foreground.
        inside = classify(-1100,200,calibration(),observation(foreground_root=999))
        self.assertEqual(inside['classification'],'inside')
        covered = classify(-1100,200,calibration(),observation(hit_root=999,foreground_root=42))
        self.assertEqual(covered['classification'],'outside')
        self.assertEqual(covered['reason'],'other_window_at_point')

    def test_capture_by_another_window_and_transparent_overlay(self):
        self.assertEqual(classify(-1100,200,calibration(),observation(capture_root=99))['classification'],'outside')
        self.assertEqual(classify(-1100,200,calibration(),observation(possible_occluders=[99]))['classification'],'uncertain')

    def test_uncertain_failed_hit_test_changed_title_and_transition(self):
        for snap in [None, {'error':'access denied'}, observation(hit_root=0),
                     observation(capture_root=None), observation(stable=False),
                     observation(title_digest=title_digest('Different tab'))]:
            self.assertEqual(classify(-1100,200,calibration(),snap)['classification'],'uncertain')

    def test_hidden_minimized_cloaked_excluded(self):
        for snap in [observation(visible=False), observation(minimized=True), observation(cloaked=True)]:
            self.assertEqual(classify(-1100,200,calibration(),snap)['classification'],'outside')

    def test_movement_resize_and_negative_monitors(self):
        c = calibration()
        moved = observation(client_rect=[100,50,1000,800])
        result = classify(200,250,c,moved)
        self.assertEqual(result['classification'],'inside')
        self.assertEqual(result['local'],[100,100])
        self.assertEqual(result['normalized'],[.1,1/7])
        large = observation(client_rect=[-1920,-200,1920,1080])
        result = classify(-1800,0,c,large)
        self.assertEqual(result['local'],[120,100])
        self.assertEqual(result['content_rect'],[-1920,-100,1920,980])
        self.assertNotEqual(result['layout_key'],classify(-1100,200,c,observation())['layout_key'])

    def test_dpi_scaled_insets_and_layout_separation(self):
        snap = observation(client_rect=[-1800,-300,1500,1200],dpi=144)
        self.assertEqual(content_rect(calibration(),snap),[-1800,-150,1500,1050])
        result = classify(-1650,0,calibration(),snap)
        self.assertEqual(result['local'],[150,150])
        self.assertEqual(result['classification'],'inside')
        self.assertEqual(result['layout_key'],'1500x1050-dpi144')

    def test_bad_calibration_is_rejected(self):
        for first,last in [((-1300,0),(-201,819)), ((-201,819),(-1200,120))]:
            with self.assertRaises(ValueError):
                calibrate(observation(), first, last)
        result = classify(-1100,200,calibration(),observation(client_rect=[0,0,100,50]))
        self.assertEqual(result['classification'],'uncertain')

    def test_crop_scaling_letterbox_alignment(self):
        mapping = {'content_size':[1000,700], 'source_rect':[100,50,800,600],
                   'frame_rect':[200,100,1600,900]}
        self.assertEqual(frame_point([100,50],[1000,700],mapping),[200,100])
        self.assertEqual(frame_point([500,350],[1000,700],mapping),[1000,550])
        self.assertIsNone(frame_point([99,50],[1000,700],mapping))
        with self.assertRaises(ValueError):
            frame_point([100,50],[999,700],mapping)


    def test_maximize_transition_requires_content_recalibration(self):
        snap = observation(maximized=True)
        self.assertEqual(classify(-1100,200,calibration(),snap)['classification'],'uncertain')
        updated = calibrate(snap,(-1200,120),(-201,819))
        self.assertEqual(classify(-1100,200,updated,snap)['classification'],'inside')
