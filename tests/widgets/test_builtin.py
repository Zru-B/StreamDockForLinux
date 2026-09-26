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
    _common, _dnd, _notifications, _pulse, audio_output, battery, network_speed, now_playing, pomodoro, system_stats,
    vpn_connected, weather)
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
    'audio_output': [{}, {'show_name': False}, {'outputs': 'hdmi', 'names': 'hdmi=TV'}],
    'battery': [{}, {'device': 'MX Master', 'label': 'Mouse'}],
    'network_speed': [{}, {'units': 'bits', 'interfaces': 'wlan*'}],
    'pomodoro': [{}, {'work_minutes': 50, 'break_minutes': 10, 'show_time': True}],
    'do_not_disturb': [{}, {'show_caption': False}],
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


class FakeDnd:
    def __init__(self, on=False):
        self.on = on
        self.writes = []

    def read(self):
        return self.on

    def write(self, on):
        self.writes.append(on)
        self.on = on


SINKS = [_pulse.Sink('alsa_output.pci.analog-stereo', 'Built-in Audio Analog Stereo', 'speakers'),
         _pulse.Sink('bluez_output.AA_BB', 'Sony WH-1000XM5', 'headphones'),
         _pulse.Sink('alsa_output.pci.hdmi-stereo', 'HDMI / DisplayPort 1 Output', 'hdmi')]

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
    monkeypatch.setattr(_dnd, 'backend', lambda name: FakeDnd())
    monkeypatch.setattr(network_speed, 'read_counters', lambda: {'eth0': (1000, 500), 'lo': (9, 9)})
    monkeypatch.setattr(_pulse, 'list_sinks', lambda: list(SINKS))
    monkeypatch.setattr(_pulse, 'default_sink', lambda: SINKS[0].name)
    monkeypatch.setattr(battery, 'read_battery', lambda device: battery.Reading(64, 'Discharging'))
    monkeypatch.setattr(network_speed, 'is_physical', lambda name: name == 'eth0')


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
             'whatsapp_notifications': 'none', 'telegram_notifications': 'none', 'do_not_disturb': 'off',
             'pomodoro': 'idle', 'battery': 'discharging', 'audio_output': 'speakers'}
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


class TestDoNotDisturb:
    def test_each_press_toggles_and_the_state_follows(self, monkeypatch):
        fake = FakeDnd(on=False)
        monkeypatch.setattr(_dnd, 'backend', lambda name: fake)
        driver, widget = started('do_not_disturb')
        monkeypatch.setattr(driver, 'run_in_background', lambda fn, then=None, skip=False: then(fn()))
        assert driver.state == 'off'
        widget.on_press(driver.ctx)
        assert (driver.state, fake.writes) == ('on', [True])
        widget.on_press(driver.ctx)
        assert (driver.state, fake.writes) == ('off', [True, False])

    def test_picks_up_a_switch_made_elsewhere(self, monkeypatch):
        fake = FakeDnd(on=False)
        monkeypatch.setattr(_dnd, 'backend', lambda name: fake)
        driver, widget = started('do_not_disturb')
        monkeypatch.setattr(driver, 'run_in_background', lambda fn, then=None, skip=False: then(fn()))
        fake.on = True
        widget.check(driver.ctx)
        assert driver.state == 'on'

    def test_no_backend_is_unavailable(self, monkeypatch):
        monkeypatch.setattr(_dnd, 'backend', lambda name: None)
        driver, widget = started('do_not_disturb')
        widget.on_press(driver.ctx)
        assert driver.state == 'unavailable'
        assert driver.widget.render(driver.ctx).size == (112, 112)

    @pytest.mark.parametrize('desktop, expected', [
        ('KDE', 'kde'), ('ubuntu:GNOME', 'gnome'), ('XFCE', 'xfce'), ('Unity', 'gnome')])
    def test_desktop_picks_the_backend(self, desktop, expected):
        assert _dnd.detect(desktop) == expected

    def test_other_desktops_look_for_a_running_daemon(self, monkeypatch):
        monkeypatch.undo()
        monkeypatch.setattr(_dnd, '_run', lambda *command: 'false' if command[0] == 'dunstctl' else None)
        assert _dnd.detect('sway') == 'dunst'
        monkeypatch.setattr(_dnd, '_run', lambda *command: None)
        assert _dnd.detect('sway') is None

    def test_gnome_dnd_is_banners_off(self, monkeypatch):
        monkeypatch.undo()
        calls = []

        def run(*command):
            calls.append(command)
            return 'false'
        monkeypatch.setattr(_dnd, '_run', run)
        gnome = _dnd.GnomeBackend()
        assert gnome.read() is True
        gnome.write(False)
        assert calls[-1][-2:] == ('show-banners', 'true')


