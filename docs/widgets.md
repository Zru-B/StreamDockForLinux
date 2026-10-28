# Widgets

A **widget** is a key that draws itself. A normal key shows a fixed icon or
text. A widget key shows whatever a small Python script draws, and the app
redraws it whenever the script asks: every minute for a clock, when the
microphone is muted for a mute indicator. The device can't draw on its own, so
the app renders each frame and sends it to the key.

A widget key is still an ordinary key. Its press, release, double-press and
long-press actions run as usual. A widget can also react to its own key being
pressed: the microphone widget toggles mute, and the example counter counts.

## Using a widget

In the key editor, set **Display Type** to **Widget**, pick a widget and adjust
its options. The preview shows what the key will look like, and the grid shows
a snapshot of it. Press **Apply** to put it on the device.

In `config.yml` a widget key looks like this:

```yaml
keys:
  Clock:
    widget: digital_clock
    widget_options:
      format: 12h
      show_seconds: false
    on_press_actions:            # optional; a widget needs no actions
      - LAUNCH_APPLICATION: { desktop_file: org.kde.kclock }
```

`widget` can't be combined with `text`. Options you leave out take their
defaults.

Widgets only work while you can see them. A widget starts the first time its
key appears on the device, and pauses (timers, watchers, polling) whenever its
layout is switched away or the screen locks. When the key comes back, it
catches up at once. The exception is the notification counters, which keep
listening while hidden, since they would otherwise miss the very messages they
count. A widget that isn't installed (for example, one you removed)
doesn't stop the configuration from loading: its key shows a red **!** tile.

Avoid `CHANGE_KEY_IMAGE` and `CHANGE_KEY_TEXT` on a widget key. The widget's
next frame replaces whatever they draw.

## Your own images, and badges

A widget key can show your own images instead of what the widget draws. Each
widget reports a **state**, such as `connected`/`disconnected` or
`muted`/`unmuted`, and you can give an image for each one:

```yaml
VPN:
  widget: vpn_connected
  state_icons:
    connected: img/vpn_on.png
    disconnected: img/vpn_off.png
```

Some widgets also report a **badge**, a short text such as an unread count or
a temperature. Give the key a base `icon`, and the badge is drawn in a corner
on top of it:

```yaml
Slack:
  widget: slack_notifications
  icon: img/slack.png
  badge:
    position: top_right        # top_right (default), top_left, bottom_right, bottom_left
    color: "#e01e5a"           # default red
    text_color: "#ffffff"
  on_press_actions:
    - LAUNCH_APPLICATION: { desktop_file: slack }
```

What the key shows:

1. the `state_icons` image for the current state, if there is one;
2. otherwise the `icon`, if there is one;
3. otherwise the widget's own drawing.

The badge is drawn only over your images (1 and 2), never over the widget's
own drawing, which usually shows the same number already. Use `badge: false`
to hide it. With an `icon`, the widget never draws at all.

In the key editor, all of this is on the **Images** tab of the Widget section.
The preview shows a sample badge while the widget has none to report, so you
can see where it will go.

## Built-in widgets

