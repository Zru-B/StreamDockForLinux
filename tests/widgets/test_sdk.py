"""The widget SDK: options, the driver's timers and events, drawing helpers."""

import os
import threading

import pytest
from PIL import Image

from streamdock_sdk import Option, OptionError, Widget, draw
from streamdock_sdk.options import resolve_options
from streamdock_sdk.scheduler import WidgetDriver, check_frame


class TestOptions:
    def test_int_rejects_bool_and_fraction(self):
        # YAML reads 'yes' as True; it must not pass as 1.
        option = Option.int('n', default=1, minimum=0, maximum=5)
        with pytest.raises(OptionError):
            option.coerce(True)
        with pytest.raises(OptionError):
            option.coerce(1.5)
        assert option.coerce(2.0) == 2

    def test_float_rejects_nan_and_infinity(self):
        # NaN compares false with any bound, so a range alone let it through.
        option = Option.float('scale', 1.0, minimum=0.0, maximum=10.0)
        for value in (float('nan'), float('inf'), float('-inf')):
            with pytest.raises(OptionError):
                option.coerce(value)

    def test_range_is_enforced(self):
        option = Option.float('f', default=0.5, minimum=0.0, maximum=1.0)
        with pytest.raises(OptionError):
            option.coerce(1.5)
        assert option.coerce(1) == 1.0

    def test_color_accepts_names_and_hex_only(self):
        option = Option.color('c')
        assert option.coerce('red') == 'red'
        assert option.coerce('#12ab34') == '#12ab34'
        with pytest.raises(OptionError):
            option.coerce('not-a-colour')

    def test_choice_defaults_to_first(self):
        option = Option.choice('mode', ['a', 'b'])
        assert option.default == 'a'
        with pytest.raises(OptionError):
            option.coerce('c')

    def test_bool_rejects_strings(self):
        with pytest.raises(OptionError):
            Option.bool('b').coerce('true')

    def test_round_trips_through_dict(self):
        option = Option.int('n', default=3, minimum=1, maximum=9, label='N', description='d')
        assert Option.from_dict(option.to_dict()) == option

    def test_resolve_fills_defaults_and_warns_on_unknown(self):
        schema = [Option.string('a', default='x'), Option.bool('b', default=True)]
        resolved, warnings = resolve_options(schema, {'b': False, 'zzz': 1})
        assert resolved == {'a': 'x', 'b': False}
        assert warnings == ["unknown option 'zzz' is ignored"]

    def test_resolve_raises_on_mistyped_value(self):
        with pytest.raises(OptionError):
            resolve_options([Option.int('n')], {'n': 'three'})


class Recorder(Widget):
    id = 'recorder'
    name = 'Recorder'
    version = '1'

    def setup(self, ctx):
        self.renders = 0
        self.events = []

    def render(self, ctx):
        self.renders += 1
        return Image.new('RGB', ctx.size)

    def on_press(self, ctx):
        self.events.append('press')

    def on_long_press(self, ctx):
        self.events.append('long_press')


class TestManifest:
    def test_events_are_the_overridden_hooks(self):
        assert Recorder.handled_events() == ('press', 'long_press')

    def test_manifest_carries_options_and_events(self):
        manifest = Recorder.manifest()
        assert manifest['id'] == 'recorder'
        assert manifest['events'] == ['press', 'long_press']


class FakeClock:
    def __init__(self, now):
        self.now = now

    def __call__(self):
        return self.now


def idle_driver(clock):
    """A driver whose loop never runs, so timers can be stepped by hand."""
    driver = WidgetDriver(Recorder, {}, clock=clock)
    driver.widget = Recorder()
    driver.widget.setup(driver.ctx)
    driver._visible = True
    return driver


