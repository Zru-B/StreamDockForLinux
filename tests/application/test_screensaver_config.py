"""
settings.screensaver through the runtime parser and the editor's document.
"""

import os

import pytest
import yaml

from StreamDock.application.config_document import ConfigDocument
from StreamDock.application.configuration_manager import (
    ConfigurationManager,
    ConfigValidationError,
)

BASE = {
    'keys': {'K': {'text': 'k', 'on_press_actions': [{'WAIT': 1}]}},
    'layouts': {'Main': {'Default': True, 'keys': [{1: 'K'}]}},
}


def parse(settings, path='/configs/config.yml'):
    return ConfigurationManager.parse_data(dict(BASE, settings=settings), path)


class TestRuntimeConfig:

    def test_absent_means_disabled(self):
        assert parse({}).screensaver.enabled is False

    def test_a_relative_folder_resolves_against_the_config(self):
        config = parse({'screensaver': {'enabled': True, 'folder': 'wallpapers'}})

        assert config.screensaver.folder == os.path.abspath('/configs/wallpapers')

    def test_online_needs_no_folder(self):
        config = parse({'screensaver': {'enabled': True, 'source': 'online',
                                        'provider': 'bing', 'interval': 30,
                                        'turn_off_after': 20}})

        assert (config.screensaver.provider, config.screensaver.interval,
                config.screensaver.turn_off_after) == ('bing', 30.0, 20.0)

    def test_an_invalid_section_is_refused(self):
        with pytest.raises(ConfigValidationError, match='interval'):
            parse({'screensaver': {'interval': 0.5}})


class TestDocument:

    def load(self, tmp_path, settings):
        path = tmp_path / 'config.yml'
        path.write_text(yaml.safe_dump({'streamdock': dict(BASE, settings=settings)}))
        return ConfigDocument.load(str(path)), path

    def test_an_untouched_document_writes_no_screensaver(self, tmp_path):
        document, path = self.load(tmp_path, {'brightness': 40})
        document.save()

        assert 'screensaver' not in yaml.safe_load(path.read_text())['streamdock']['settings']

    def test_it_round_trips_what_was_written_and_unknown_fields(self, tmp_path):
        section = {'enabled': True, 'folder': 'pics', 'interval': 7.5, 'brightness': 30,
                   'future': 1}
        document, path = self.load(tmp_path, {'screensaver': section})
        document.save()

        assert yaml.safe_load(path.read_text())['streamdock']['settings']['screensaver'] \
            == section

    def test_update_reports_a_change_only_when_there_is_one(self, tmp_path):
        document, _ = self.load(tmp_path, {})
        screensaver = document.settings.screensaver

        assert not screensaver.update({'enabled': False, 'interval': 10})
        assert screensaver.update({'enabled': True, 'source': 'online'})
        assert document.settings.to_dict()['screensaver'] == {'enabled': True,
                                                              'source': 'online'}

    def test_save_as_keeps_a_relative_folder_pointing_at_the_same_place(self, tmp_path):
        (tmp_path / 'pics').mkdir()
        document, _ = self.load(tmp_path, {'screensaver': {'enabled': True, 'folder': 'pics'}})
        (tmp_path / 'elsewhere').mkdir()
        document.save(str(tmp_path / 'elsewhere' / 'config.yml'))

        folder = document.settings.screensaver.folder
        assert os.path.normpath(os.path.join(document.config_dir, folder)) \
            == str(tmp_path / 'pics')