class TestPomodoro:
    class Timer:
        """Stands in for threading.Timer; the tests end phases by moving the clock."""

        def __init__(self, interval, function):
            self.interval = interval
            self.daemon = False

        def start(self):
            pass

        def cancel(self):
            pass

    @pytest.fixture
    def world(self, monkeypatch):
        now = [1000.0]
        notes = []
        monkeypatch.setattr(pomodoro, 'clock', lambda: now[0])
        monkeypatch.setattr(pomodoro, 'notify', lambda summary, body: notes.append(summary))
        monkeypatch.setattr(pomodoro.threading, 'Timer', self.Timer)
        return now, notes

    def start(self, monkeypatch, **options):
        driver, widget = started('pomodoro', **options)
        monkeypatch.setattr(driver, 'run_in_background', lambda fn, then=None, skip=False: fn())
        return driver, widget

    def test_defaults_are_25_and_5_minutes(self):
        options = {option.key: option.default for option in SPECS['pomodoro'].options}
        assert (options['work_minutes'], options['break_minutes']) == (25, 5)

    def test_press_starts_pauses_and_resumes(self, world, monkeypatch):
        now, _ = world
        driver, widget = self.start(monkeypatch)
        assert (driver.state, driver.badge) == ('idle', None)
        widget.on_press(driver.ctx)
        assert (driver.state, driver.badge) == ('work', '25:00')
        now[0] += 60
        widget.on_press(driver.ctx)
        assert (driver.state, driver.badge) == ('paused', '24:00')
        now[0] += 600  # paused time doesn't count
        widget.on_press(driver.ctx)
        assert (driver.state, driver.badge) == ('work', '24:00')

    def test_long_press_resets(self, world, monkeypatch):
        driver, widget = self.start(monkeypatch)
        widget.on_press(driver.ctx)
        widget.on_long_press(driver.ctx)
        assert (driver.state, driver.badge) == ('idle', None)

    def test_work_then_break_then_waits(self, world, monkeypatch):
        now, notes = world
        driver, widget = self.start(monkeypatch, work_minutes=2, break_minutes=1)
        widget.on_press(driver.ctx)
        now[0] += 120
        widget.tick(driver.ctx)
        assert (driver.state, driver.badge, notes) == ('break', '1:00', ['Time for a break'])
        now[0] += 60
        widget.tick(driver.ctx)
        assert (driver.state, notes[-1]) == ('idle', 'Break is over')

    def test_auto_start_work_after_a_break(self, world, monkeypatch):
        now, notes = world
        driver, widget = self.start(monkeypatch, work_minutes=2, break_minutes=1, auto_start_work=True)
        widget.on_press(driver.ctx)
        now[0] += 180
        widget.advance(driver.ctx)
        assert (driver.state, driver.badge, notes) == ('work', '2:00', ['Back to work'])

    def test_catches_up_after_a_long_sleep(self, world, monkeypatch):
        now, notes = world
        driver, widget = self.start(monkeypatch, work_minutes=2, break_minutes=1)
        widget.on_press(driver.ctx)
        now[0] += 3600
        widget.on_show(driver.ctx)
        assert driver.state == 'idle'
        assert notes == ['Break is over']

    def test_notifications_can_be_turned_off(self, world, monkeypatch):
        now, notes = world
        driver, widget = self.start(monkeypatch, work_minutes=1, notify=False)
        widget.on_press(driver.ctx)
        now[0] += 60
        widget.advance(driver.ctx)
        assert (driver.state, notes) == ('break', [])

    def test_paused_ring_blinks_at_2_hz(self, world, monkeypatch):
        driver, widget = self.start(monkeypatch)
        assert [(timer.interval, timer.align) for timer in driver._timers] == [(0.25, True)]
        widget.on_press(driver.ctx)
        widget.on_press(driver.ctx)
        frames = []
        for _ in range(2):
            widget.tick(driver.ctx)
            frames.append(widget.render(driver.ctx).tobytes())
        assert frames[0] != frames[1]
        widget.tick(driver.ctx)
        assert widget.render(driver.ctx).tobytes() == frames[0]