class TestTimers:
    def test_aligned_timer_fires_just_after_the_minute(self):
        clock = FakeClock(1000.0)  # 16:40 past the epoch minute 960
        driver = idle_driver(clock)
        fired = []
        driver.ctx.every(60, lambda: fired.append(clock.now), align=True)

        clock.now = 1019.9
        driver._run_due_timers(clock.now)
        assert fired == []
        clock.now = 1020.0 + WidgetDriver.ALIGN_SLACK
        driver._run_due_timers(clock.now)
        assert fired == [clock.now]

    def test_a_clock_jump_fires_once_and_realigns(self):
        # After a suspend the wall clock leaps; one catch-up tick, not a burst.
        clock = FakeClock(1000.0)
        driver = idle_driver(clock)
        fired = []
        driver.ctx.every(60, lambda: fired.append(clock.now), align=True)

        clock.now = 5000.0
        driver._run_due_timers(clock.now)
        driver._run_due_timers(clock.now)
        assert len(fired) == 1
        assert driver._timers[0].due == pytest.approx(5040.0 + WidgetDriver.ALIGN_SLACK)

    def test_a_clock_going_back_realigns_instead_of_going_silent(self):
        # Setting the clock back an hour left the timer due an hour away.
        clock = FakeClock(5000.0)
        driver = idle_driver(clock)
        fired = []
        driver.ctx.every(60, lambda: fired.append(clock.now), align=True)

        clock.now = 1000.0
        driver._run_due_timers(clock.now)
        assert fired == []
        assert driver._timers[0].due == pytest.approx(1020.0 + WidgetDriver.ALIGN_SLACK)
        clock.now = 1021.0
        driver._run_due_timers(clock.now)
        assert fired == [1021.0]

    def test_sleep_is_capped_so_jumps_are_noticed(self):
        clock = FakeClock(0.0)
        driver = idle_driver(clock)
        driver.ctx.every(3600, lambda: None)
        assert driver._next_timeout(clock.now) == WidgetDriver.MAX_SLEEP

    def test_hidden_widget_timers_do_not_fire(self):
        clock = FakeClock(0.0)
        driver = idle_driver(clock)
        fired = []
        driver.ctx.every(1, lambda: fired.append(1))
        driver._visible = False

        clock.now = 10.0
        driver._run_due_timers(clock.now)
        assert fired == []
        assert driver._next_timeout(clock.now) is None


class TestDriverThread:
    def test_events_and_renders_reach_the_widget(self):
        frames = []
        got_frame = threading.Event()

        def on_frame(image):
            frames.append(image)
            got_frame.set()

        driver = WidgetDriver(Recorder, {}, on_frame=on_frame)
        driver.start()
        assert got_frame.wait(2)
        driver.post_event('press')
        driver.post_event('long_press')
        driver.show()
        driver.stop()

        assert driver.widget.events == ['press', 'long_press']
        assert frames[0].size == (112, 112)

    def test_render_failure_is_reported_not_raised(self):
        class Broken(Recorder):
            def render(self, ctx):
                raise RuntimeError('boom')

        errors = []
        reported = threading.Event()
        driver = WidgetDriver(Broken, {}, on_error=lambda message: (errors.append(message), reported.set()))
        driver.start()
        assert reported.wait(2)
        driver.stop()
        assert 'boom' in errors[0]

    def test_unknown_event_is_refused(self):
        with pytest.raises(ValueError):
            WidgetDriver(Recorder, {}).post_event('wiggle')


class TestFrames:
    def test_wrong_size_is_rejected(self):
        with pytest.raises(ValueError):
            check_frame(Image.new('RGB', (10, 10)), (112, 112))

    def test_non_image_is_rejected(self):
        with pytest.raises(TypeError):
            check_frame('not an image', (112, 112))

    def test_rgba_is_converted(self):
        assert check_frame(Image.new('RGBA', (112, 112)), (112, 112)).mode == 'RGB'

    def test_text_key_has_requested_size(self):
        assert draw.text_key('12:34', size=(96, 64)).size == (96, 64)


class Lamp(Widget):
    id = 'lamp'
    name = 'Lamp'
    version = '1'
    states = ('on', 'off')
    supports_badge = True

    def render(self, ctx):
        return Image.new('RGB', ctx.size)


