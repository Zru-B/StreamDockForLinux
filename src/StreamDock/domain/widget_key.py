import logging

from StreamDock.domain.key import Key

logger = logging.getLogger(__name__)


class WidgetKey(Key):
    """
    A key whose image comes from a running widget instead of an icon or text.

    The widget host owns the image; this key only shows the host's latest
    frame whenever its layout is applied. Key events the widget handles go to
    the widget first and then to the key's configured actions, and are
    registered even when the key has no actions of that kind.
    """

    def __init__(self, device, key_number, widget_host, key_name, **kwargs):
        super().__init__(device, key_number, image_path='', **kwargs)
        self.widget_host = widget_host
        self.widget_key_name = key_name
        for event in widget_host.events_for(key_name):
            attribute = f'on_{event}'
            setattr(self, attribute, self._with_widget_event(event, getattr(self, attribute)))

    def _with_widget_event(self, event, configured):
        def callback(device, key):
            self.widget_host.dispatch_event(self.widget_key_name, event)
            if configured is not None:
                configured(device, key)
        return callback

    def _configure(self):
        self.device.set_key_pil_image(self.key_number, self.widget_host.frame_for(self.widget_key_name))
        if self._has_callbacks():
            self._register_callbacks()