class TestNetworkSpeed:
    def test_proc_net_dev_is_parsed(self, tmp_path, monkeypatch):
        monkeypatch.undo()
        path = tmp_path / 'dev'
        path.write_text(
            'Inter-|   Receive                            |  Transmit\n'
            ' face |bytes    packets errs drop fifo frame compressed multicast|bytes    packets ...\n'
            '    lo:  1234      10    0    0    0     0          0         0     1234      10 0 0 0 0 0 0\n'
            '  eth0: 987654   321    0    0    0     0          0         0   123456     111 0 0 0 0 0 0\n')
        assert network_speed.read_counters(str(path)) == {'lo': (1234, 1234), 'eth0': (987654, 123456)}

    def test_physical_interfaces_by_default(self):
        names = ['lo', 'eth0', 'wlan0', 'docker0', 'tun0']
        physical = {'eth0', 'wlan0'}.__contains__
        assert network_speed.selected(names, '', physical) == ['eth0', 'wlan0']
        assert network_speed.selected(names, 'tun*, docker0', physical) == ['docker0', 'tun0']

    @pytest.mark.parametrize('rate, bits, text', [
        (0, False, '0 B/s'), (999, False, '999 B/s'), (1500, False, '1.5 kB/s'), (2_500_000, False, '2.5 MB/s'),
        (45_000_000, False, '45 MB/s'), (125_000, True, '1.0 Mb/s'), (3e12, False, '3000 GB/s')])
    def test_rates_are_short(self, rate, bits, text):
        assert network_speed.format_rate(rate, bits) == text

    def test_speed_is_the_difference_of_two_readings(self, monkeypatch):
        readings = iter([{'eth0': (1000, 0), 'lo': (0, 0)}, {'eth0': (5_001_000, 200_000), 'lo': (9e9, 9e9)}])
        times = iter([100.0, 102.0])
        monkeypatch.setattr(network_speed, 'read_counters', lambda: next(readings))
        monkeypatch.setattr(network_speed, 'clock', lambda: next(times))
        driver, widget = started('network_speed')
        widget.sample(driver.ctx)
        assert (widget.down, widget.up) == (2_500_000, 100_000)
        assert (driver.state, driver.badge) == ('active', '2.5MB/s')


class TestBattery:
    @staticmethod
    def supply(root, name, **files):
        folder = root / name
        folder.mkdir()
        for key, value in files.items():
            (folder / key).write_text(value + '\n')

    @pytest.fixture
    def sysfs(self, tmp_path, monkeypatch):
        monkeypatch.undo()
        self.supply(tmp_path, 'AC', type='Mains', online='1')
        self.supply(tmp_path, 'BAT0', type='Battery', capacity='80', status='Discharging')
        self.supply(tmp_path, 'BAT1', type='Battery', capacity='40', status='Charging', scope='System')
        self.supply(tmp_path, 'hidpp_battery_0', type='Battery', scope='Device', capacity_level='Low',
                    status='Discharging', model_name='MX Master 3')
        return str(tmp_path)

    def test_system_batteries_count_as_one(self, sysfs):
        assert battery.read_battery('', sysfs) == battery.Reading(60, 'Charging')

    def test_a_peripheral_by_model_with_only_a_level(self, sysfs):
        assert battery.read_battery('mx master', sysfs) == battery.Reading(15, 'Discharging', approximate=True)

    def test_nothing_found(self, sysfs):
        assert battery.read_battery('keyboard', sysfs) is None
        assert battery.read_battery('', '/nonexistent') is None

    @pytest.mark.parametrize('reading, state', [
        (battery.Reading(64, 'Discharging'), 'discharging'), (battery.Reading(12, 'Discharging'), 'low'),
        (battery.Reading(12, 'Charging'), 'charging'), (battery.Reading(100, 'Full'), 'full'),
        (battery.Reading(100, 'Not charging'), 'full'), (None, 'unavailable')])
    def test_states(self, monkeypatch, reading, state):
        monkeypatch.setattr(battery, 'read_battery', lambda device: reading)
        driver, widget = started('battery')
        assert driver.state == state
        assert driver.badge == (None if reading is None else f'{reading.percent}%')
        assert widget.render(driver.ctx).size == (112, 112)


