from .key import Key


class Layout:
    """
    Represents a layout configuration for the StreamDock device.

    A Layout contains 1-15 Keys and can be applied to the device all at once.
    This makes it easy to switch between different key configurations.
    """

    def __init__(self, device, keys, clear_keys=None, clear_all=False):
        """
        Initialize a Layout with a device and a collection of Keys.

        :param device: The StreamDock device instance
        :param keys: List of Key instances (1-15 keys)
        :param clear_keys: Optional list of key numbers to clear (set to empty)
        :param clear_all: If True, clear all icons before applying this layout (default: False)
        """
        self.device = device

        # Validate that we have between 1 and 15 keys (or clear operations)
        if not isinstance(keys, list):
            raise TypeError("keys must be a list of Key instances")

        self.keys = keys
        self.clear_keys = clear_keys or []
        self.clear_all = clear_all

        # Total operations (keys + clears) must be at least 1 and at most 15
        total_operations = len(keys) + len(self.clear_keys)
        if total_operations < 1 or total_operations > 15:
            raise ValueError("Layout must contain between 1 and 15 total operations (keys + clears)")

    def apply(self):
        """
        Apply this layout to the device.

        This will configure all keys in the layout and refresh the device display.
        If clear_all is True, all icons and callbacks will be cleared before applying the layout.
        """
        # Clear all icons and callbacks if requested
        if self.clear_all:
            self.device.clear_all_icons()
            self.device.clear_all_callbacks()

        # Clear specified keys (both icons and callbacks)
        for key_number in self.clear_keys:
            self.device.cleaerIcon(key_number)
            # Get the logical key number for callback clearing
            logical_key = key_number  # Will be mapped in clear_key_callback if needed
            from .key import Key
            logical_key = Key.KEY_MAPPING.get(key_number, key_number)
            self.device.clear_key_callback(logical_key)

        # Configure each key in the layout
        for key in self.keys:
            key._configure()

        # Refresh the device display
        self.device.refresh()

    def get_key(self, key_number):
        """
        Get a Key instance by its key number.

        :param key_number: Physical key number (1-15)
        :return: Key instance or None if not found
        """
        for key in self.keys:
            if key.key_number == key_number:
                return key
        return None

    def update_key(self, key_number, new_image=None, new_on_press=None, new_on_release=None):
        """
        Update a specific key in the layout.

        :param key_number: Physical key number (1-15)
        :param new_image: Optional new image path
        :param new_on_press: Optional new press callback
        :param new_on_release: Optional new release callback
        """
        key = self.get_key(key_number)
        if key is None:
            raise ValueError(f"Key {key_number} not found in this layout")

        if new_image is not None:
            key.update_image(new_image)

        if new_on_press is not None or new_on_release is not None:
            key.update_callbacks(new_on_press, new_on_release)

        self.device.refresh()

    def update_device(self, new_device):
        """
        Update the device reference for all keys in this layout.
        Used when device is recreated (e.g., after unlock).

        :param new_device: New device instance
        """
        self.device = new_device
        # Update device reference for all keys
        for key in self.keys:
            key.update_device(new_device)
