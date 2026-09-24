from StreamDock.widgets.builtin._notifications import NotificationCounter, counter_options


class SlackNotifications(NotificationCounter):
    id = 'slack_notifications'
    name = 'Slack Notifications'
    version = '1.1.0'
    description = ('Counts new Slack messages from its desktop notifications; clears when you open Slack. '
                   'Put it on your own Slack icon to get a count badge in the corner.')
    author = 'StreamDock'
    states = NotificationCounter.states
    options = counter_options('slack', 'app.slack.com', 'slack', '#4a154b')

    def draw_glyph(self, canvas, box, color, background, scale):
        left, top, right, bottom = box
        width, height = right - left, bottom - top
        bubble = (left + width * 0.02, top + height * 0.05, right - width * 0.02, top + height * 0.78)
        canvas.rounded_rectangle(bubble, radius=height * 0.22, outline=color, width=3 * scale)
        tail_x = left + width * 0.28
        canvas.polygon([(tail_x, bubble[3] - scale), (tail_x + width * 0.18, bubble[3] - scale),
                        (tail_x, bottom)], fill=color)
        for i in range(3):
            r = height * 0.06
            x = left + width * (0.28 + i * 0.22)
            y = (bubble[1] + bubble[3]) / 2
            canvas.ellipse((x - r, y - r, x + r, y + r), fill=color)
