from StreamDock.widgets.builtin._notifications import NotificationCounter, counter_options


class WhatsAppNotifications(NotificationCounter):
    id = 'whatsapp_notifications'
    name = 'WhatsApp Notifications'
    version = '1.0.0'
    description = ('Counts new WhatsApp messages from WhatsApp Web (in the browser) or a desktop client; '
                   'clears when you open the WhatsApp tab.')
    author = 'StreamDock'
    states = NotificationCounter.states
    options = counter_options('whatsapp, zapzap', 'web.whatsapp.com', 'whatsapp', '#128c4a')

    def draw_glyph(self, canvas, box, color, background, scale):
        left, top, right, bottom = box
        size = min(right - left, bottom - top)
        cx, cy = (left + right) / 2, (top + bottom) / 2
        r = size * 0.44
        canvas.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=3 * scale)
        canvas.polygon([(cx - r * 0.72, cy + r * 0.55), (cx - r * 0.95, cy + r * 1.02),
                        (cx - r * 0.35, cy + r * 0.86)], fill=color)
        # Handset: two rounded ends joined by a curve.
        canvas.arc((cx - r * 0.5, cy - r * 0.5, cx + r * 0.5, cy + r * 0.5), start=100, end=260,
                   fill=color, width=int(r * 0.22))
        for angle_x, angle_y in ((-0.1, -0.5), (-0.1, 0.5)):
            x, y = cx + angle_x * r, cy + angle_y * r
            canvas.ellipse((x - r * 0.13, y - r * 0.13, x + r * 0.13, y + r * 0.13), fill=color)
