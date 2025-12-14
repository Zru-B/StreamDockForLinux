import evdev
from evdev import UInput, ecodes
import time
import logging
import threading

logger = logging.getLogger(__name__)

class VirtualKeyboard:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(VirtualKeyboard, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        
        self.device = None
        self.available = False
        self._setup_device()
        self._initialized = True

    def _setup_device(self):
        """Initialize the uinput device."""
        try:
            # Define capabilities - we want all keys
            cap = {
                ecodes.EV_KEY: self._get_all_keys()
            }
            
            self.device = UInput(cap, name='StreamDock-Virtual-Keyboard')
            self.available = True
            logger.info("Virtual Keyboard initialized successfully")
            
        except PermissionError:
            logger.warning("Permission denied accessing /dev/uinput. Virtual Keyboard will be disabled.")
            logger.warning("Please configure udev rules as described in SETUP_UDEV.md")
            self.available = False
        except Exception as e:
            logger.error(f"Failed to initialize Virtual Keyboard: {e}")
            self.available = False

    def _get_all_keys(self):
        """Get a list of all key constants from ecodes."""
        keys = []
        for name in dir(ecodes):
            if name.startswith('KEY_'):
                val = getattr(ecodes, name)
                if isinstance(val, int) and val < ecodes.KEY_CNT:
                    keys.append(val)
        return keys

    def _get_keycode(self, key_name):
        """Convert string key name to evdev keycode."""
        # Clean up and normalize key name
        key_name = key_name.upper().replace(' ', '_')
        
        # Mapping for common differences
        mapping = {
            'CTRL': 'KEY_LEFTCTRL',
            'CONTROL': 'KEY_LEFTCTRL',
            'LCTRL': 'KEY_LEFTCTRL',
            'RCTRL': 'KEY_RIGHTCTRL',
            'ALT': 'KEY_LEFTALT',
            'LALT': 'KEY_LEFTALT',
            'RALT': 'KEY_RIGHTALT',
            'SHIFT': 'KEY_LEFTSHIFT',
            'LSHIFT': 'KEY_LEFTSHIFT',
            'RSHIFT': 'KEY_RIGHTSHIFT',
            'META': 'KEY_LEFTMETA',
            'SUPER': 'KEY_LEFTMETA',
            'WIN': 'KEY_LEFTMETA',
            'CMD': 'KEY_LEFTMETA',
            'ENTER': 'KEY_ENTER',
            'RETURN': 'KEY_ENTER',
            'ESC': 'KEY_ESC',
            'ESCAPE': 'KEY_ESC',
            'DEL': 'KEY_DELETE',
            'BACKSPACE': 'KEY_BACKSPACE',
            'INS': 'KEY_INSERT',
            'CAPS': 'KEY_CAPSLOCK',
            'TAB': 'KEY_TAB',
            'SPACE': 'KEY_SPACE',
            # Function keys
            'F1': 'KEY_F1', 'F2': 'KEY_F2', 'F3': 'KEY_F3', 'F4': 'KEY_F4',
            'F5': 'KEY_F5', 'F6': 'KEY_F6', 'F7': 'KEY_F7', 'F8': 'KEY_F8',
            'F9': 'KEY_F9', 'F10': 'KEY_F10', 'F11': 'KEY_F11', 'F12': 'KEY_F12',
            # Arrows
            'UP': 'KEY_UP', 'DOWN': 'KEY_DOWN', 
            'LEFT': 'KEY_LEFT', 'RIGHT': 'KEY_RIGHT',
            'PAGEUP': 'KEY_PAGEUP', 'PAGEDOWN': 'KEY_PAGEDOWN',
            'HOME': 'KEY_HOME', 'END': 'KEY_END',
        }
        
        if key_name in mapping:
            return getattr(ecodes, mapping[key_name])
            
        # Try direct mapping (KEY_A, KEY_1, etc.)
        evdev_name = f"KEY_{key_name}"
        if hasattr(ecodes, evdev_name):
            return getattr(ecodes, evdev_name)
            
        # Try single character mapping if it's alphanumeric
        if len(key_name) == 1:
            if key_name.isdigit():
                 evdev_name = f"KEY_{key_name}"
            elif key_name.isalpha():
                 evdev_name = f"KEY_{key_name}"
            
            if hasattr(ecodes, evdev_name):
                return getattr(ecodes, evdev_name)
                
        logger.warning(f"Unknown key: {key_name}")
        return None

    def press_key(self, key_code):
        """Press (hold down) a key."""
        if not self.available:
            return
        try:
            self.device.write(ecodes.EV_KEY, key_code, 1)
            self.device.syn()
        except Exception as e:
            logger.error(f"Error pressing key: {e}")

    def release_key(self, key_code):
        """Release a key."""
        if not self.available:
            return
        try:
            self.device.write(ecodes.EV_KEY, key_code, 0)
            self.device.syn()
        except Exception as e:
            logger.error(f"Error releasing key: {e}")

    def tap_key(self, key_code, duration=0.05):
        """Press and release a key."""
        if not self.available:
            return
        self.press_key(key_code)
        time.sleep(duration)
        self.release_key(key_code)

    def send_combo(self, combo_string):
        """
        Send a key combination.
        Format: "CTRL+C", "ALT+SHIFT+ESC", etc.
        """
        if not self.available:
            return False
            
        keys = [k.strip() for k in combo_string.split('+')]
        key_codes = []
        
        for k in keys:
            code = self._get_keycode(k)
            if code:
                key_codes.append(code)
            else:
                logger.error(f"Could not map key '{k}' in combo '{combo_string}'")
                return False
                
        # Press all keys in order
        for code in key_codes:
            self.press_key(code)
            
        time.sleep(0.05)
        
        # Release all keys in reverse order
        for code in reversed(key_codes):
            self.release_key(code)
            
        return True

    def type_string(self, text, delay=0.01):
        """
        Type a string of text.
        Note: This maps characters to keystrokes.
        Simple logic for now: assumes US layout logic for shifts.
        """
        if not self.available:
            return False
            
        # Mapping for special chars that need SHIFT
        shift_chars = {
            '!': '1', '@': '2', '#': '3', '$': '4', '%': '5', '^': '6',
            '&': '7', '*': '8', '(': '9', ')': '0', '_': '-', '+': '=',
            '{': '[', '}': ']', '|': '\\', ':': ';', '"': '\'', '<': ',',
            '>': '.', '?': '/', '~': '`'
        }
        
        for char in text:
            time.sleep(delay)
            
            if char.isupper() or char in shift_chars:
                # Hold Shift
                self.press_key(ecodes.KEY_LEFTSHIFT)
                
                # Get the base character
                if char in shift_chars:
                    target_char = shift_chars[char]
                else:
                    target_char = char.lower()
                    
                # Type the key
                code = self._get_keycode(target_char)
                if code:
                    self.tap_key(code)
                
                # Release Shift
                self.release_key(ecodes.KEY_LEFTSHIFT)
                
            else:
                # Normal character
                code = self._get_keycode(char.upper())
                if code:
                     self.tap_key(code)
                elif char == ' ':
                     self.tap_key(ecodes.KEY_SPACE)
                elif char == '\t':
                     self.tap_key(ecodes.KEY_TAB)
                elif char == '\n':
                     self.tap_key(ecodes.KEY_ENTER)
                else:
                    # Fallback for unhandled chars
                    logger.warning(f"Character '{char}' not supported in virtual keyboard typing yet")
                    
        return True

    def close(self):
        """Close the uinput device."""
        if self.device:
            self.device.close()
            self.available = False