class TestStateAndBadge:
    def test_changes_are_reported_once(self):
        states, badges = [], []
        driver = WidgetDriver(Lamp, {}, on_state=states.append, on_badge=badges.append)
        driver.ctx.set_state('on')
        driver.ctx.set_state('on')
        driver.ctx.set_badge(3)
        driver.ctx.set_badge('3')
        driver.ctx.set_badge('')
        assert states == ['on']
        assert badges == ['3', None]

    def test_undeclared_state_is_refused(self):
        # The editor offers images for declared states only; others would never show.
        with pytest.raises(ValueError):
            WidgetDriver(Lamp, {}).ctx.set_state('dim')

    def test_badge_is_kept_short(self):
        badges = []
        WidgetDriver(Lamp, {}, on_badge=badges.append).ctx.set_badge('123456789012')
        assert badges == ['12345678']

    def test_manifest_lists_states_and_badge(self):
        assert Lamp.manifest()['states'] == ['on', 'off']
        assert Lamp.manifest()['supports_badge'] is True

    def test_no_frames_when_drawing_is_off(self):
        frames = []
        started = threading.Event()
        driver = WidgetDriver(Lamp, {}, on_frame=frames.append, on_state=lambda s: started.set(),
                              draw_frames=False)
        driver.start()
        driver.show()
        driver.ctx.set_state('on')
        assert started.wait(2)
        driver.stop()
        assert frames == []


class TestWrap:
    def test_long_text_wraps_and_ends_in_an_ellipsis(self):
        image, canvas = draw.canvas((112, 112))
        lines = draw.wrap(canvas, 'Bohemian Rhapsody Remastered 2011 Deluxe Edition', draw.font(17), 100, 2)
        assert len(lines) == 2
        assert lines[-1].endswith('…')
        assert all(canvas.textlength(line, font=draw.font(17)) <= 100 for line in lines)

    def test_a_word_wider_than_the_key_is_broken(self):
        image, canvas = draw.canvas((112, 112))
        lines = draw.wrap(canvas, 'Supercalifragilisticexpialidocious', draw.font(17), 60, 5)
        assert ''.join(lines) == 'Supercalifragilisticexpialidocious'


class DataDirWidget(Widget):
    id = 'data_dir_widget'
    name = 'Data'
    version = '1'

    def setup(self, ctx):
        self.folder = ctx.data_dir

    def render(self, ctx):
        return Image.new('RGB', ctx.size)


class TestRenderOnceDataDir:
    def test_a_scratch_folder_is_lent_and_removed(self):
        driver = WidgetDriver(DataDirWidget, {})
        driver.render_once()
        assert not os.path.exists(driver.widget.folder)

    def test_a_given_folder_is_used(self, tmp_path):
        driver = WidgetDriver(DataDirWidget, {}, data_dir=str(tmp_path / 'mine'))
        driver.render_once()
        assert driver.widget.folder == str(tmp_path / 'mine')


class TestBackgroundJobs:
    def test_a_call_site_runs_one_job_at_a_time(self):
        # A poll slower than its interval used to stack up threads.
        driver = WidgetDriver(Recorder, {})
        release = threading.Event()
        started = []

        def poll():
            driver.run_in_background(lambda: started.append(1) or release.wait(5), None, skip_if_running=True)

        poll()
        poll()
        driver.run_in_background(lambda: started.append(2), None)
        release.set()
        for _ in range(100):
            if not driver._in_flight:
                break
            threading.Event().wait(0.01)
        assert sorted(started) == [1, 2]
        poll()
        for _ in range(100):
            if len(started) == 3:
                break
            threading.Event().wait(0.01)
        assert started.count(1) == 2

    def test_user_work_is_never_skipped(self):
        # Two quick presses of a mute toggle must toggle twice, even from one call site.
        driver = WidgetDriver(Recorder, {})
        release = threading.Event()
        started = []

        def press():
            driver.ctx.run_in_background(lambda: started.append(1) or release.wait(5))

        press()
        press()
        release.set()
        for _ in range(100):
            if len(started) == 2 and not driver._in_flight:
                break
            threading.Event().wait(0.01)
        assert started == [1, 1]
        assert not driver._in_flight
