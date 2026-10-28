import logging
import os
import threading
from collections import OrderedDict

from StreamDock.image_helpers.pil_helper import load_image, render_key_image

logger = logging.getLogger(__name__)

KEY_IMAGE_SIZE = (112, 112)

# Rendered key images, shared by every Key: a layout is rebuilt per slot and on
# every reload, and switching windows re-applies layouts constantly. Keyed by
# the icon's mtime as well as its path, so an icon edited on disk is picked up.
_IMAGE_CACHE_SIZE = 256
_image_cache: "OrderedDict[tuple, object]" = OrderedDict()
_image_cache_lock = threading.Lock()


def _cached_image(cache_key, build):
    with _image_cache_lock:
        image = _image_cache.get(cache_key)
        if image is not None:
            _image_cache.move_to_end(cache_key)
            return image
    image = build()
    with _image_cache_lock:
        _image_cache[cache_key] = image
        while len(_image_cache) > _IMAGE_CACHE_SIZE:
            _image_cache.popitem(last=False)
    return image


def _load_icon(path):
    image, temp_file = load_image(path, target_size=KEY_IMAGE_SIZE)
    try:
        image.load()
        return image.resize(KEY_IMAGE_SIZE) if image.size != KEY_IMAGE_SIZE else image.copy()
    finally:
        if temp_file and os.path.exists(temp_file):
            os.remove(temp_file)


