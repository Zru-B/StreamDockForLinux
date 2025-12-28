"""
Window monitoring for KDE Plasma Wayland to detect active window and trigger layout changes.
"""
import logging
import re
import subprocess
import threading
import time


class WindowMonitor:
    """
    Monitor the active window on KDE Plasma (Wayland) and trigger callbacks when focus changes.
    """
    
    def __init__(self, poll_interval=0.5):
        """
        Initialize the window monitor.
        
        :param poll_interval: How often to check for window changes (in seconds)
        """
        self.logger = logging.getLogger(__name__)
        self.poll_interval = poll_interval
        self.current_window = None
        self.window_rules = []
        self.running = False
        self.monitor_thread = None
        self.default_callback = None
    
    def get_active_window_info(self):
        """
        Get information about the currently active window using multiple methods.
        Tries different approaches for KDE Plasma 6 Wayland compatibility.
        
        :return: Dictionary with window info: {'title': str, 'class': str, 'pid': int}
                 Returns None if unable to get window info
        """
        # Try multiple methods in order of reliability
        
        # Method 1: Try kdotool (best for KDE Wayland)
        window_info = self._try_kdotool()
        if window_info:
            return window_info
        
        # Method 2: Try KWin D-Bus scripting interface
        window_info = self._try_kwin_scripting()
        if window_info:
            return window_info
        
        # Method 3: Try parsing plasma-workspace
        window_info = self._try_plasma_taskmanager()
        if window_info:
            return window_info
        
        # Method 4: Fallback to basic KWin interface
        window_info = self._try_kwin_basic()
        if window_info:
            return window_info
        
        return None
    
    def _try_kdotool(self):
        """Try using kdotool to get active window."""
        try:
            # Get window ID
            result = subprocess.run(
                ['kdotool', 'getactivewindow'],
                capture_output=True,
                text=True,
                timeout=1
            )
            
            if result.returncode != 0:
                return None
            
            window_id = result.stdout.strip()
            
            # Get window title
            result = subprocess.run(
                ['kdotool', 'getwindowname', window_id],
                capture_output=True,
                text=True,
                timeout=1
            )
            
            if result.returncode != 0:
                return None
            
            window_title = result.stdout.strip()
            
            # Try to get actual window class
            result_class = subprocess.run(
                ['kdotool', 'getwindowclassname', window_id],
                capture_output=True,
                text=True,
                timeout=1
            )
            
            if result_class.returncode == 0 and result_class.stdout.strip():
                window_class = result_class.stdout.strip()
            else:
                # Fallback to extracting from title
                window_class = self._extract_app_from_title(window_title)
            
            return {
                'title': window_title,
                'class': window_class,
                'raw': window_title,
                'method': 'kdotool'
            }
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return None
    
    def _try_kwin_scripting(self):
        """Try using KWin scripting D-Bus interface."""
        try:
            # Use KWin's client API through D-Bus
            script = """
            var client = workspace.activeClient;
            if (client) {
                print(client.caption + '|||' + client.resourceClass);
            }
            """
            
            result = subprocess.run(
                ['qdbus', 'org.kde.KWin', '/Scripting', 'org.kde.kwin.Scripting.loadScript', script, 'temp'],
                capture_output=True,
                text=True,
                timeout=1
            )
            
            # This method might not work directly, skip for now
            return None
            
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return None
    
    def _try_plasma_taskmanager(self):
        """Try getting info from plasma task manager."""
        try:
            # Query plasma shell for active window
            result = subprocess.run(
                ['qdbus', 'org.kde.plasmashell', '/PlasmaShell', 'org.kde.PlasmaShell.evaluateScript',
                 'var taskmanager = panelById(panelIds[0]); taskmanager;'],
                capture_output=True,
                text=True,
                timeout=1
            )
            
            # This is complex, skip for now
            return None
            
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
            return None
    
    def _try_kwin_basic(self):
        """Try basic KWin D-Bus interface - using Plasma 6 compatible method."""
        try:
            # For KDE Plasma 6, we need to use a different approach
            # Try to get list of windows and find the active one
            
            # Method 1: Try using qdbus6 (Plasma 6 uses Qt6)
            result = subprocess.run(
                ['bash', '-c',
                 'qdbus6 org.kde.KWin /KWin org.kde.KWin.queryWindowInfo 2>/dev/null || qdbus org.kde.KWin /KWin org.kde.KWin.queryWindowInfo 2>/dev/null || echo ""'],
                capture_output=True,
                text=True,
                timeout=1
            )
            
            if result.returncode == 0 and result.stdout.strip():
                window_title = result.stdout.strip()
                window_class = self._extract_app_from_title(window_title)
                
                return {
                    'title': window_title,
                    'class': window_class,
                    'raw': window_title,
                    'method': 'kwin_plasma6'
                }
            
            # Method 2: Try using busctl to query KWin
            result = subprocess.run(
                ['bash', '-c',
                 'busctl --user get-property org.kde.KWin /KWin org.kde.KWin ActiveWindow 2>/dev/null || echo ""'],
                capture_output=True,
                text=True,
                timeout=1
            )
            
            if result.returncode == 0 and result.stdout.strip() and 'Error' not in result.stdout:
                window_title = result.stdout.strip()
                # Remove busctl formatting
                if window_title.startswith('s '):
                    window_title = window_title[2:].strip('"')
                
                window_class = self._extract_app_from_title(window_title)
                
                return {
                    'title': window_title,
                    'class': window_class,
                    'raw': window_title,
                    'method': 'busctl'
                }
            
            # Method 3: Try using xdotool (X11 fallback)
            result = subprocess.run(
                ['bash', '-c',
                 'xdotool getactivewindow 2>/dev/null || echo ""'],
                capture_output=True,
                text=True,
                timeout=1
            )
            
            if result.returncode == 0 and result.stdout.strip():
                window_id = result.stdout.strip()
                
                # Get window title
                result_title = subprocess.run(
                    ['xdotool', 'getwindowname', window_id],
                    capture_output=True,
                    text=True,
                    timeout=1
                )
                
                window_title = result_title.stdout.strip() if result_title.returncode == 0 else ''
                
                # Get window class (WM_CLASS)
                result_class = subprocess.run(
                    ['xdotool', 'getwindowclassname', window_id],
                    capture_output=True,
                    text=True,
                    timeout=1
                )
                
                if result_class.returncode == 0 and result_class.stdout.strip():
                    window_class = result_class.stdout.strip()
                else:
                    window_class = self._extract_app_from_title(window_title)
                
                return {
                    'title': window_title,
                    'class': window_class,
                    'raw': window_title,
                    'method': 'xdotool_fallback'
                }
            
            return None
            
        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            return None
    
    def _extract_app_from_title(self, title):
        """
        Extract application name from window title.
        Common patterns: "Title - Application" or "Application: Title"
        
        :param title: Window title string
        :return: Extracted application name
        """
        if not title:
            return "unknown"
        
        # Common patterns in window titles
        # "Document Name - Application"
        if ' — ' in title:
            return title.split(' — ')[-1].strip()
        if ' - ' in title:
            parts = title.split(' - ')
            if len(parts) > 1:
                return parts[-1].strip()
        if ': ' in title:
            return title.split(':')[0].strip()
        
        # If no pattern found, try to identify by keywords
        title_lower = title.lower()
        known_apps = {
            'firefox': 'Firefox',
            'chrome': 'Chrome',
            'konsole': 'Konsole',
            'kate': 'Kate',
            'dolphin': 'Dolphin',
            'spotify': 'Spotify',
            'discord': 'Discord',
            'slack': 'Slack',
            'code': 'VSCode',
            'pycharm': 'PyCharm',
            'intellij': 'IntelliJ',
        }
        
        for keyword, app_name in known_apps.items():
            if keyword in title_lower:
                return app_name
        
        # Return first word of title as fallback
        return title.split()[0] if title.split() else "unknown"
    
    def add_window_rule(self, pattern, callback, match_field='class'):
        """
        Add a rule that triggers a callback when a window matching the pattern is focused.
        
        :param pattern: String or regex pattern to match against window info
        :param callback: Function to call when pattern matches. Signature: callback(window_info)
        :param match_field: Which field to match against: 'title', 'class', or 'raw'
        """
        rule = {
            'pattern': pattern,
            'callback': callback,
            'match_field': match_field,
            'is_regex': isinstance(pattern, re.Pattern)
        }
        self.window_rules.append(rule)
    
    def set_default_callback(self, callback):
        """
        Set a callback to trigger when no window rules match.
        
        :param callback: Function to call when no rules match. Signature: callback(window_info)
        """
        self.default_callback = callback
    
    def _check_rules(self, window_info):
        """
        Check if any rules match the current window and execute callbacks.
        
        :param window_info: Dictionary with window information
        """
        if not window_info:
            return
        
        matched = False
        
        for rule in self.window_rules:
            field_value = window_info.get(rule['match_field'], '')
            pattern = rule['pattern']
            
            # Check if pattern matches
            match = False
            if rule['is_regex']:
                match = pattern.search(field_value) is not None
            else:
                match = pattern.lower() in field_value.lower()
            
            if match:
                matched = True
                try:
                    rule['callback'](window_info)
                except Exception:
                    self.logger.exception("Error executing window rule callback")
                break  # Only trigger first matching rule
        
        # If no rules matched, call default callback
        if not matched and self.default_callback:
            try:
                self.default_callback(window_info)
            except Exception:
                self.logger.exception("Error executing default callback")
    
    def _monitor_loop(self):
        """
        Main monitoring loop that runs in a separate thread.
        """
        while self.running:
            try:
                window_info = self.get_active_window_info()
                
                # Check if window has changed
                if window_info:
                    window_id = f"{window_info['title']}|{window_info['class']}"
                    
                    if window_id != self.current_window:
                        self.current_window = window_id
                        self._check_rules(window_info)
                
                time.sleep(self.poll_interval)
                
            except Exception:
                self.logger.exception("Error in window monitor")
                time.sleep(self.poll_interval)
    
    def start(self):
        """
        Start monitoring window focus changes in a background thread.
        """
        if self.running:
            return
        
        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop(self):
        """
        Stop monitoring window focus changes.
        """
        if not self.running:
            return
        
        self.running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
    
    def clear_rules(self):
        """
        Clear all window rules.
        """
        self.window_rules.clear()