class TestAudioOutput:
    def test_press_cycles_through_the_outputs(self, monkeypatch):
        switched = []
        monkeypatch.setattr(_pulse, 'set_default_sink', lambda name, move: switched.append((name, move)))
        driver, widget = started('audio_output')
        monkeypatch.setattr(driver, 'run_in_background', lambda fn, then=None, skip=False: fn())
        for _ in range(3):
            widget.on_press(driver.ctx)
        assert [name for name, _ in switched] == [SINKS[1].name, SINKS[2].name, SINKS[0].name]
        assert driver.state == 'speakers'

    def test_outputs_option_picks_and_orders(self):
        chosen = audio_output.cycle(SINKS, 'hdmi, built-in')
        assert [sink.kind for sink in chosen] == ['hdmi', 'speakers']
        assert audio_output.next_sink(chosen, SINKS[1].name) is chosen[0]
        assert audio_output.next_sink([], None) is None

    def test_short_names(self):
        assert audio_output.display_name(SINKS[1], 'Built-in=Desk, sony = Buds') == 'Buds'
        assert audio_output.display_name(SINKS[2], 'Built-in=Desk') == 'HDMI / DisplayPort 1 Output'

    @pytest.mark.parametrize('args, kind', [
        (('alsa_output.pci-0000_00_1f.3.hdmi-stereo',), 'hdmi'),
        (('bluez_output.00_11', 'Buds', '', '', 'bluetooth'), 'headphones'),
        (('alsa_output.usb-headset', 'USB', '', 'headset'), 'headphones'),
        (('alsa_output.pci.analog-stereo', 'Built-in', 'analog-output-headphones'), 'headphones'),
        (('alsa_output.pci.analog-stereo', 'Built-in', 'analog-output-speaker'), 'speakers')])
    def test_kind_of_output(self, args, kind):
        assert _pulse.sink_kind(*args) == kind

    def test_pactl_json_is_read(self, monkeypatch):
        monkeypatch.undo()
        output = ('[{"name": "bluez_output.X", "description": "Buds", "active_port": null,'
                  ' "properties": {"device.bus": "bluetooth"}}]')
        monkeypatch.setattr(_pulse, '_pactl_output', lambda *args: output if args[0] == '--format=json' else None)
        assert _pulse.list_sinks() == [_pulse.Sink('bluez_output.X', 'Buds', 'headphones')]

    def test_old_pactl_falls_back_to_names(self, monkeypatch):
        monkeypatch.undo()
        short = '0\talsa_output.pci.hdmi-stereo\tPipeWire\ts32le 2ch 48000Hz\tSUSPENDED\n'
        monkeypatch.setattr(_pulse, '_pactl_output', lambda *args: short if args[0] == 'list' else None)
        name = 'alsa_output.pci.hdmi-stereo'
        assert _pulse.list_sinks() == [_pulse.Sink(name, name, 'hdmi')]

    def test_streams_move_on_pulseaudio(self, monkeypatch):
        monkeypatch.undo()
        calls = []

        def pactl(*args):
            calls.append(args)
            return '12\t0\t34\tPipeWire\tfloat32le 2ch 48000Hz\n' if args[:2] == ('list', 'short') else ''
        monkeypatch.setattr(_pulse, '_pactl_output', pactl)
        _pulse.set_default_sink('sink2')
        assert calls == [('set-default-sink', 'sink2'), ('list', 'short', 'sink-inputs'),
                         ('move-sink-input', '12', 'sink2')]
