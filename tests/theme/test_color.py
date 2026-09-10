"""
Colour arithmetic.

Pure functions, so these run without Qt and without a display.
"""

import pytest

from StreamDock.ui.theme import color


class TestParsing:
    """Every notation the desktops write colours in."""

    @pytest.mark.parametrize('text, expected', [
        ('#3DAEE9', (61, 174, 233)),
        ('#fff', (255, 255, 255)),
        ('61,174,233', (61, 174, 233)),
        (' 61 , 174 , 233 ', (61, 174, 233)),
    ])
    def test_it_reads_the_notation(self, text, expected):
        assert color.parse(text) == expected

    def test_it_drops_the_alpha_kde_sometimes_appends(self):
        assert color.parse('61,174,233,128') == (61, 174, 233)

    @pytest.mark.parametrize('text', ['', 'blue', '#12345', '1,2'])
    def test_it_refuses_what_is_not_a_colour(self, text):
        with pytest.raises(ValueError):
            color.parse(text)

    def test_out_of_range_channels_are_clamped(self):
        assert color.parse('300,-20,10') == (255, 0, 10)


class TestBlending:
    """mix, lighten, darken and shade."""

    def test_mixing_halfway_lands_in_the_middle(self):
        assert color.mix('#000000', '#FFFFFF', 0.5) == '#808080'

    @pytest.mark.parametrize('ratio', [-1.0, 0.0])
    def test_a_ratio_at_or_below_zero_gives_the_start(self, ratio):
        assert color.mix('#102030', '#FFFFFF', ratio) == '#102030'

    @pytest.mark.parametrize('ratio', [1.0, 2.0])
    def test_a_ratio_at_or_above_one_gives_the_end(self, ratio):
        assert color.mix('#102030', '#FFFFFF', ratio) == '#FFFFFF'

    def test_shade_lightens_a_dark_colour(self):
        assert color.luminance(color.shade('#202326', 0.2)) > color.luminance('#202326')

    def test_shade_darkens_a_light_one(self):
        assert color.luminance(color.shade('#EFF0F1', 0.2)) < color.luminance('#EFF0F1')


class TestLegibility:
    """Which foreground survives on a given background."""

    def test_white_on_a_dark_accent(self):
        assert color.readable_on('#3584E4') == '#FFFFFF'

    def test_dark_text_on_a_pale_accent(self):
        """A user can pick a yellow accent, and white on it is unreadable."""
        assert color.readable_on('#F6E58D') == '#1B1B1B'

    def test_rgba_carries_the_channels_and_the_alpha(self):
        assert color.rgba('#3DAEE9', 0.5) == 'rgba(61, 174, 233, 0.500)'
