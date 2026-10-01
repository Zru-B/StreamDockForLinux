from datetime import datetime, time, timedelta, tzinfo
from typing import Optional, Tuple

from streamdock_sdk import Option, Widget, draw
from StreamDock.widgets.builtin import _common


def parse_target(text: str, now: datetime) -> Optional[Tuple[datetime, bool]]:
    """
    When ``text`` falls, and whether it repeats every day.

    Accepts a date ('2026-12-24'), a date and time ('2026-12-24 18:00') or a
    time alone ('17:30'), which means its next occurrence, every day.
    """
    text = text.strip()
    if not text:
        return None
    try:
        moment = time.fromisoformat(text)
    except ValueError:
        pass
    else:
        target = now.replace(hour=moment.hour, minute=moment.minute, second=moment.second, microsecond=0)
        return (target if target > now else target + timedelta(days=1)), True
    try:
        target = datetime.fromisoformat(text)
    except ValueError:
        return None
    return target.replace(tzinfo=now.tzinfo) if target.tzinfo is None else target.astimezone(now.tzinfo), False


def remaining_text(seconds: float) -> Tuple[str, str]:
    """(what the key shows, a short badge) for ``seconds`` left."""
    seconds = max(int(seconds), 0)
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    if days >= 2:
        return f'{days} days', f'{days}d'
    if days or hours:
        return f'{days * 24 + hours}h {minutes:02d}m', f'{days * 24 + hours}h'
    return f'{minutes}:{secs:02d}', f'{minutes}m' if minutes else f'{secs}s'


class Countdown(Widget):
    id = 'countdown'
    name = 'Countdown'
    version = '1.0.0'
    description = ('Time left until a date, or until a time of day - the end of the workday, say. Days, '
                   'then hours and minutes, then minutes and seconds.')
    author = 'StreamDock'
    states = ('counting', 'soon', 'done', 'invalid')
    supports_badge = True
    options = [
        Option.string('target', default='17:00', label='Count down to',
                      description='A date "2026-12-24", a date and time "2026-12-24 18:00", or a time "17:30" '
                                  'for every day.'),
        Option.string('title', default='', label='Title', description='Shown above the time, e.g. "Release".'),
        Option.string('done_text', default='Now!', label='Text when the time comes'),
        Option.int('soon_minutes', default=60, minimum=0, maximum=10080, label='Soon from (minutes before)'),
        Option.string('timezone', default='', label='Time zone', description='e.g. Europe/London; empty: local.'),
        Option.color('color', default='#ffffff', label='Text colour'),
        Option.color('soon_color', default='#ffb300', label='Colour when soon'),
        Option.color('done_color', default='#66bb6a', label='Colour when done'),
        Option.color('background', default='#000000', label='Background'),
    ]

    def setup(self, ctx):
        self.zone: Optional[tzinfo] = _common.parse_zone(ctx.options['timezone'])
        self.shown: Optional[Tuple[str, str]] = None
        self.update(ctx)
        ctx.every(1, lambda: self.update(ctx), align=True)

    def on_show(self, ctx):
        self.update(ctx)

    def status(self, options) -> Tuple[str, str, Optional[str]]:
        """(state, text, badge) right now."""
        now = _common.now(self.zone)
        parsed = parse_target(options['target'], now)
        if parsed is None:
            return 'invalid', 'Bad date', None
        target = parsed[0]
        seconds = (target - now).total_seconds()
        if seconds <= 0:
            return 'done', options['done_text'], None
        text, badge = remaining_text(seconds)
        return ('soon' if seconds <= options['soon_minutes'] * 60 else 'counting'), text, badge

    def update(self, ctx):
        state, text, badge = self.status(ctx.options)
        ctx.set_state(state)
        ctx.set_badge(badge)
        if (state, text) != self.shown:
            self.shown = (state, text)
            ctx.request_render()

    def render(self, ctx):
        options = ctx.options
        state, text, _ = self.status(options)
        self.shown = (state, text)
        width, height = ctx.size
        image, canvas = draw.canvas(ctx.size, options['background'])
        color = {'soon': options['soon_color'], 'done': options['done_color']}.get(state, options['color'])
        if state == 'invalid':
            color = '#e57373'
        top = 8
        if options['title']:
            # A fixed size, so titles look alike across keys; only a long one shrinks.
            title_font = draw.fit_font(canvas, options['title'], width - 12, 26, start=18, bold=False)
            draw.centered_text(canvas, (6, 6, width - 6, 34), options['title'], color=options['color'],
                               text_font=title_font)
            top = 38
        draw.centered_text(canvas, (6, top, width - 6, height - 10), text.replace(' ', '\n', 1)
                           if ' ' in text and state not in ('done', 'invalid') else text, color=color)
        return image
