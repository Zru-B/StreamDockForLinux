"""
Working out which desktop is running and what it looks like.

The environment is faked rather than read, so the same answers come back on a
developer's Plasma session and in a headless CI container.
"""

import subprocess

import pytest

from StreamDock.ui.theme import detection
from StreamDock.ui.theme.detection import Flavor, Scheme

DESKTOP_VARIABLES = ('XDG_CURRENT_DESKTOP', 'XDG_SESSION_DESKTOP',
                     'DESKTOP_SESSION', 'KDE_FULL_SESSION',
                     'GNOME_DESKTOP_SESSION_ID')


@pytest.fixture
def bare_session(monkeypatch):
    """A session that claims to be nothing in particular."""
    for name in DESKTOP_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


class TestFlavorDetection:
    """detect_flavor()."""

    @pytest.mark.parametrize('value, expected', [
        ('KDE', Flavor.KDE),
        ('plasma', Flavor.KDE),
        ('LXQt', Flavor.KDE),
        ('GNOME', Flavor.GNOME),
        ('ubuntu:GNOME', Flavor.GNOME),
        ('X-Cinnamon', Flavor.GNOME),
        ('XFCE', Flavor.GNOME),
    ])
    def test_it_reads_the_current_desktop(self, bare_session, value, expected):
        bare_session.setenv('XDG_CURRENT_DESKTOP', value)

        assert detection.detect_flavor() is expected

    def test_a_session_path_is_reduced_to_its_name(self, bare_session):
        """DESKTOP_SESSION is a path to a .desktop file on some distributions."""
        bare_session.setenv('DESKTOP_SESSION',
                            '/usr/share/wayland-sessions/plasma.desktop')

        assert detection.detect_flavor() is Flavor.KDE

    def test_the_first_recognised_name_wins(self, bare_session):
        bare_session.setenv('XDG_CURRENT_DESKTOP', 'GNOME')
        bare_session.setenv('DESKTOP_SESSION', 'plasma')

        assert detection.detect_flavor() is Flavor.GNOME

    def test_it_falls_back_to_the_legacy_kde_marker(self, bare_session):
        bare_session.setenv('KDE_FULL_SESSION', 'true')

        assert detection.detect_flavor() is Flavor.KDE

    def test_an_unknown_session_gets_the_qt_design(self, bare_session):
        """This is a Qt application; Breeze is the safer guess."""
        bare_session.setenv('XDG_CURRENT_DESKTOP', 'awesome')

        assert detection.detect_flavor() is detection.DEFAULT_FLAVOR


class TestKdeColors:
    """read_kde_colors()."""

    def write_kdeglobals(self, tmp_path, monkeypatch, body):
        monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
        (tmp_path / 'kdeglobals').write_text(body, encoding='utf-8')

    def test_it_reads_the_scheme_the_user_chose(self, tmp_path, monkeypatch):
        self.write_kdeglobals(tmp_path, monkeypatch, """
[Colors:Window]
BackgroundNormal=32,35,38
ForegroundNormal=252,252,252

[Colors:Selection]
BackgroundNormal=61,174,233
""")

        colors = detection.read_kde_colors()

        assert colors['window_bg'] == '#202326'
        assert colors['window_fg'] == '#FCFCFC'
        assert colors['selection_bg'] == '#3DAEE9'

    def test_an_explicit_accent_is_reported(self, tmp_path, monkeypatch):
        self.write_kdeglobals(tmp_path, monkeypatch, """
[General]
AccentColor=146,74,255
""")

        assert detection.read_kde_colors()['accent'] == '#924AFF'

    def test_repeated_sections_do_not_stop_the_read(self, tmp_path, monkeypatch):
        """Plasma writes per-state variants of the same section."""
        self.write_kdeglobals(tmp_path, monkeypatch, """
[Colors:Header]
BackgroundNormal=41,44,48

[Colors:Header][Inactive]
BackgroundNormal=32,35,38

[Colors:Window]
BackgroundNormal=32,35,38
""")

        assert detection.read_kde_colors()['header_bg'] == '#292C30'

    def test_a_malformed_colour_is_skipped_not_fatal(self, tmp_path, monkeypatch):
        self.write_kdeglobals(tmp_path, monkeypatch, """
[Colors:Window]
BackgroundNormal=not a colour
ForegroundNormal=252,252,252
""")

        colors = detection.read_kde_colors()

        assert 'window_bg' not in colors
        assert colors['window_fg'] == '#FCFCFC'

    def test_no_file_means_no_colours(self, tmp_path, monkeypatch):
        monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))

        assert detection.read_kde_colors() == {}


class TestGnomeSettings:
    """What GSettings is asked, and what happens when it is not there."""

    def test_the_accent_name_becomes_a_colour(self, monkeypatch):
        monkeypatch.setattr(detection, 'read_gnome_setting',
                            lambda key, **kwargs: 'purple')

        assert detection.read_gnome_accent() == '#9141AC'

    def test_an_unknown_accent_leaves_adwaita_blue_alone(self, monkeypatch):
        monkeypatch.setattr(detection, 'read_gnome_setting',
                            lambda key, **kwargs: 'chartreuse')

        assert detection.read_gnome_accent() is None

    def test_quoting_is_stripped_from_the_value(self, monkeypatch):
        monkeypatch.setattr(detection.shutil, 'which', lambda _name: '/usr/bin/gsettings')
        monkeypatch.setattr(
            detection.subprocess, 'run',
            lambda *a, **k: subprocess.CompletedProcess(a, 0, "'prefer-dark'\n", ''))

        assert detection.read_gnome_setting('color-scheme') == 'prefer-dark'

    def test_a_missing_gsettings_is_not_an_error(self, monkeypatch):
        monkeypatch.setattr(detection.shutil, 'which', lambda _name: None)

        assert detection.read_gnome_setting('color-scheme') == ''

    def test_a_hanging_gsettings_is_not_an_error(self, monkeypatch):
        def timeout(*_args, **_kwargs):
            raise subprocess.TimeoutExpired('gsettings', 1.5)

        monkeypatch.setattr(detection.shutil, 'which', lambda _name: '/usr/bin/gsettings')
        monkeypatch.setattr(detection.subprocess, 'run', timeout)

        assert detection.read_gnome_setting('color-scheme') == ''


