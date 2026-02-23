from enum import Enum, auto

class ActionType(Enum):
    EXECUTE_COMMAND = auto()
    KEY_PRESS = auto()
    TYPE_TEXT = auto()
    WAIT = auto()
    CHANGE_KEY_IMAGE = auto()
    CHANGE_KEY_TEXT = auto()
    CHANGE_KEY = auto()
    CHANGE_LAYOUT = auto()
    DBUS = auto()
    DEVICE_BRIGHTNESS_UP = auto()
    DEVICE_BRIGHTNESS_DOWN = auto()
    LAUNCH_APPLICATION = auto()
