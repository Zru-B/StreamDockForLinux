from .Actions import execute_actions


class Key:
    """
    Represents a configurable key on the StreamDock device.

    Creating a Key instance automatically configures the key's image and callbacks
    on the provided device.
    """

    # Mapping from hardware key numbers to logical key numbers
    KEY_MAPPING = {
        1: 11, 2: 12, 3: 13, 4: 14,
        5: 15, 6: 6, 7: 7, 8: 8,
        9: 9, 10: 10, 11: 1, 12: 2,
        13: 3, 14: 4, 15: 5
    }

    def __init__(self, device, key_number, image_path, on_press=None, on_release=None, on_double_press=None):
        """
        Initialize and configure a key on the StreamDock device.

        :param device: The StreamDock device instance
        :param key_number: Physical key number (1-15)
        :param image_path: Path to the image file for this key
        :param on_press: Optional callback - can be:
                        - A function: callback(device, key)
                        - A list of actions: [(ActionType, parameter), ...]
        :param on_release: Optional callback - can be:
                          - A function: callback(device, key)
                          - A list of actions: [(ActionType, parameter), ...]
        :param on_double_press: Optional callback - can be:
                               - A function: callback(device, key)
                               - A list of actions: [(ActionType, parameter), ...]
        """
        self.device = device
        self.key_number = key_number
        self.image_path = image_path

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

    def _create_callback(self, actions_or_callback):
        """
        Create a callback function from actions or return the callback if it's already a function.

        :param actions_or_callback: Either a list of actions or a callback function
        :return: Callback function
        """
        # If it's already a function, return it
        if callable(actions_or_callback):
            return actions_or_callback

        # If it's a list of actions, create a callback that executes them
        if isinstance(actions_or_callback, list):
            def action_callback(device, key):
                execute_actions(actions_or_callback, device=device, key_number=self.key_number)

            return action_callback

        # If it's a single action tuple, wrap it in a list
        if isinstance(actions_or_callback, tuple):
            def action_callback(device, key):
                execute_actions([actions_or_callback], device=device, key_number=self.key_number)

            return action_callback

        return None

    def _configure(self):
        """Configure the key by setting its image and callbacks on the device."""
        # Set the key image
        self.device.set_key_image(self.key_number, self.image_path)

        # Register callbacks if provided
        if self.on_press is not None or self.on_release is not None or self.on_double_press is not None:
            self.device.set_per_key_callback(
                self.logical_key,
                on_press=self.on_press,
                on_release=self.on_release,
                on_double_press=self.on_double_press
            )

    def update_image(self, new_image_path):
        """
        Update the key's image.

        :param new_image_path: Path to the new image file
        """
        self.image_path = new_image_path
        self.device.set_key_image(self.key_number, self.image_path)

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

        # Convert actions to callback functions
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
        # Re-register callbacks on the new device
        if self.on_press is not None or self.on_release is not None or self.on_double_press is not None:
            self.device.set_per_key_callback(
                self.logical_key,
                on_press=self.on_press,
                on_release=self.on_release,
                on_double_press=self.on_double_press
            )
