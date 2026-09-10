"""
The remembered preferences.

QSettings is pointed at a scratch file so a test run never touches the
developer's own configuration.
"""

import pytest
from PyQt6.QtCore import QSettings

from StreamDock.ui import settings_store


@pytest.fixture(autouse=True)
def scratch_settings(tmp_path, monkeypatch):
    """Keep every read and write in a file of this test's own."""
    path = str(tmp_path / "streamdock.ini")
    monkeypatch.setattr(settings_store, '_settings',
                        lambda: QSettings(path, QSettings.Format.IniFormat))


class TestDesign:
    """Which interface design to wear."""

    def test_it_follows_the_desktop_until_told_otherwise(self):
        assert settings_store.get_design() == 'auto'

    @pytest.mark.parametrize('design', ['auto', 'kde', 'gnome'])
    def test_a_choice_survives(self, design):
        settings_store.set_design(design)

        assert settings_store.get_design() == design

    def test_a_value_nobody_understands_falls_back_to_following(self):
        """The settings file is a text file someone can edit by hand."""
        settings_store.set_design('aqua')

        assert settings_store.get_design() == 'auto'


class TestScheme:
    """Light or dark."""

    def test_it_follows_the_desktop_until_told_otherwise(self):
        assert settings_store.get_scheme() == 'auto'

    @pytest.mark.parametrize('scheme', ['auto', 'light', 'dark'])
    def test_a_choice_survives(self, scheme):
        settings_store.set_scheme(scheme)

        assert settings_store.get_scheme() == scheme

    def test_the_two_preferences_do_not_collide(self):
        settings_store.set_design('gnome')
        settings_store.set_scheme('light')

        assert settings_store.get_design() == 'gnome'
        assert settings_store.get_scheme() == 'light'