class TestSchemeDetection:
    """detect_scheme()."""

    @pytest.fixture(autouse=True)
    def no_qt_opinion(self, monkeypatch):
        """Qt answers first when it can; these tests are about the fallbacks."""
        monkeypatch.setattr(detection, '_scheme_from_qt', lambda: None)

    def test_qt_is_believed_when_it_has_an_answer(self, monkeypatch):
        monkeypatch.setattr(detection, '_scheme_from_qt', lambda: Scheme.LIGHT)

        assert detection.detect_scheme(Flavor.KDE) is Scheme.LIGHT

    def test_a_light_kde_scheme_is_recognised(self, monkeypatch):
        monkeypatch.setattr(detection, 'read_kde_colors',
                            lambda: {'window_bg': '#EFF0F1'})

        assert detection.detect_scheme(Flavor.KDE) is Scheme.LIGHT

    def test_a_dark_kde_scheme_is_recognised(self, monkeypatch):
        monkeypatch.setattr(detection, 'read_kde_colors',
                            lambda: {'window_bg': '#202326'})

        assert detection.detect_scheme(Flavor.KDE) is Scheme.DARK

    def test_gnome_is_asked_through_gsettings(self, monkeypatch):
        monkeypatch.setattr(detection, 'read_gnome_setting',
                            lambda key, **kwargs: 'prefer-dark')

        assert detection.detect_scheme(Flavor.GNOME) is Scheme.DARK

    def test_an_unreadable_session_keeps_the_dark_look_it_shipped_with(
            self, monkeypatch):
        monkeypatch.setattr(detection, 'read_kde_colors', dict)
        monkeypatch.setattr(detection, 'read_gnome_setting', lambda key, **kwargs: '')

        assert detection.detect_scheme(Flavor.GNOME) is Scheme.DARK


@pytest.fixture
def kde_config(tmp_path, monkeypatch):
    """A scratch XDG_CONFIG_HOME with a kdeglobals and the theme's defaults."""
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path))
    (tmp_path / 'kdedefaults').mkdir()

    def write(kdeglobals: str = '', kdedefaults: str = ''):
        if kdeglobals:
            (tmp_path / 'kdeglobals').write_text(kdeglobals, encoding='utf-8')
        if kdedefaults:
            (tmp_path / 'kdedefaults' / 'kdeglobals').write_text(kdedefaults, encoding='utf-8')
    return write


class TestKdeSettings:
    """The odds and ends read from kdeglobals beyond the colours."""

    def test_the_users_file_beats_the_themes_defaults(self, kde_config):
        kde_config(kdeglobals='[Icons]\nTheme=Papirus\n',
                   kdedefaults='[Icons]\nTheme=breeze-dark\n')

        assert detection.read_kde_icon_theme() == 'Papirus'

    def test_the_themes_defaults_fill_in_what_the_user_left(self, kde_config):
        kde_config(kdeglobals='[General]\nColorSchemeHash=abc\n',
                   kdedefaults='[Icons]\nTheme=breeze-dark\n')

        assert detection.read_kde_icon_theme() == 'breeze-dark'

    def test_nothing_configured_reads_as_empty(self, kde_config):
        assert detection.read_kde_icon_theme() == ''
        assert detection.read_kde_font() == ''

    def test_the_interface_font_comes_back_verbatim(self, kde_config):
        kde_config(kdeglobals='[General]\nfont=Noto Sans,11,-1,5,400,0,0,0,0,0,0,0,0,0,0,1\n')

        assert detection.read_kde_font().startswith('Noto Sans,11')

    def test_the_inactive_header_colour_is_read(self, kde_config):
        kde_config(kdeglobals='[Colors:Header]\nBackgroundNormal=41,44,48\n\n'
                              '[Colors:Header][Inactive]\nBackgroundNormal=32,35,38\n')

        colors = detection.read_kde_colors()

        assert colors['header_bg'] == '#292C30'
        assert colors['header_bg_inactive'] == '#202326'

    @pytest.mark.parametrize('raw, expected', [
        ('0.3', 0.3), ('', 0.2), ('banana', 0.2), ('7', 0.2),
    ])
    def test_the_frame_contrast_is_sane(self, kde_config, raw, expected):
        kde_config(kdeglobals=f'[KDE]\nframeContrast={raw}\n')

        assert detection.read_kde_frame_contrast() == pytest.approx(expected)


class TestPlasmaSession:
    """is_plasma_session() - Plasma itself, not merely a Qt desktop."""

    def test_plasma_reports_itself(self, bare_session):
        bare_session.setenv('XDG_CURRENT_DESKTOP', 'KDE')

        assert detection.is_plasma_session() is True

    def test_the_legacy_marker_counts(self, bare_session):
        bare_session.setenv('KDE_FULL_SESSION', 'true')

        assert detection.is_plasma_session() is True

    def test_another_qt_desktop_does_not(self, bare_session):
        bare_session.setenv('XDG_CURRENT_DESKTOP', 'LXQt')

        assert detection.detect_flavor() is Flavor.KDE
        assert detection.is_plasma_session() is False

    def test_a_bare_session_does_not(self, bare_session):
        assert detection.is_plasma_session() is False
