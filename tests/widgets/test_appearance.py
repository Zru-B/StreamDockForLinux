"""Composing a widget key from the user's images, the widget's state and its badge."""

import pytest
from PIL import Image

from StreamDock.widgets.appearance import Appearance, BadgeStyle, compose

SIZE = (112, 112)


@pytest.fixture
def images(tmp_path):
    paths = {}
    for name, color in (('base', 'blue'), ('on', 'green')):
        paths[name] = str(tmp_path / f'{name}.png')
        Image.new('RGB', SIZE, color).save(paths[name])
    return paths


def test_state_image_then_base_image_then_drawing(images):
    drawn = Image.new('RGB', SIZE, 'red')
    with_base = Appearance(icon=images['base'], state_icons=(('on', images['on']),))
    without_base = Appearance(state_icons=(('on', images['on']),))

    assert compose(with_base, 'on', None, drawn, SIZE).getpixel((56, 56)) == (0, 128, 0)
    assert compose(with_base, 'off', None, drawn, SIZE).getpixel((56, 56)) == (0, 0, 255)
    assert compose(without_base, 'off', None, drawn, SIZE) is drawn
    assert compose(without_base, 'off', None, None, SIZE) is None


@pytest.mark.parametrize('position, corner, far', [
    ('top_right', (100, 14), (10, 100)),
    ('top_left', (12, 14), (100, 100)),
    ('bottom_right', (100, 98), (10, 10)),
    ('bottom_left', (12, 98), (100, 10)),
])
def test_badge_lands_in_its_corner(images, position, corner, far):
    shown = compose(Appearance(icon=images['base'], badge=BadgeStyle(position, color='#ffff00')),
                    None, '7', None, SIZE)
    assert shown.getpixel(corner)[:2] == (255, 255)
    assert shown.getpixel(far) == (0, 0, 255)


def test_badge_is_not_drawn_over_the_widgets_own_drawing():
    # The widget draws its own count; a second one on top would double it.
    drawn = Image.new('RGB', SIZE, 'red')
    assert compose(Appearance(), None, '7', drawn, SIZE) is drawn


def test_missing_image_falls_back_to_the_drawing(tmp_path):
    drawn = Image.new('RGB', SIZE, 'red')
    assert compose(Appearance(icon=str(tmp_path / 'gone.png')), None, None, drawn, SIZE) is drawn


def test_config_paths_resolve_against_the_config_folder(tmp_path):
    appearance = Appearance.from_key_config(
        {'icon': 'img/base.png', 'state_icons': {'on': 'img/on.png'}, 'badge': False}, str(tmp_path))
    assert appearance.icon == str(tmp_path / 'img' / 'base.png')
    assert appearance.image_for('on') == str(tmp_path / 'img' / 'on.png')
    assert appearance.badge is None
    assert Appearance.from_key_config({}).badge == BadgeStyle()
