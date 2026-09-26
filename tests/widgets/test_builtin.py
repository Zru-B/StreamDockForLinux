"""Every built-in widget draws a key-sized frame with its defaults and variants."""

import os
import sys
import threading
import time
from datetime import datetime

import pytest
from PIL import Image

from streamdock_sdk.options import resolve_options
from streamdock_sdk.scheduler import WidgetDriver
from StreamDock.widgets.builtin import (
    _common, _notifications, _pulse, now_playing, system_stats, vpn_connected, weather)
from StreamDock.infrastructure import mpris as _mpris
from StreamDock.widgets.registry import load_builtin_specs

SPECS = load_builtin_specs()

VARIANTS = {
    'digital_clock': [{}, {'format': '12h', 'show_seconds': True}, {'timezone': 'Asia/Tokyo'}],
    'analog_clock': [{}, {'show_seconds': True}],
    'date': [{'format': name} for name in ('weekday_day_month', 'day_month', 'iso', 'numeric')],
    'system_stats': [{'metric': name} for name in ('cpu', 'ram', 'both')],
    'mic_muted': [{}, {'show_caption': False}],
    'sound_muted': [{}],
    'volume': [{}, {'max_volume': 150}],
    'volume_column': [{'button': name} for name in ('up', 'mute', 'down')] + [{'show_level_bar': False}],
    'vpn_connected': [{}, {'source': 'interfaces'}],
    'media_playing': [{}, {'player': 'spotify'}],
    'now_playing': [{}, {'show_art': False}],
    'weather': [{}, {'units': 'fahrenheit', 'location': '32.08,34.78'}],
    'slack_notifications': [{}, {'app_name': 'Signal'}],
    'whatsapp_notifications': [{}],
    'telegram_notifications': [{}],
}

PLAYING = _mpris.PlayerStatus('org.mpris.MediaPlayer2.spotify', 'playing', 'A Very Long Song Title Indeed',
                              ['Some Artist'])


