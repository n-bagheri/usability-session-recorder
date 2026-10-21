"""Mock Win32 adapters on Linux; these are not real Windows validation."""
import ctypes
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from recorder import windows


class WindowsAdapterTests(unittest.TestCase):
    def test_enumeration_uses_process_class_and_handle_not_title(self):
        enum = Mock()
        def enumerate_windows(callback, param):
            for hwnd in (0x100000042, 88, 99):
                callback(hwnd,param)
            return 1
        enum.side_effect = enumerate_windows
        user = SimpleNamespace(EnumWindows=enum,IsWindowVisible=lambda h:True)
        def identity(user,hwnd):
            return {'hwnd':hwnd,'pid':1,'process_started':2,
                    'executable':'chrome.exe' if hwnd != 88 else 'other.exe',
                    'class_name':'Chrome_WidgetWin_1' if hwnd != 99 else 'OtherClass'}
        # On Linux, stand in for ctypes' Windows callback factory.
        with patch.object(windows,'api',return_value=user), \
             patch.object(windows,'_identity',side_effect=identity), \
             patch.object(windows,'_title',return_value='MapGen'), \
             patch.object(ctypes,'WINFUNCTYPE',return_value=lambda f:f,create=True):
            offered = windows.chrome_windows()
        self.assertEqual(len(offered),1)
        self.assertEqual(offered[0]['identity']['hwnd'],0x100000042)

    def test_window_geometry_failure_becomes_observation_error(self):
        with patch.object(windows,'api',return_value=object()), \
             patch.object(windows,'_identity',side_effect=OSError('window closed')):
            self.assertEqual(windows.target_snapshot(42,10,20),{'error':'window closed'})