class Key:
    """
    Represents a configurable key on the StreamDock device.

    Creating a Key instance automatically configures the key's image and callbacks
    on the provided device.

    A key can be rendered in three modes:
    - **Icon-only**: supply ``image_path``, leave ``text`` empty.
    - **Text-only**: leave ``image_path`` empty, supply ``text``.
    - **Icon + text overlay**: supply both; text is drawn on top of the icon.
    """

    # Mapping from hardware key numbers to logical key numbers
    KEY_MAPPING = {
        1: 11, 2: 12, 3: 13, 4: 14,
        5: 15, 6: 6, 7: 7, 8: 8,
        9: 9, 10: 10, 11: 1, 12: 2,
        13: 3, 14: 4, 15: 5
    }

    def __init__(
        self,
        device,
        key_number,
        image_path,
        on_press=None,
        on_release=None,
        on_double_press=None,
        action_executor=None,
        on_long_press=None,
        # --- text rendering ---
        text: str = '',
        text_color: str = 'white',
        background_color: str = 'black',
        font_size: int = 20,
        bold: bool = True,
        text_position: str = 'bottom',
    ):
        """
        Initialize and configure a key on the StreamDock device.

        :param device: The StreamDock device instance
        :param key_number: Physical key number (1-15)
        :param image_path: Path to the image file for this key (can be empty
                           when text-only rendering is desired)
        :param on_press: Optional callback or action list for key press
        :param on_release: Optional callback or action list for key release
        :param on_double_press: Optional callback or action list for double press
        :param action_executor: Optional ActionExecutor instance
        :param on_long_press: Optional callback or action list for long press
        :param text: Optional text label to render on the key
        :param text_color: Text colour (name or hex string, default 'white')
        :param background_color: Background colour used in text-only mode
        :param font_size: Font size in pixels (default 20)
        :param bold: Use bold font variant when available (default True)
        :param text_position: Where to place text when both icon and text are
                              set – 'bottom' (default), 'top', or 'center'
        """
        self.device = device
        self.key_number = key_number
        self.image_path = image_path
        self.action_executor = action_executor

        # Text rendering configuration
        self.text = text or ''
        self.text_color = text_color
        self.background_color = background_color
        self.font_size = font_size
        self.bold = bold
        self.text_position = text_position

        # Store the original actions/callbacks
        self.on_press_actions = on_press
        self.on_release_actions = on_release
        self.on_double_press_actions = on_double_press
        self.on_long_press_actions = on_long_press

        # Convert actions to callback functions
        self.on_press = self._create_callback(on_press) if on_press else None
        self.on_release = self._create_callback(on_release) if on_release else None
        self.on_double_press = self._create_callback(on_double_press) if on_double_press else None
        self.on_long_press = self._create_callback(on_long_press) if on_long_press else None

        # Get the logical key number for callback registration
        self.logical_key = self.KEY_MAPPING.get(key_number, key_number)

    # ------------------------------------------------------------------
    # Image rendering
    # ------------------------------------------------------------------

    def _render_image(self):
        """
        The PIL image this key shows, from the shared cache when possible.

        Returns None when the icon cannot be read; the caller then hands the
        raw path to the device, which reports the missing or broken file.
        """
        has_text = bool(self.text and self.text.strip())
        mtime = None
        if self.image_path:
            try:
                mtime = os.stat(self.image_path).st_mtime_ns
            except OSError:
                mtime = None

        if not has_text:
            if mtime is None:
                return None
            try:
                return _cached_image(('icon', self.image_path, mtime),
                                     lambda: _load_icon(self.image_path))
            except Exception:  # pylint: disable=broad-exception-caught
                logger.debug("Key %s: cannot load icon %r", self.key_number, self.image_path,
                             exc_info=True)
                return None

        icon_path = self.image_path if mtime is not None else ''
        params = (self.text, self.text_color, self.background_color, self.font_size,
                  self.bold, self.text_position)
        try:
            return _cached_image(
                ('text', icon_path, mtime) + params,
                lambda: render_key_image(
                    size=KEY_IMAGE_SIZE,
                    icon_path=icon_path,
                    text=self.text,
                    text_color=self.text_color,
                    background_color=self.background_color,
                    font_size=self.font_size,
                    bold=self.bold,
                    text_position=self.text_position,
                ))
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception(
                "Key %s: failed to render image (icon=%r, text=%r)",
                self.key_number, self.image_path, self.text
            )
            return None

    def prepare(self) -> None:
        """
        Render this key's image ahead of applying it.

        Called outside the device lock, so decoding and text rendering never
        hold up another thread's writes to the device.
        """
        self._render_image()

    def _show_image(self) -> None:
        image = self._render_image()
        if image is not None:
            self.device.set_key_pil_image(self.key_number, image)
        elif self.image_path:
            self.device.set_key_image(self.key_number, self.image_path)
        else:
            logger.warning(
                "Key %s has no image or text to display – skipping image set",
                self.key_number
            )

    # ------------------------------------------------------------------
    # Callback helpers
    # ------------------------------------------------------------------

    def _create_callback(self, actions_or_callback):
        """
        Create a callback function from actions or return the callback if it's
        already a function.

        :param actions_or_callback: Either a list of actions or a callback function
        :return: Callback function
        """
        if callable(actions_or_callback):
            return actions_or_callback

        if isinstance(actions_or_callback, list):
            def action_callback(device, key):
                if self.action_executor:
                    self.action_executor.execute_actions(actions_or_callback, device=device, key_number=self.key_number)
                else:
                    logger.warning("No action_executor available for key %s", self.key_number)
            return action_callback

        if isinstance(actions_or_callback, tuple):
            def action_callback(device, key):
                if self.action_executor:
                    self.action_executor.execute_actions([actions_or_callback], device=device, key_number=self.key_number)
                else:
                    logger.warning("No action_executor available for key %s", self.key_number)
            return action_callback

        return None

    # ------------------------------------------------------------------
    # Device configuration
    # ------------------------------------------------------------------

    def _configure(self):
        """Configure the key by setting its image and callbacks on the device."""
        self._show_image()

        if self._has_callbacks():
            self._register_callbacks()

    def _has_callbacks(self) -> bool:
        return any(cb is not None for cb in (
            self.on_press, self.on_release, self.on_double_press, self.on_long_press))

    def _register_callbacks(self):
        self.device.set_per_key_callback(
            self.logical_key,
            on_press=self.on_press,
            on_release=self.on_release,
            on_double_press=self.on_double_press,
            on_long_press=self.on_long_press
        )

    # ------------------------------------------------------------------
    # Update helpers
    # ------------------------------------------------------------------

    def update_image(self, new_image_path):
        """
        Update the key's image.

        :param new_image_path: Path to the new image file
        """
        self.image_path = new_image_path
        self._show_image()

    def update_text(
        self,
        text: str,
        text_color: str = None,
        background_color: str = None,
        font_size: int = None,
        bold: bool = None,
    ):
        """
        Update the key's text label and re-render the key image.

        :param text: New text label (use '' to remove)
        :param text_color: Optional new text colour
        :param background_color: Optional new background colour
        :param font_size: Optional new font size
        :param bold: Optional bold flag
        """
        self.text = text
        if text_color is not None:
            self.text_color = text_color
        if background_color is not None:
            self.background_color = background_color
        if font_size is not None:
            self.font_size = font_size
        if bold is not None:
            self.bold = bold

        self._show_image()

    def update_callbacks(self, on_press=None, on_release=None, on_double_press=None,
                         on_long_press=None):
        """
        Update the key's callbacks.

        :param on_press: New callback for key press
        :param on_release: New callback for key release
        :param on_double_press: New callback for key double-press
        :param on_long_press: New callback for key long-press
        """
        self.on_press_actions = on_press
        self.on_release_actions = on_release
        self.on_double_press_actions = on_double_press
        self.on_long_press_actions = on_long_press

        self.on_press = self._create_callback(on_press) if on_press else None
        self.on_release = self._create_callback(on_release) if on_release else None
        self.on_double_press = self._create_callback(on_double_press) if on_double_press else None
        self.on_long_press = self._create_callback(on_long_press) if on_long_press else None

        self._register_callbacks()

    def update_device(self, new_device):
        """
        Update the device reference for this key.
        Used when device is recreated (e.g., after unlock).

        :param new_device: New device instance
        """
        self.device = new_device
        if self._has_callbacks():
            self._register_callbacks()
