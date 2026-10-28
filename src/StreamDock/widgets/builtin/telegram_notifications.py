from StreamDock.widgets.builtin._notifications import NotificationCounter, counter_options


class TelegramNotifications(NotificationCounter):
    id = 'telegram_notifications'
    name = 'Telegram Notifications'
    version = '1.0.0'
    description = ('Counts new Telegram messages from Telegram Desktop or Telegram Web; '
                   'clears when you open Telegram.')
    author = 'StreamDock'
    states = NotificationCounter.states
    options = counter_options('telegram', 'web.telegram.org', 'telegram', '#1f7fb8')

    def draw_glyph(self, canvas, box, color, background, scale):
        left, top, right, bottom = box
        size = min(right - left, bottom - top)
        cx, cy = (left + right) / 2, (top + bottom) / 2
        r = size * 0.46
        # A paper plane.
        nose = (cx + r, cy - r * 0.75)
        canvas.polygon([(cx - r, cy - r * 0.05), nose, (cx + r * 0.45, cy + r * 0.85)], fill=color)
        canvas.polygon([(cx - r * 0.2, cy + r * 0.25), nose, (cx - r * 0.05, cy + r * 0.8)], fill=background)
        canvas.line((cx - r * 0.2, cy + r * 0.25, nose[0], nose[1]), fill=color, width=2 * scale)