@pytest.fixture(autouse=True)
def frozen_world(monkeypatch):
    monkeypatch.setattr(_common, 'now', lambda zone=None: datetime(2026, 9, 23, 16, 5, 7, tzinfo=zone))
    monkeypatch.setattr(_pulse, 'read_muted', lambda kind: True)
    monkeypatch.setattr(_pulse, 'read_level', lambda kind: _pulse.AudioLevel(40, False))
    monkeypatch.setattr(_pulse.HUB, 'subscribe', lambda callback: None)
    monkeypatch.setattr(_pulse.HUB, 'unsubscribe', lambda callback: None)
    monkeypatch.setattr(vpn_connected, 'networkmanager_vpn', lambda: False)
    monkeypatch.setattr(vpn_connected, 'interface_up', lambda patterns: False)
    monkeypatch.setattr(system_stats, 'read_cpu_times', lambda: (50, 100))
    monkeypatch.setattr(system_stats, 'read_memory_percent', lambda: 42.0)
    monkeypatch.setattr(system_stats.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(_mpris, 'current', lambda player='', with_metadata=True: PLAYING)
    monkeypatch.setattr(weather, 'locate', lambda location, timeout=0: (51.5, -0.1))
    monkeypatch.setattr(weather, 'fetch', lambda position, units, timeout=0: weather.Reading(21.4, 'rain'))
    monkeypatch.setattr(_notifications.HUB, 'subscribe', lambda callback: None)
    monkeypatch.setattr(_notifications.HUB, 'unsubscribe', lambda callback: None)


def test_every_builtin_has_variants_listed():
    assert set(SPECS) == set(VARIANTS)


@pytest.mark.parametrize('widget_id, options', [
    (widget_id, options) for widget_id, variants in VARIANTS.items() for options in variants
])
def test_renders_a_key_sized_frame(widget_id, options):
    spec = SPECS[widget_id]
    resolved, warnings = resolve_options(spec.options, options)
    assert warnings == []
    frame = WidgetDriver(spec.widget_cls, resolved).render_once()
    assert frame.size == (112, 112)
    assert frame.mode == 'RGB'


def test_clock_ticks_every_minute_on_the_minute():
    spec = SPECS['digital_clock']
    driver = WidgetDriver(spec.widget_cls, resolve_options(spec.options, {})[0])
    driver.widget = spec.widget_cls()
    driver.widget.setup(driver.ctx)
    assert [(timer.interval, timer.align) for timer in driver._timers] == [(60, True)]


def driver_for(widget_id, **options):
    spec = SPECS[widget_id]
    return WidgetDriver(spec.widget_cls, resolve_options(spec.options, options)[0])


def test_cpu_percentage_is_a_difference_of_two_readings(monkeypatch):
    readings = iter([(100, 1000), (150, 1100)])
    monkeypatch.setattr(system_stats, 'read_cpu_times', lambda: next(readings))
    driver = driver_for('system_stats', metric='cpu')
    driver.render_once()
    assert driver.widget.cpu == pytest.approx(50.0)
    assert (driver.state, driver.badge) == ('normal', '50%')


def test_states_report_what_the_widgets_see():
    # These are the names users map images to in state_icons.
    cases = {'mic_muted': 'muted', 'vpn_connected': 'disconnected', 'media_playing': 'playing', 'weather': 'rain',
             'now_playing': 'playing', 'slack_notifications': 'none', 'system_stats': 'normal',
             'whatsapp_notifications': 'none', 'telegram_notifications': 'none'}
    for widget_id, state in cases.items():
        driver = driver_for(widget_id)
        driver.render_once()
        assert driver.state == state, widget_id
        assert state in SPECS[widget_id].states


def started(widget_id, **options):
    driver = driver_for(widget_id, **options)
    driver.widget = SPECS[widget_id].widget_cls()
    driver.widget.setup(driver.ctx)
    return driver, driver.widget


def notify(app, sender=':1.7', summary='Alice', body='hi', replaces=0, entry=''):
    return _notifications.NotificationEvent('notify', sender, app, summary, body, entry, replaces)


class TestNotificationCounters:
    def test_counts_its_app_and_press_clears(self):
        driver, widget = started('slack_notifications')
        for event in (notify('Slack'), notify('Slack'), notify('Firefox'), notify('Slack', replaces=12)):
            widget.on_notification(driver.ctx, event)
        # A notification replacing an earlier one was already counted.
        assert (driver.state, driver.badge) == ('unread', '2')
        widget.on_press(driver.ctx)
        assert (driver.state, driver.badge) == ('none', None)

    def test_browser_notifications_count_by_site(self):
        driver, widget = started('whatsapp_notifications')
        widget.on_notification(driver.ctx, notify('Google Chrome', body='web.whatsapp.com\n\nhello'))
        widget.on_notification(driver.ctx, notify('Google Chrome', body='github.com\n\nPR merged'))
        widget.on_notification(driver.ctx, notify('ZapZap'))
        assert driver.badge == '2'

    def test_desktop_entry_identifies_the_app(self):
        driver, widget = started('telegram_notifications')
        widget.on_notification(driver.ctx, notify('', entry='org.telegram.desktop'))
        assert driver.badge == '1'

    def test_app_withdrawing_its_notifications_uncounts_them(self):
        # Chat apps close their notifications once the message is read.
        driver, widget = started('slack_notifications')
        widget.on_notification(driver.ctx, notify('Slack', sender=':1.7'))
        widget.on_notification(driver.ctx, notify('Slack', sender=':1.7'))
        widget.on_notification(driver.ctx, _notifications.NotificationEvent('close', ':1.99'))
        assert driver.badge == '2'
        widget.on_notification(driver.ctx, _notifications.NotificationEvent('close', ':1.7'))
        assert driver.badge == '1'
        for _ in range(3):
            widget.on_notification(driver.ctx, _notifications.NotificationEvent('close', ':1.7'))
        assert (driver.state, driver.badge) == ('none', None)

    def test_following_the_app_can_be_turned_off(self):
        driver, widget = started('slack_notifications', follow_app=False)
        widget.on_notification(driver.ctx, notify('Slack'))
        widget.on_notification(driver.ctx, _notifications.NotificationEvent('close', ':1.7'))
        assert driver.badge == '1'

    @pytest.mark.parametrize('widget_id, app, title', [
        ('slack_notifications', 'Slack', 'general - Acme - Slack'),
        ('whatsapp_notifications', 'firefox', '(3) WhatsApp — Mozilla Firefox'),
        ('telegram_notifications', 'TelegramDesktop', 'Telegram'),
    ])
    def test_focusing_the_app_clears(self, widget_id, app, title):
        driver, widget = started(widget_id)
        widget.on_notification(driver.ctx, notify(app, body='web.whatsapp.com') if 'whatsapp' in widget_id
                               else notify(app))
        assert driver.badge == '1'
        widget.on_window_focus(driver.ctx, 'konsole', 'bash')
        assert driver.badge == '1'
        widget.on_window_focus(driver.ctx, app, title)
        assert driver.badge is None

    def test_focus_clearing_can_be_turned_off(self):
        driver, widget = started('slack_notifications', clear_on_focus=False)
        widget.on_notification(driver.ctx, notify('Slack'))
        widget.on_window_focus(driver.ctx, 'Slack', 'Slack')
        assert driver.badge == '1'

    def test_lost_bus_shows_unavailable(self):
        driver, widget = started('slack_notifications')
        widget.on_notification(driver.ctx, None)
        assert driver.state == 'unavailable'

    def test_counters_keep_listening_while_hidden(self):
        for widget_id in ('slack_notifications', 'whatsapp_notifications', 'telegram_notifications'):
            assert SPECS[widget_id].run_while_hidden and SPECS[widget_id].window_focus


@pytest.mark.parametrize('line, expected', [
    ('{"sender":":1.5","member":"Notify","payload":{"data":["Slack",0,"","Alice","hi",[],'
     '{"desktop-entry":{"type":"s","data":"slack"}},-1]}}', ('notify', ':1.5', 'Slack', 'slack', 0)),
    ('{"sender":":1.5","member":"Notify","payload":{"data":["Slack",42,"","t","b",[],{},-1]}}',
     ('notify', ':1.5', 'Slack', '', 42)),
    ('{"sender":":1.5","member":"CloseNotification","payload":{"data":[7]}}', ('close', ':1.5', '', '', 0)),
    ('{"member":"GetServerInformation","payload":{"data":[]}}', None),
    ('not json', None),
    ('{"sender":":1.5","member":"Notify","payload":{"data":["Slack","x","","t","b",[],{},-1]}}', None),
    ('{"sender":":1.5","member":"Notify","payload":{"data":["Slack",[1],"","t","b",[],{},-1]}}', None),
])
def test_monitor_lines_are_parsed(line, expected):
    event = _notifications.parse_event(line)
    assert (None if event is None else
            (event.kind, event.sender, event.app, event.desktop_entry, event.replaces_id)) == expected


@pytest.mark.parametrize('code, is_day, state', [
    (0, True, 'clear'), (0, False, 'clear_night'), (2, True, 'partly_cloudy'), (3, True, 'cloudy'),
    (45, True, 'fog'), (53, True, 'rain'), (81, True, 'rain'), (73, True, 'snow'), (86, True, 'snow'),
    (95, True, 'storm'), (None, True, 'unknown'),
])
def test_weather_codes_map_to_states(code, is_day, state):
    assert weather.condition(code, is_day) == state
    assert state in weather.STATES


def test_coordinates_skip_geocoding(monkeypatch):
    monkeypatch.undo()
    monkeypatch.setattr(weather, '_get_json', lambda *args: pytest.fail('no lookup expected'))
    assert weather.locate(' 32.08 , 34.78 ') == (32.08, 34.78)


def test_mpris_prefers_the_playing_player(monkeypatch):
    replies = {
        'ListNames': [['org.mpris.MediaPlayer2.firefox', 'org.mpris.MediaPlayer2.spotify', ':1.5']],
        'org.mpris.MediaPlayer2.firefox': [{'PlaybackStatus': {'type': 's', 'data': 'Paused'}}],
        'org.mpris.MediaPlayer2.spotify': [{
            'PlaybackStatus': {'type': 's', 'data': 'Playing'},
            'Metadata': {'type': 'a{sv}', 'data': {
                'xesam:title': {'type': 's', 'data': 'Song'},
                'xesam:artist': {'type': 'as', 'data': ['A', 'B']},
                'mpris:artUrl': {'type': 's', 'data': 'file:///tmp/art.png'},
            }},
        }],
    }
    calls = []

    def busctl(*args):
        calls.append(args)
        return replies.get(args[-1] if args[-1] == 'ListNames' else args[1])

    monkeypatch.undo()
    monkeypatch.setattr(_mpris, '_busctl', busctl)
    _mpris.invalidate()
    status = _mpris.current()
    assert (status.player, status.status, status.title, status.artist) == \
        ('org.mpris.MediaPlayer2.spotify', 'playing', 'Song', 'A, B')
    assert _mpris.current('firefox', with_metadata=False).status == 'paused'
    assert _mpris.current('vlc').status == 'none'
    # Two widgets polling together share one ListNames and one GetAll per player.
    assert len(calls) == 3
    assert all(args[3:5] == ('org.freedesktop.DBus.Properties', 'GetAll') for args in calls[1:])
    _mpris.invalidate()


def test_art_is_scaled_and_only_successes_are_cached(tmp_path, monkeypatch):
    # A missing file used to be cached as "no art" for the rest of the session.
    monkeypatch.undo()
    monkeypatch.setattr(now_playing, '_art_cache', type(now_playing._art_cache)())
    path = tmp_path / 'art.png'
    url = path.as_uri()
    assert now_playing.fetch_art(url) is None
    Image.new('RGB', (1000, 800), 'red').save(path)
    art = now_playing.fetch_art(url)
    assert art is not None and max(art.size) <= max(now_playing.ART_SIZE)
    path.unlink()
    assert now_playing.fetch_art(url) is art


def test_art_is_read_only_from_plain_files(tmp_path, monkeypatch):
    monkeypatch.undo()
    fifo = tmp_path / 'fifo'
    os.mkfifo(fifo)
    assert now_playing.fetch_art(fifo.as_uri()) is None
    (tmp_path / 'art.bmp').write_bytes(b'BM' + b'\0' * 100)
    assert now_playing.fetch_art((tmp_path / 'art.bmp').as_uri()) is None


def test_vpn_skips_nmcli_when_an_interface_is_up(monkeypatch):
    monkeypatch.setattr(vpn_connected, 'interface_up', lambda patterns: True)
    monkeypatch.setattr(vpn_connected, 'networkmanager_vpn', lambda: pytest.fail('nmcli not needed'))
    assert vpn_connected.VpnConnected.detect({'source': 'auto', 'interfaces': 'tun*'}) is True


def test_odd_weather_data_does_not_fail_setup(monkeypatch):
    # A reply of an unexpected shape raised TypeError out of setup and killed the widget.
    monkeypatch.setattr(weather, 'fetch', lambda position, units, timeout=0: None + 1)
    driver, widget = started('weather')
    assert widget.reading is None and widget.failed


def test_stats_redraw_only_when_the_shown_numbers_change(monkeypatch):
    monkeypatch.setattr(system_stats, 'read_memory_percent', lambda: 42.2)
    driver, widget = started('system_stats', metric='ram')
    renders = []
    monkeypatch.setattr(driver, 'request_render', lambda: renders.append(1))
    widget.sample(driver.ctx)
    monkeypatch.setattr(system_stats, 'read_memory_percent', lambda: 42.4)
    widget.sample(driver.ctx)
    assert renders == []
    monkeypatch.setattr(system_stats, 'read_memory_percent', lambda: 43.0)
    widget.sample(driver.ctx)
    assert renders == [1]


def test_interface_detection_uses_the_up_flag(tmp_path, monkeypatch):
    monkeypatch.undo()
    for name, flags in (('tun0', '0x1091'), ('wg0', '0x1090'), ('eth0', '0x1003')):
        (tmp_path / name).mkdir()
        (tmp_path / name / 'flags').write_text(flags)
    assert vpn_connected.interface_up('tun*', str(tmp_path)) is True
    assert vpn_connected.interface_up('wg*', str(tmp_path)) is False
    assert vpn_connected.interface_up('ppp*', str(tmp_path)) is False


def test_pactl_mute_output_is_parsed(monkeypatch):
    class Result:
        returncode = 0
        stdout = 'Mute: yes\n'

    monkeypatch.undo()
    monkeypatch.setattr(_pulse.subprocess, 'run', lambda *args, **kwargs: Result())
    assert _pulse.read_muted('source') is True
    Result.stdout = 'Mute: no\n'
    assert _pulse.read_muted('sink') is False
    Result.returncode = 1
    assert _pulse.read_muted('sink') is None


class TestProcessHub:
    """The shared monitor processes behind the notification and mute widgets."""

    def hub(self, tmp_path, body):
        script = tmp_path / 'monitor.py'
        script.write_text('import sys, time\n' + body)
        hub = _common.ProcessHub([sys.executable, str(script)], 'test-hub')
        hub.RESTART_DELAY = 0.05
        return hub

    def wait(self, predicate, timeout=5.0):
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            time.sleep(0.01)
        return predicate()

    def test_a_bad_line_does_not_kill_the_reader(self, tmp_path):
        # An exception from parsing one line used to end the thread and every counter with it.
        hub = self.hub(tmp_path, "print('bad', flush=True); print('good', flush=True); time.sleep(30)")
        hub._parse = lambda line: 1 / 0 if line.startswith('bad') else line.strip()
        got = []
        hub.subscribe(got.append)
        try:
            assert self.wait(lambda: 'good' in got)
        finally:
            hub.unsubscribe(got.append)

    def test_a_stopped_generation_never_publishes_to_the_next(self, tmp_path):
        hub = self.hub(tmp_path, "time.sleep(30)")
        first = []
        hub.subscribe(first.append)
        old = hub._stopping
        hub.unsubscribe(first.append)
        second = []
        hub.subscribe(second.append)
        try:
            hub._publish(old, 'stale')
            assert second == []
        finally:
            hub.unsubscribe(second.append)

    def test_a_process_started_after_stop_is_killed(self, tmp_path, monkeypatch):
        # unsubscribe() during Popen saw no process to stop, and the monitor ran on unowned.
        hub = self.hub(tmp_path, "time.sleep(30)")
        spawned = []
        real_popen = _common.subprocess.Popen

        def slow_popen(*args, **kwargs):
            hub.unsubscribe(callback)
            process = real_popen(*args, **kwargs)
            spawned.append(process)
            return process

        monkeypatch.setattr(_common.subprocess, 'Popen', slow_popen)
        callback = lambda event: None  # noqa: E731
        hub.subscribe(callback)
        assert self.wait(lambda: spawned and spawned[0].poll() is not None)
        assert hub._process is None


def test_mute_events_are_coalesced(monkeypatch):
    reads = []
    monkeypatch.setattr(_pulse, 'read_muted', lambda kind: reads.append(kind) or False)
    subscribed = []
    monkeypatch.setattr(_pulse.HUB, 'subscribe', subscribed.append)
    driver, widget = started('mic_muted')
    reads.clear()
    widget.on_show(driver.ctx)
    listener = subscribed[-1]
    done = threading.Event()
    monkeypatch.setattr(driver.ctx, 'call_soon', lambda fn: done.set())
    for _ in range(20):
        listener("Event 'change' on source #5")
    assert done.wait(2)
    time.sleep(0.2)
    # One read from on_show's refresh at most, plus one for the whole burst.
    assert reads.count('source') <= 2
    widget.stop_watching()


def test_pactl_volume_output_is_parsed(monkeypatch):
    class Result:
        returncode = 0
        stdout = ('Volume: front-left: 26214 /  40% / -23.88 dB,   front-right: 32768 /  50% / -18.06 dB\n'
                  '        balance 0.10\n')

    monkeypatch.undo()
    monkeypatch.setattr(_pulse.subprocess, 'run', lambda *args, **kwargs: Result())
    assert _pulse.read_volume('sink') == 45
    Result.returncode = 1
    assert _pulse.read_volume('sink') is None


class TestStepVolume:
    @pytest.fixture
    def pactl(self, monkeypatch):
        monkeypatch.undo()
        calls = []
        monkeypatch.setattr(_pulse.subprocess, 'run', lambda command, **kwargs: calls.append(command))
        monkeypatch.setattr(_pulse, 'read_level', lambda kind: _pulse.AudioLevel(None, None))
        return calls

    def volume_is(self, monkeypatch, percent):
        monkeypatch.setattr(_pulse, 'read_volume', lambda kind: percent)

    def test_steps_are_relative_so_the_balance_stays(self, pactl, monkeypatch):
        self.volume_is(monkeypatch, 40)
        _pulse.step_volume('sink', -5, unmute=False)
        assert pactl == [['pactl', 'set-sink-volume', '--', '@DEFAULT_SINK@', '-5%']]

    def test_raising_stops_at_the_maximum(self, pactl, monkeypatch):
        self.volume_is(monkeypatch, 97)
        _pulse.step_volume('sink', 5, maximum=100, unmute=False)
        assert pactl == [['pactl', 'set-sink-volume', '--', '@DEFAULT_SINK@', '100%']]
        pactl.clear()
        self.volume_is(monkeypatch, 100)
        _pulse.step_volume('sink', 5, maximum=100, unmute=False)
        assert pactl == []

    def test_raising_unmutes(self, pactl, monkeypatch):
        self.volume_is(monkeypatch, 40)
        _pulse.step_volume('sink', 5, unmute=True)
        assert pactl[-1] == ['pactl', 'set-sink-mute', '@DEFAULT_SINK@', '0']
        pactl.clear()
        _pulse.step_volume('sink', -5, unmute=True)
        assert len(pactl) == 1


class TestVolumeColumn:
    @pytest.mark.parametrize('button, step', [('up', 5), ('down', -5)])
    def test_up_and_down_step_the_volume(self, monkeypatch, button, step):
        steps = []
        monkeypatch.setattr(_pulse, 'step_volume',
                            lambda kind, change, maximum, unmute: steps.append((kind, change, maximum)))
        driver, widget = started('volume_column', button=button)
        monkeypatch.setattr(driver, 'run_in_background', lambda fn, then=None, skip=False: fn())
        widget.on_press(driver.ctx)
        assert steps == [('sink', step, 100)]

    def test_middle_button_toggles_mute(self, monkeypatch):
        toggled = []
        monkeypatch.setattr(_pulse, 'toggle_muted', toggled.append)
        driver, widget = started('volume_column', button='mute')
        monkeypatch.setattr(driver, 'run_in_background', lambda fn, then=None, skip=False: then(fn()))
        widget.on_press(driver.ctx)
        assert toggled == ['sink']

    def test_reports_mute_state_and_volume_badge(self, monkeypatch):
        driver, widget = started('volume_column')
        assert (driver.state, driver.badge) == ('unmuted', '40%')
        widget.update(driver.ctx, _pulse.AudioLevel(55, True))
        assert (driver.state, driver.badge) == ('muted', '55%')


class TestVolume:
    def test_press_raises_double_press_lowers(self, monkeypatch):
        steps = []
        monkeypatch.setattr(_pulse, 'step_volume',
                            lambda kind, change, maximum, unmute: steps.append((kind, change, maximum, unmute)))
        driver, widget = started('volume', step=10, max_volume=120)
        monkeypatch.setattr(driver, 'run_in_background', lambda fn, then=None, skip=False: fn())
        widget.on_press(driver.ctx)
        widget.on_double_press(driver.ctx)
        assert steps == [('sink', 10, 120, True), ('sink', -10, 120, True)]

    def test_long_press_toggles_mute(self, monkeypatch):
        toggled = []
        monkeypatch.setattr(_pulse, 'toggle_muted', toggled.append)
        driver, widget = started('volume')
        monkeypatch.setattr(driver, 'run_in_background', lambda fn, then=None, skip=False: then(fn()))
        widget.on_long_press(driver.ctx)
        assert toggled == ['sink']

    def test_handles_all_three_gestures(self):
        assert set(SPECS['volume'].events) == {'press', 'double_press', 'long_press'}
