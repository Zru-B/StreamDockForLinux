"""
Naming the desktop's icons.

The icon theme is faked rather than read, so the same answers come back with
and without Breeze installed.
"""

import pytest
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QStyle

from StreamDock.ui.theme import icons
from StreamDock.ui.theme.detection import Scheme


def real_icon() -> QIcon:
    """An icon that is not null."""
    pixmap = QPixmap(4, 4)
    pixmap.fill()
    return QIcon(pixmap)


@pytest.fixture
def theme_with(monkeypatch):
    """Pretend the icon theme holds exactly these names."""
    def install(*available):
        def from_theme(name):
            return real_icon() if name in available else QIcon()
        monkeypatch.setattr(icons.QIcon, 'fromTheme', staticmethod(from_theme))
    return install


class TestThemedIcon:
    """themed_icon() takes the first name the theme can supply."""

    def test_the_first_available_name_wins(self, qapp, theme_with):
        theme_with('list-add-symbolic')

        assert not icons.themed_icon('list-add', 'list-add-symbolic').isNull()

    def test_nothing_available_gives_an_empty_icon(self, qapp, theme_with):
        theme_with()

        assert icons.themed_icon('list-add').isNull()

    def test_the_fallback_is_used_when_nothing_resolves(self, qapp, theme_with):
        theme_with()
        fallback = real_icon()

        assert icons.themed_icon('list-add', fallback=fallback) is fallback


class TestButtonIcons:
    """The icon KDE puts on a dialog button, by its label."""

    @pytest.mark.parametrize('label, expected', [
        ('Save', 'document-save'),
        ('&Save', 'document-save'),
        ('OK', 'dialog-ok'),
        ('Cancel', 'dialog-cancel'),
        ('Close', 'dialog-close'),
        ('Select Icon...', 'insert-image'),
        ('Browse...', 'document-open'),
        ('Add Action', 'list-add'),
    ])
    def test_standard_labels_get_their_icon(self, qapp, monkeypatch, label, expected):
        asked = []
        monkeypatch.setattr(icons, 'themed_icon',
                            lambda *names, fallback=None: asked.append(names) or real_icon())

        assert not icons.button_icon(label).isNull()
        assert asked[0][0] == expected

    def test_an_unknown_label_gets_none(self, qapp, theme_with):
        theme_with('dialog-ok')

        assert icons.button_icon('Frobnicate').isNull()


class TestStandardIcons:
    """Qt's standard pictures, redirected to the theme."""

    def test_a_message_box_question_comes_from_the_theme(self, qapp, theme_with):
        theme_with('dialog-question')

        assert not icons.standard_icon(QStyle.StandardPixmap.SP_MessageBoxQuestion).isNull()

    def test_a_picture_the_theme_lacks_is_left_to_qt(self, qapp, theme_with):
        theme_with()

        assert icons.standard_icon(QStyle.StandardPixmap.SP_MessageBoxQuestion).isNull()


class TestEnsuringATheme:
    """ensure_icon_theme() fills in what Qt could not find."""

    @pytest.fixture
    def icon_theme(self, monkeypatch):
        state = {'name': '', 'fallback': '', 'paths': []}
        monkeypatch.setattr(icons.QIcon, 'themeName', staticmethod(lambda: state['name']))
        monkeypatch.setattr(icons.QIcon, 'setThemeName',
                            staticmethod(lambda name: state.update(name=name)))
        monkeypatch.setattr(icons.QIcon, 'fallbackThemeName',
                            staticmethod(lambda: state['fallback']))
        monkeypatch.setattr(icons.QIcon, 'setFallbackThemeName',
                            staticmethod(lambda name: state.update(fallback=name)))
        monkeypatch.setattr(icons.QIcon, 'themeSearchPaths', staticmethod(lambda: []))
        monkeypatch.setattr(icons.QIcon, 'setThemeSearchPaths',
                            staticmethod(lambda paths: state.update(paths=list(paths))))
        monkeypatch.setattr(icons, 'icon_theme_directories', lambda: ['/icons'])
        monkeypatch.setattr(icons, 'read_kde_icon_theme', lambda: '')
        return state

    def test_no_theme_at_all_gets_breeze_for_the_scheme(self, qapp, icon_theme):
        assert icons.ensure_icon_theme(Scheme.DARK) == 'breeze-dark'
        assert icon_theme['name'] == 'breeze-dark'
        assert icon_theme['fallback'] == 'breeze'
        assert '/icons' in icon_theme['paths']

    def test_the_configured_theme_is_preferred(self, qapp, icon_theme, monkeypatch):
        monkeypatch.setattr(icons, 'read_kde_icon_theme', lambda: 'Papirus-Dark')

        assert icons.ensure_icon_theme(Scheme.DARK) == 'Papirus-Dark'

    def test_a_theme_qt_found_is_left_alone(self, qapp, icon_theme):
        icon_theme['name'] = 'Papirus'

        assert icons.ensure_icon_theme(Scheme.LIGHT) == 'Papirus'
        assert icon_theme['paths'] == []

    def test_breeze_is_matched_to_the_scheme(self, qapp, icon_theme):
        """Dark Breeze icons are white, which vanishes on a light window."""
        icon_theme['name'] = 'breeze-dark'

        assert icons.ensure_icon_theme(Scheme.LIGHT) == 'breeze'
        assert icon_theme['name'] == 'breeze'
