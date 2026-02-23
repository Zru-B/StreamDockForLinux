import logging
import os
import tempfile

from StreamDock.image_helpers.pil_helper import render_key_image

logger = logging.getLogger(__name__)


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

        # Convert actions to callback functions
        self.on_press = self._create_callback(on_press) if on_press else None
        self.on_release = self._create_callback(on_release) if on_release else None
        self.on_double_press = self._create_callback(on_double_press) if on_double_press else None

        # Get the logical key number for callback registration
        self.logical_key = self.KEY_MAPPING.get(key_number, key_number)

        # Track temp file created by _render_image so we can clean it up
        self._rendered_temp_path: str = ''

    # ------------------------------------------------------------------
    # Image rendering
    # ------------------------------------------------------------------

    def _render_image(self) -> str:
        """
        Render the key image and return the file path that should be sent to
        the device.

        Returns the original ``image_path`` when no text is involved and the
        file already exists, otherwise generates a temporary JPEG file with
        the correct pixel content and returns its path.

        The caller is responsible for honouring ``_rendered_temp_path`` for
        cleanup (set on this instance after the call).

        :return: Absolute path to the image file to hand to the device.
        """
        has_icon = bool(self.image_path and os.path.exists(self.image_path))
        has_text = bool(self.text and self.text.strip())

        # Icon-only, icon already on disk → nothing to do, send the path directly.
        if has_icon and not has_text:
            return self.image_path


        try:
            pil_image = render_key_image(
                size=(112, 112),
                icon_path=self.image_path if has_icon else '',
                text=self.text,
                text_color=self.text_color,
                background_color=self.background_color,
                font_size=self.font_size,
                bold=self.bold,
                text_position=self.text_position,
            )
        except Exception:
            logger.exception(
                "Key %s: failed to render image (icon=%r, text=%r)",
                self.key_number, self.image_path, self.text
            )
            return self.image_path  # Fall back to raw icon path (may be empty)

        # Save to a temp file so the device transport can read it by path
        try:
            fd, tmp_path = tempfile.mkstemp(suffix='.jpg', prefix='sdkey_')
            os.close(fd)
            pil_image.save(tmp_path, format='JPEG', quality=95)
            # Clean up any previous temp file for this key
            self._cleanup_temp()
            self._rendered_temp_path = tmp_path
            return tmp_path
        except Exception:
            logger.exception("Key %s: failed to save rendered image to temp file", self.key_number)
            return self.image_path

    def _cleanup_temp(self) -> None:
        """Remove any previously created temporary rendered image file."""
        if self._rendered_temp_path and os.path.exists(self._rendered_temp_path):
            try:
                os.remove(self._rendered_temp_path)
            except Exception:
                pass
            self._rendered_temp_path = ''

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
        rendered_path = self._render_image()

        if rendered_path:
            self.device.set_key_image(self.key_number, rendered_path)
        else:
            logger.warning(
                "Key %s has no image or text to display – skipping image set",
                self.key_number
            )

        if self.on_press is not None or self.on_release is not None or self.on_double_press is not None:
            self.device.set_per_key_callback(
                self.logical_key,
                on_press=self.on_press,
                on_release=self.on_release,
                on_double_press=self.on_double_press
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
        rendered_path = self._render_image()
        if rendered_path:
            self.device.set_key_image(self.key_number, rendered_path)

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

        rendered_path = self._render_image()
        if rendered_path:
            self.device.set_key_image(self.key_number, rendered_path)

    def update_callbacks(self, on_press=None, on_release=None, on_double_press=None):
        """
        Update the key's callbacks.

        :param on_press: New callback for key press
        :param on_release: New callback for key release
        :param on_double_press: New callback for key double-press
        """
        self.on_press_actions = on_press
        self.on_release_actions = on_release
        self.on_double_press_actions = on_double_press

        self.on_press = self._create_callback(on_press) if on_press else None
        self.on_release = self._create_callback(on_release) if on_release else None
        self.on_double_press = self._create_callback(on_double_press) if on_double_press else None

        self.device.set_per_key_callback(
            self.logical_key,
            on_press=self.on_press,
            on_release=self.on_release,
            on_double_press=self.on_double_press
        )

    def update_device(self, new_device):
        """
        Update the device reference for this key.
        Used when device is recreated (e.g., after unlock).

        :param new_device: New device instance
        """
        self.device = new_device
        if self.on_press is not None or self.on_release is not None or self.on_double_press is not None:
            self.device.set_per_key_callback(
                self.logical_key,
                on_press=self.on_press,
                on_release=self.on_release,
                on_double_press=self.on_double_press
            )

    def __del__(self):
        """Clean up any temporary rendered image files."""
        try:
            self._cleanup_temp()
        except Exception:
            pass