| Widget | id | Options |
|---|---|---|
| Digital Clock | `digital_clock` | `format` (`24h`/`12h`), `show_seconds`, `timezone`, `color`, `background` |
| Analog Clock | `analog_clock` | `show_seconds`, `timezone`, `face_color`, `hand_color`, `second_hand_color`, `background` |
| Countdown | `countdown` | `target`, `title`, `done_text`, `soon_minutes`, `timezone`, `color`, `soon_color`, `done_color`, `background` |
| Date | `date` | `format` (`weekday_day_month`, `day_month`, `iso`, `numeric`), `color`, `accent`, `background` |
| Battery | `battery` | `devices`, `label`, `low`, `interval`, `color`, `background` |
| Network Speed | `network_speed` | `interfaces`, `units` (`bytes`/`bits`), `interval`, `idle_below`, `down_color`, `up_color`, `color`, `background` |
| Temperature | `temperature` | `sensor`, `label`, `units` (`celsius`/`fahrenheit`), `warm`, `hot`, `interval`, `color`, `background` |
| System Stats | `system_stats` | `metric` (`cpu`, `ram`, `both`), `interval`, `color`, `bar_color`, `alert_color`, `background` |
| Microphone Mute | `mic_muted` | `toggle_on_press`, `show_caption`, `muted_color`, `unmuted_color`, `color` |
| Sound Mute | `sound_muted` | same as Microphone Mute |
| Pomodoro | `pomodoro` | `work_minutes`, `break_minutes`, `auto_start_work`, `notify`, `show_time`, `work_color`, `break_color`, `background` |
| Do Not Disturb | `do_not_disturb` | `backend` (`auto`, `kde`, `gnome`, `xfce`, `dunst`, `swaync`), `interval`, `show_caption`, `on_color`, `off_color`, `color` |
| Audio Output | `audio_output` | `outputs`, `move_streams`, `show_name`, `names`, `color`, `background` |
| Volume | `volume` | `step`, `max_volume`, `unmute_on_raise`, `color`, `gauge_color`, `muted_color`, `background` |
| Volume Column (1x3) | `volume_column` | `button` (`up`, `mute`, `down`), `step`, `max_volume`, `unmute_on_raise`, `show_level_bar`, colours |
| VPN Status | `vpn_connected` | `source` (`auto`, `networkmanager`, `interfaces`), `interfaces`, `interval`, colours |
| Weather | `weather` | `location`, `units` (`celsius`/`fahrenheit`), `refresh_minutes`, `color`, `background` |
| Now Playing | `now_playing` | `player`, `show_art`, `art_brightness`, `toggle_on_press`, `interval`, `color`, `background` |
| Media Playing | `media_playing` | `player`, `toggle_on_press`, `interval`, colours |
| Slack Notifications | `slack_notifications` | see [Notification counters](#notification-counters) |
| WhatsApp Notifications | `whatsapp_notifications` | see [Notification counters](#notification-counters) |
| Telegram Notifications | `telegram_notifications` | see [Notification counters](#notification-counters) |

States and badges, for `state_icons` and badge overlays:

| Widget | States | Badge |
|---|---|---|
| `countdown` | `counting`, `soon`, `done`, `invalid` | the time left, e.g. `3d`, `5h`, `12m` |
| `mic_muted`, `sound_muted` | `muted`, `unmuted`, `unknown` | — |
| `do_not_disturb` | `on`, `off`, `unavailable` | — |
| `pomodoro` | `idle`, `work`, `break`, `paused` | the time left, e.g. `12:34` |
| `audio_output` | `speakers`, `headphones`, `hdmi`, `unknown` | — |
| `volume`, `volume_column` | `muted`, `unmuted`, `unknown` | the volume, e.g. `45%` |
| `vpn_connected` | `connected`, `disconnected`, `unknown` | — |
| `battery` | `charging`, `discharging`, `full`, `low`, `unavailable` | the charge, e.g. `64%` |
| `network_speed` | `idle`, `active` | the download speed, e.g. `2.5MB/s` |
| `temperature` | `normal`, `warm`, `hot`, `unavailable` | the temperature, e.g. `64°` |
| `system_stats` | `normal`, `high` (anything shown above 85%) | the first figure shown, e.g. `35%` |
| `weather` | `clear`, `clear_night`, `partly_cloudy`, `cloudy`, `fog`, `rain`, `snow`, `storm`, `unknown` | temperature, e.g. `21°` |
| `media_playing`, `now_playing` | `playing`, `paused`, `stopped`, `none` | — |
| `slack_notifications`, `whatsapp_notifications`, `telegram_notifications` | `unread`, `none`, `unavailable` | the unread count |

`timezone` takes an IANA name such as `Europe/London`. Leave it empty for local time.

The mute widgets use `pactl`, which works with both PulseAudio and PipeWire.
They update as soon as the mute changes anywhere, not only when you press the
key. If `toggle_on_press` is on, don't also give the key a `DBUS: mute`
action, or one press will toggle mute twice.

**Weather** uses [Open-Meteo](https://open-meteo.com), which needs no account.
`location` is a place name (looked up once) or `latitude,longitude`. Pressing
the key updates it straight away.

**Now Playing** and **Media Playing** read any MPRIS player (Spotify, browsers,
VLC, mpv…) through `busctl`, which comes with systemd. They show the player
that's playing, or the one named in `player`, e.g. `spotify`. Pressing the key
plays or pauses.

### Battery

**Battery** shows the charge of the laptop and of connected devices: a
wireless mouse or keyboard, Bluetooth headphones, a game controller. Each
press shows the next device; the device's name is above the battery and a row
of dots below shows which one of how many is on show. The battery is green,
amber below 50% and red at or below `low` (20% by default), with a bolt while
it charges.

`devices` limits and orders the devices a press cycles through, by part of
their name or their kind (`laptop`, `mouse`, `keyboard`, `headset`,
`headphones`...): `laptop, mouse, WH-1000` shows those three in that order.
Empty shows every device found, the laptop first. For a key that always shows
one device, give just that one, e.g. `devices: MX Master`, and a `label` if
you want another name above it.

Devices come from UPower (`upower --dump` lists what it sees), which knows
Bluetooth headphones through BlueZ. Without UPower they come from
`/sys/class/power_supply`, which has the laptop and devices whose kernel
driver reports a battery, such as most Logitech ones, but not Bluetooth
headphones. The key checks every `interval` seconds, and on each press, so a
device that just connected turns up.

Some devices report only a level (critical, low, normal, high, full) rather
than a percentage; the key then shows the level's name. A laptop with two
batteries counts as one.

### Countdown

**Countdown** shows the time left until `target`, with an optional `title`
above it:

| `target` | Counts down to |
|---|---|
| `2026-12-24` | midnight at the start of that day |
| `2026-12-24 18:00` | that moment |
| `17:30` | the next 17:30, every day; the end of the workday, say |

Two days or more show as days, then hours and minutes, and in the last hour
minutes and seconds. The time turns amber `soon_minutes` before (60 by
default) and shows `done_text` (`Now!`) in green once it's reached; a date in
the past stays that way. A `target` it can't read shows **Bad date**.

### Network Speed

**Network Speed** shows the download (blue, arrow down) and upload (orange,
arrow up) speed, over a graph of the last 40 readings: download as a filled
area, upload as a line.

It counts every physical interface (wired and wireless) by default, and
leaves out tunnels, bridges and containers, so traffic through a VPN isn't
counted twice. To count something else, set `interfaces` to names or patterns,
e.g. `wlan0` or `en*, wg0`. `units: bits` shows Mb/s, as speed tests do; the
default is MB/s, as file managers show. The state is `idle` while both
directions stay below `idle_below` kB/s.

### Audio Output

**Audio Output** shows which output sound plays through, as speakers,
headphones or a monitor with the output's name, and each press switches to the
next one. What's playing moves along to the new output.

- `outputs` limits and orders the outputs a press cycles through, by part of
  their name: `Speakers, Buds` switches between those two only. Empty cycles
  through all of them.
- `names` gives outputs short names for the key: `Built-in=Desk, Sony=Buds`.
- Bluetooth outputs, and outputs named or plugged in as headphones or a
  headset, show headphones. HDMI and DisplayPort outputs show a monitor.
  Everything else shows a speaker.

It uses `pactl`, like the volume widgets, and follows changes made elsewhere.
PipeWire moves playing streams to the new output by itself. On PulseAudio the
widget moves them, unless `move_streams` is off.

### Temperature

**Temperature** shows a temperature and a thermometer that's green, amber from
`warm` (70 °C) and red from `hot` (85 °C). The thresholds are always in °C,
even with `units: fahrenheit`.

`sensor` picks what to show:

| `sensor` | Reads |
|---|---|
| `cpu` (default) | Intel `coretemp` package, AMD `k10temp`/`zenpower`, or the board's `cpu_thermal` / `acpitz` |
| `gpu` | `amdgpu`, `nouveau`, `radeon` or Intel; NVIDIA's own driver through `nvidia-smi` |
| `nvme` | The SSD's composite temperature |
| a chip, e.g. `k10temp` | That chip's first reading |
| a chip and reading, e.g. `nvme/Sensor 1` | That reading |

The chips and readings are the ones `sensors` (from lm-sensors) lists, or the
`name` and `temp*_label` files under `/sys/class/hwmon`.

### Volume

**Volume** puts the default speaker's volume on one key, as a gauge with the
percentage under a speaker icon.

| Gesture | Does |
|---|---|
| Press | Raises the volume by `step` percent (default 5), up to `max_volume` |
| Double press | Lowers it by `step` percent |
| Long press | Mutes, or unmutes; the gauge turns red while muted |

`max_volume` is 100 by default; up to 150 amplifies. With `unmute_on_raise`
(the default), raising the volume also unmutes, as keyboard volume keys do.

Because the key tells a press from a double press and a hold, a press takes
effect when you let go of the key, after the double-press window
(`double_press_interval`, 0.3 s by default). Hold the key for
`long_press_duration` (0.5 s) to mute. If a single, immediate press matters
more, use the volume column below. [Action Triggers](configuration.md#action-triggers)
explains the timing.

### Volume column

**Volume Column (1x3)** fills one column of the device with three keys: volume
up on top, mute in the middle, volume down at the bottom. A key shows one
widget, so the column is three keys that each use `volume_column` with a
different `button`. Stack them in one column, top to bottom `up`, `mute`,
`down`. Each draws its third of a shared level bar, so the column reads as one
tall meter.

```yaml
keys:
  VolumeUp:
    widget: volume_column
    widget_options: { button: up }
  VolumeMute:
    widget: volume_column
    widget_options: { button: mute }
  VolumeDown:
    widget: volume_column
    widget_options: { button: down }

layouts:
  Main:
    keys:
      - 5: VolumeUp        # the right-hand column: 5, 10, 15
      - 10: VolumeMute
      - 15: VolumeDown
```

- **up** and **down** change the default speaker's volume by `step` percent
  (default 5). Raising stops at `max_volume` (default 100; up to 150
  amplifies). With `unmute_on_raise` (the default), raising also unmutes, as
  keyboard volume keys do.
- **mute** toggles the mute and shows the volume, or **MUTED** on red.

Give all three keys the same `step`, `max_volume` and colours. The level bar
reads them per key, so different values split it unevenly. The keys follow
volume changes made anywhere, through `pactl` like the mute widgets.

### Do Not Disturb

**Do Not Disturb** silences desktop notifications. Each press switches it on or
off, and the key shows which: a moon on purple while it's on, a bell while
notifications are shown, a grey bell when no supported desktop was found.

`backend` is `auto` by default: KDE Plasma, GNOME or XFCE by the desktop you're
running, otherwise a running SwayNotificationCenter or dunst. The key checks
every `interval` seconds, so Do Not Disturb switched elsewhere shows too. On
KDE that covers apps that hold notifications back, but not Plasma's own tray
switch, which the key can't read.

| Backend | How |
|---|---|
| `kde` | Asks Plasma's notification server to hold notifications back. Plasma shows this as Do Not Disturb in the tray. Needs `dbus-python` (see [Installation](installation.md)). It ends when StreamDock quits. The key can't switch off a Do Not Disturb that another app asked for. |
| `gnome` | Turns off notification banners, as GNOME's own Do Not Disturb switch does. |
| `xfce` | The `xfce4-notifyd` Do Not Disturb setting, through `xfconf-query`. |
| `dunst` | `dunstctl set-paused`. |
| `swaync` | `swaync-client --dnd-on` / `--dnd-off`. |

### Pomodoro

**Pomodoro** times work sessions and breaks: 25 minutes of work, then a
5-minute break, by default. Set `work_minutes` (1-180) and `break_minutes`
(1-60) to change them.

| Gesture | Does |
|---|---|
| Press | Starts a work session; while one is running, pauses it; while paused, resumes |
| Long press | Resets to idle |

What the key shows:

| State | Key |
|---|---|
| Idle | A tomato with watch hands |
| Work | The same tomato inside an amber ring that shortens as the session runs out |
| Paused | The tomato, with the ring as it was blinking twice a second |
| Break | A smiling tomato inside a green ring that shortens as the break runs out |

When the work session ends the break starts on its own. When the break ends
the timer goes back to idle and waits for a press, unless `auto_start_work` is
on. Each change of phase sends a desktop notification (`notify-send`); turn
`notify` off to stop them. `show_time` draws the minutes and seconds left on
the tomato instead of its hands or face.

The timer keeps running while you switch layouts or lock the screen, and the
notification still comes on time. Because the key has a long press, a press
takes effect when you let go of the key.

### Notification counters

The Slack, WhatsApp and Telegram widgets count an app's desktop notifications.
They need no account or token, so they count only messages the app shows a
notification for (not muted channels, and not while you're already looking at
the chat).

The count clears:

- when that app's window gets focus. `focus_match` is matched against the
  window's class and title, so the browser tab titled "WhatsApp" counts;
- when the app withdraws the notifications it sent, which chat apps typically
  do once you've read the message (`follow_app`);
- when you press the key (`reset_on_press`).

Each can be turned off. They identify notifications in two ways:

| Option | Slack | WhatsApp | Telegram | Meaning |
|---|---|---|---|---|
| `app_name` | `slack` | `whatsapp, zapzap` | `telegram` | parts of the sending app's name (or its desktop file) |
| `site` | `app.slack.com` | `web.whatsapp.com` | `web.telegram.org` | a browser notification mentioning this site |
| `focus_match` | `slack` | `whatsapp` | `telegram` | window class or title that means you're reading |

**Web apps in a browser.** Chrome, Chromium, Brave and Edge put the site's
address in the notification text, so `site` finds WhatsApp Web and Telegram
Web there. Firefox doesn't always. If a web app's notifications aren't
counted, run this, trigger a message, and look at the app name and text
Firefox sends:

```sh
busctl --user monitor --match "type='method_call',member='Notify'"
```

Then put something from it in `app_name` or `site`. Setting `app_name` to
`firefox` counts every Firefox notification, not just WhatsApp's.

One `busctl monitor` process serves every counter.

The VPN widget in `auto` mode counts you as connected if NetworkManager has an
active VPN or WireGuard connection, or if an interface matching `interfaces`
(default `tun*,wg*,ppp*,fctvpn*`) is up. `fctvpn*` is the interface FortiClient
VPN creates. Add `tailscale0` to that list if you use Tailscale.

## Third-party widgets

Open **Keys → Widgets…** and choose **Install…**. Pick either:

- a single `.py` file, or
- the `widget.py` inside a folder. The whole folder is installed, so a widget
  can ship helper modules and images alongside its script.

Installing works on a private copy of the widget, taken first, so what you
agree to is exactly what gets installed even if the original files change
meanwhile:

1. **It reads the copy without running it.** The script must define exactly
   one subclass of `streamdock_sdk.Widget`. Its `id`, `name`, `version` and
   `options` must be plain literals, so the app can list and configure the
   widget without executing it.
2. **It asks you**, listing what the widget can do (below). Nothing of the
   widget has run yet.
3. **Only after you agree, it runs the widget once in a separate process** and
   checks that it draws a correctly sized frame within 5 seconds, and that it
   didn't change its own files while doing so. Then the checked copy is moved
   into place.

**Checking a widget doesn't make it safe.** A widget is a program. It runs
with your user's permissions and can read your files. The install dialog lists
anything the script does beyond drawing a key (runs other programs, uses the
network, loads native code, talks to D-Bus, builds code at runtime, sees which
window you focus). Install
widgets only from sources you trust.

Installed widgets live in `~/.local/share/streamdock/widgets/<id>/`. If you
edit one of their files afterwards, or add a symbolic link or a `__pycache__`
folder, the app won't run the widget until you choose **Approve Again…**,
which checks it again, asks again and test-runs it, in the same order as an
install. The files are checked again each time the widget's process starts,
so a change is caught even while the app is running. Widgets run with
Python's bytecode cache turned off, so a `.pyc` file never stands in for the
source you approved.

Each third-party widget runs in its own process. If it crashes, it is
restarted after 1, 2, 4… seconds. After five crashes in a row it stays stopped
and its key shows the error tile. A widget that hangs only affects its own key.

## Writing a widget

```python
from streamdock_sdk import Option, Widget, draw


class Counter(Widget):
    id = 'hello_counter'          # lowercase letters, digits, _; unique
    name = 'Counter'
    version = '1.0.0'
    sdk_version = 1               # optional; the SDK version you wrote against
    description = 'Counts presses; hold the key to reset.'
    author = 'You'
    options = [
        Option.color('color', default='#ffffff', label='Text colour'),
        Option.int('start', default=0, minimum=0, label='Start at'),
    ]

    def setup(self, ctx):
        self.count = ctx.options['start']

    def render(self, ctx):
        return draw.text_key(str(self.count), color=ctx.options['color'], size=ctx.size)

    def on_press(self, ctx):
        self.count += 1
        ctx.request_render()

    def on_long_press(self, ctx):
        self.count = ctx.options['start']
        ctx.request_render()
```

Two complete examples are in `examples/widgets/`:

- [`hello_counter.py`](../examples/widgets/hello_counter.py): options, key
  events, redrawing.
- [`reachability.py`](../examples/widgets/reachability.py): network work in
  the background, `states` and a badge, and pausing while hidden.

### The Widget class

Everything above `setup` is read from the source without running it, so each
value must be a plain literal: a string, number, `True`/`False`, or a tuple or
list of those. `id = PREFIX + '_x'` is refused.

| Member | Required | Meaning |
|---|---|---|
| `id` | yes | 3–41 characters: a lowercase letter, then lowercase letters, digits or `_`. Unique; can't reuse a built-in's id. |
| `name`, `version` | yes | Non-empty strings. `version` is shown to users; any format. |
| `sdk_version` | no | The SDK version you wrote against (default and current: `1`). A widget asking for a newer SDK is refused. |
| `description`, `author` | no | Strings shown in the editor and the install dialog. |
| `options` | no | A list of `Option.<type>(...)` calls with literal arguments. |
| `states` | no | A tuple of state names (a lowercase letter, then lowercase letters, digits or `_`; up to 31 characters) the widget reports. |
| `supports_badge` | no | `True` if the widget reports a badge. |
| `run_while_hidden` | no | `True` to start at once and keep running while the key is off the device. |
| `setup(ctx)` | no | Runs once before the first frame. Start timers here. |
| `render(ctx)` | yes | Returns a PIL image of exactly `ctx.size` (112×112 on the 293V3). |
| `on_press` / `on_release` / `on_double_press` / `on_long_press` | no | Key events. Override only the ones you use. |
| `on_show` / `on_hide` | no | The key appeared on or left the device (layout switch, screen lock). |
| `on_window_focus(ctx, app, title)` | no | A window got focus. Delivered visible or not, only to widgets that define it. |
| `teardown(ctx)` | no | Runs once when the widget stops. |

Only override the key events you use. Overriding `on_long_press` changes how
the key's gestures behave: the key waits to see whether a press is a hold
before it runs the press actions. [Action Triggers](configuration.md#action-triggers)
explains how.

### Options

| Constructor | Value | Editor control |
|---|---|---|
| `Option.string(key, default='')` | text | text field |
| `Option.int(key, default=0, minimum=None, maximum=None)` | whole number | spin box |
| `Option.float(key, default=0.0, minimum=None, maximum=None)` | number | spin box |
| `Option.bool(key, default=False)` | true/false | switch |
| `Option.color(key, default='#ffffff')` | colour name or `#rrggbb` | text field and picker |
| `Option.choice(key, choices, default=None)` | one of `choices` (default: the first) | drop-down |

Every constructor also takes `label` (default: the key, capitalised) and
`description` (shown as a tooltip). Each option's default must itself be a
valid value, and each key may appear only once.

Values from `config.yml` are checked against these types before your widget
sees them, so `ctx.options['start']` is always an `int`. A wrong value is a
configuration error that names the option. An option the widget doesn't
declare is ignored, with a warning in the log.

### The context

`ctx` is passed to every hook:

| Member | Meaning |
|---|---|
| `ctx.options` | The options, read-only, with defaults filled in. |
| `ctx.size` | `(width, height)` of the key. |
| `ctx.request_render()` | Draw a new frame soon. Repeated calls before it runs merge into one. |
| `ctx.set_state(name)` | Report one of the declared `states`, or `None`. Keys with `state_icons` switch image. Raises `ValueError` for a name not in `states`. |
| `ctx.set_badge(text)` | Report a short badge, or `None`/`''` for none. Anything else is turned into a string and cut to 8 characters. |
| `ctx.every(seconds, fn=None, align=False)` | Call `fn` (by default, redraw) every `seconds` while the key is shown. With `align=True` it fires on wall-clock multiples, so `every(60, align=True)` fires at :00 of each minute. |
| `ctx.run_in_background(fn, then=None, *, skip_if_running=False)` | Run blocking `fn` on another thread, then call `then(result)` back on the widget's thread. If `fn` raises, the error is logged and `then` isn't called. Pass `skip_if_running=True` from a periodic poll: the call is then skipped while a job started from the same line of code is still running, so a poll slower than its interval doesn't pile up. Leave it off for work the user asked for, such as a toggle on a press. |
| `ctx.call_soon(fn)` | Run `fn` on the widget's thread. Safe to call from any thread. |
| `ctx.visible` | Whether the key is on the device right now. |
| `ctx.data_dir` | A folder for the widget's own files (`~/.local/state/streamdock/widgets/<id>/`), created on first use. In editor previews and the install check it's a throwaway folder, deleted afterwards. |
| `ctx.log` | A `logging.Logger` named `widget.<id>`. Output goes to the app's log. |

State and badge changes are passed on only when the value actually changes, so
reporting the same value on every poll costs nothing.

### Drawing helpers

`from streamdock_sdk import draw`. Colours are anything Pillow accepts: a name
or `#rrggbb`.

| Helper | Returns |
|---|---|
| `draw.text_key(text, color='white', background='black', size=(112, 112), bold=True, padding=8)` | A whole key showing `text` as large as it fits. `\n` starts a new line. |
| `draw.canvas(size=(112, 112), background='black')` | `(image, drawing)`: a blank key and a Pillow `ImageDraw` for it. |
| `draw.centered_text(drawing, box, text, color='white', text_font=None, bold=True)` | Draws `text` centred in `box` = `(left, top, right, bottom)`. It shrinks the text to fit unless you pass `text_font`. |
| `draw.fit_font(drawing, text, max_width, max_height, start=64, bold=True, minimum=8)` | The largest font, from `start` down, in which `text` fits the size. |
| `draw.wrap(drawing, text, text_font, max_width, max_lines)` | A list of at most `max_lines` lines. Words longer than a line are broken, and the last line ends in "…" if text was left over. |
| `draw.font(size, bold=True)` | The TrueType font ordinary text keys use, at `size` pixels. |

For smooth shapes, draw at 4× the key size and shrink the result with
`image.resize(ctx.size, Image.LANCZOS)`. The built-in status widgets do this.

### Other names the SDK exports

| Name | What it is |
|---|---|
| `KEY_EVENTS` | `('press', 'release', 'double_press', 'long_press')` |
| `SDK_VERSION` | The SDK version this app provides (`1`). |
| `OptionError` | Raised by `Option.coerce(value)` for a value of the wrong type or range. |
| `WidgetContext` | The type of `ctx`, for type hints. |

### Rules of thumb

- **All hooks run on one thread**, one at a time, so you don't need locks for
  your widget's own state. Code in `run_in_background` is the exception: have
  it return a result and handle it in `then`.
- **Keep `render` fast.** Do network requests, D-Bus calls and subprocesses in
  `run_in_background`, store the result, and call `request_render()`. A quick
  first reading in `setup` is fine; it makes the first frame right.
- **Widgets start lazily and pause while hidden.** `setup` runs when the key
  first appears; timers stop on `on_hide`. Stop your own watchers in `on_hide`,
  and refresh in `on_show`, where the widget also redraws. Only set
  `run_while_hidden` if missing events while hidden would be wrong.
- **Timers survive suspend.** They are measured against the wall clock and
  checked at least every 5 seconds, so a clock is right again within seconds
  of waking up.
- **Report state and badge even though you draw.** It costs nothing, and it
  lets users put your widget on their own images.
- **`print()` is safe.** Its output goes to the app's log, not to the key.

### When things go wrong

| What happens | Result |
|---|---|
| `render` raises, or returns something other than a PIL image of `ctx.size` | The key shows the red error tile and the error is logged. The next successful render replaces it. |
| `setup` raises | The error is logged, the key shows the error tile, and the widget stays stopped until the app restarts or the key's widget settings change. |
| Another hook raises (key event, timer, `then`, `on_show`…) | The error is logged; the widget keeps running. |
| A third-party widget's process crashes or exits | It restarts after 1, 2, 4… seconds (at most 30). After 5 crashes in a row it stays stopped and shows the error tile. |
| A third-party widget doesn't start within 5 seconds | The process is killed; this counts as a crash. |
| A widget asks for frames too fast | Each key gets at most four updates a second; identical frames are skipped. |

### Install rules

A third-party widget is refused at install if:

- it isn't a `.py` file or a folder containing `widget.py`;
- a `.py` file is over 256 KB, the widget is over 5 MB, it has more than 200
  files, or it contains a symbolic link (to a file or a folder);
- any `.py` file doesn't parse;
- `widget.py` doesn't define exactly one class that subclasses `Widget`
  directly, imported as `from streamdock_sdk import Widget` or used as
  `streamdock_sdk.Widget`;
- a class attribute from the table above isn't a plain literal of the right
  kind, `render` is missing, or an option is written other than as
  `Option.<type>(...)` with literal arguments;
- its `name` is longer than 80 characters or its `author` longer than 200,
  or either has a line break or another control character;
- its `id` is already a built-in's;
- the test run fails: importing, `setup` with default options, and one
  `render` in a separate process must finish within 5 seconds and give a
  correctly sized image.

The install dialog lists these capabilities for the user to accept. They're
spotted from the source, in any of the widget's `.py` files:

| Listed as | Found by |
|---|---|
| runs other programs | importing `subprocess`, `pty` or `multiprocessing`; using `os.system`, `os.popen`, or any `os.exec…`, `os.spawn…` or `os.posix_spawn…`, also through `import os as x` or `from os import …` |
| uses the network | importing `socket`, `ssl`, `urllib`, `http`, `requests`, `httpx`, `aiohttp`, `websocket(s)`, `ftplib`, `smtplib` |
| loads native code | importing `ctypes` or `cffi` |
| talks to D-Bus | importing `dbus`, `gi`, `pydbus`, `jeepney`, `dbus_next` |
| runs code built at runtime | calling `eval`, `exec`, `compile` or `__import__`; importing `importlib` or `builtins`; mentioning `__builtins__` |
| uses the app's own code | importing anything from `StreamDock` (only `streamdock_sdk` is a stable API) |
| sees which window you focus, and its title | defining `on_window_focus` |

### Trying a widget without the app

With the app's Python environment active:

```sh
python -c "
from streamdock_sdk.loader import load_widget_class
from streamdock_sdk.options import resolve_options
from streamdock_sdk.scheduler import WidgetDriver
cls = load_widget_class('my_widget.py')
options, warnings = resolve_options(cls.options, {})
driver = WidgetDriver(cls, options)
driver.render_once().save('preview.png')
print('state:', driver.state, 'badge:', driver.badge)
"
```

To run the full install check without installing (this runs the widget):

```sh
python -c "
from StreamDock.widgets.validator import validate_widget
report = validate_widget('my_widget.py')
print(report.errors or 'OK', report.capabilities)
"
```

### How it runs

Built-in widgets run inside the app. A third-party widget runs as
`python -B -m streamdock_sdk.host widget.py`. It exchanges JSON lines with the
app: commands (`start`, `render_once`, `event`, `focus`, `show`, `hide`, `stop`) go to it on stdin,
and it sends back `ready`, `frame` (a base64 PNG), `state`, `badge` and
`error` on stdout. The app composes your images and the badge itself: a widget
never sees your image files, and with a base `icon` it isn't asked to draw.
Frames go to the device only for keys on the layout that is currently shown.
Identical frames are skipped, and each key gets at most four updates a second.
