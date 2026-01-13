import pytest
import re
import os
import time
import subprocess
from unittest.mock import MagicMock, call, patch
from StreamDock.Models import WindowInfo
from StreamDock.window_detection import (
    KWinDynamicScriptingDetection,
    KWinBasicDetection,
    SimulationDetection,
    XWindowDetection,
    KdotoolDetection,
    PlasmaTaskManagerDetection
)

class TestKWinDynamicScriptingDetection:
    @pytest.fixture
    def detector(self):
        return KWinDynamicScriptingDetection()

    @patch('time.time')
    @patch('tempfile.NamedTemporaryFile')
    @patch('subprocess.run')
    def test_detect_success(self, mock_run, mock_tempfile, mock_time, detector):
        """Test successful detection with dynamic scripting."""
        mock_time.return_value = 12.345
        marker = "STREAMDOCK_QUERY_12345"
        
        # Mock temp file
        mock_tmp = MagicMock()
        mock_tmp.name = "/tmp/test.js"
        mock_tempfile.return_value.__enter__.return_value = mock_tmp
        
        # Mock sequence of subprocess calls
        def run_side_effect(*args, **kwargs):
            cmd = args[0]
            # Load script
            if 'loadScript' in cmd:
                return MagicMock(returncode=0, stdout="123\n")
            # Run script
            if 'run' in repr(cmd) and 'Script123' in repr(cmd):
                return MagicMock(returncode=0)
            # Journal query
            if cmd[0] == 'journalctl':
                return MagicMock(returncode=0, stdout=f"Jan 01 10:00:00 host kwin: js: {marker}:My Window Title|MyClass\n")
            return MagicMock(returncode=0)

        mock_run.side_effect = run_side_effect
        
        info = detector.detect()
        
        assert info is not None
        assert info.title == "My Window Title"
        assert info.class_name == "MyClass"
        assert info.method == "kwin_dynamic"

    @patch('subprocess.run')
    def test_load_script_failure(self, mock_run, detector):
        """Test failure when loading script."""
        mock_run.return_value = MagicMock(returncode=1, stderr="Error loading")
        assert detector.detect() is None
        
    @patch('time.time')
    @patch('tempfile.NamedTemporaryFile')
    @patch('subprocess.run')
    def test_marker_not_found(self, mock_run, mock_tempfile, mock_time, detector):
        """Test when marker is not found in journal."""
        mock_time.return_value = 12.345
        
        # Mock temp file
        mock_tmp = MagicMock()
        mock_tmp.name = "/tmp/test.js"
        mock_tempfile.return_value.__enter__.return_value = mock_tmp
        
        def run_side_effect(*args, **kwargs):
            cmd = args[0]
            if 'loadScript' in cmd:
                return MagicMock(returncode=0, stdout="123\n")
            if cmd[0] == 'journalctl':
                return MagicMock(returncode=0, stdout="Other logs\n")
            return MagicMock(returncode=0)

        mock_run.side_effect = run_side_effect
        
        assert detector.detect() is None

class TestKWinBasicDetection:
    @pytest.fixture
    def detector(self):
        return KWinBasicDetection()

    @patch('subprocess.run')
    def test_method1_qdbus6_success(self, mock_run, detector):
        """Test success via qdbus6."""
        mock_run.return_value = MagicMock(returncode=0, stdout="My Window\n")
        
        # Mock WindowUtils to avoid external dependencies if possible, 
        # but here we rely on it being imported inside the method.
        # Ideally we'd mock it, but simpler to rely on real util for now if it doesn't do I/O.
        
        info = detector.detect()
        assert info is not None
        assert info.title == "My Window"
        assert info.method == "kwin_plasma6"

    @patch('subprocess.run')
    def test_method2_busctl_success(self, mock_run, detector):
        """Test success via busctl."""
        # Fail first method
        fail = MagicMock(returncode=1)
        # Succeed second method
        success = MagicMock(returncode=0, stdout='s "Active Window"\n')
        
        mock_run.side_effect = [fail, success]
        
        info = detector.detect()
        assert info is not None
        assert info.title == "Active Window"
        assert info.method == "busctl"

    @patch('subprocess.run')
    def test_method3_xdotool_fallback(self, mock_run, detector):
        """Test fallback to xdotool within KWinBasic."""
        fail = MagicMock(returncode=1)
        # xdotool activewindow
        xdo_id = MagicMock(returncode=0, stdout="123\n")
        # xdotool getwindowname
        xdo_name = MagicMock(returncode=0, stdout="X11 Window\n")
        # xdotool getwindowclassname
        xdo_class = MagicMock(returncode=0, stdout="X11Class\n")
        
        mock_run.side_effect = [fail, fail, xdo_id, xdo_name, xdo_class]
        
        info = detector.detect()
        assert info is not None
        assert info.title == "X11 Window"
        assert info.class_name == "X11Class"
        assert info.method == "kwin_basic_x11"

class TestSimulationDetection:
    @pytest.fixture
    def detector(self):
        return SimulationDetection("/tmp/test_sim_window")

    def test_detect_file_exists(self, detector):
        with patch('os.path.exists', return_value=True), \
             patch('builtins.open', new_callable=MagicMock) as mock_open:
            
            mock_open.return_value.__enter__.return_value.read.return_value = "SimTitle|SimClass"
            
            info = detector.detect()
            assert info is not None
            assert info.title == "SimTitle"
            assert info.class_name == "SimClass"
            assert info.method == "simulation"

    def test_detect_no_file(self, detector):
        with patch('os.path.exists', return_value=False):
            assert detector.detect() is None
