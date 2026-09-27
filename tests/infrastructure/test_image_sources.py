"""
Picture sources for the lock-screen slideshow, and cutting a picture into key tiles.
"""

import json
import os
import random

import pytest
from PIL import Image

from StreamDock.business_logic.screensaver import ScreensaverConfig
from StreamDock.domain.device_geometry import (
    KEY_COLUMNS,
    KEY_GAP_PIXELS,
    KEY_PIXELS,
    KEY_ROWS,
    panel_size,
)
from StreamDock.image_helpers.pil_helper import tile_image
from StreamDock.infrastructure.image_sources import (
    FolderImageSource,
    OnlineImageSource,
    http_get,
    make_image_source,
)


def write_picture(path, color=(255, 0, 0), size=(40, 30)):
    Image.new('RGB', size, color).save(path)
    return path


def jpeg_bytes(color=(0, 0, 255), size=(50, 30)):
    import io
    buffer = io.BytesIO()
    Image.new('RGB', size, color).save(buffer, format='JPEG')
    return buffer.getvalue()


class TestTileImage:

    def test_fifteen_tiles_of_key_size(self):
        tiles = tile_image(Image.new('RGB', (1920, 1080)), 5, 3, (112, 112))

        assert len(tiles) == 15
        assert {tile.size for tile in tiles} == {(112, 112)}

    def test_tiles_run_row_by_row_from_the_top_left(self):
        # Guards key 1 being the top-left key: a transposed order would
        # scramble every picture on the deck.
        image = Image.new('RGB', (5, 3))
        for x in range(5):
            for y in range(3):
                image.putpixel((x, y), (x * 50, y * 100, 0))

        tiles = tile_image(image, 5, 3, (1, 1))

        assert tiles[1].getpixel((0, 0)) == (50, 0, 0)
        assert tiles[5].getpixel((0, 0)) == (0, 100, 0)
        assert tiles[14].getpixel((0, 0)) == (200, 200, 0)


class TestTilesFollowThePanel:
    """Each key shows the part of the picture under its own screen, not a squeezed neighbour."""

    def test_the_panel_is_the_measured_front_of_the_deck(self):
        # 5 screens of 13.5 mm and 4 gaps of 5.25 mm across, 3 and 2 down,
        # at 112 px per 13.5 mm.
        assert panel_size() == (734, 423)

    def test_the_gaps_are_cut_away(self):
        # A panel-sized picture with a marker at key 2's top-left corner:
        # without the gap it would sit in key 1.
        picture = Image.new('RGB', panel_size(), (0, 0, 0))
        left = round(KEY_PIXELS + KEY_GAP_PIXELS)
        picture.paste((255, 255, 255), (left, 0, left + 4, 4))

        tiles = tile_image(picture, KEY_COLUMNS, KEY_ROWS, (KEY_PIXELS, KEY_PIXELS),
                           gap=KEY_GAP_PIXELS)

        assert tiles[1].getpixel((1, 1)) == (255, 255, 255)
        assert tiles[0].getpixel((KEY_PIXELS - 1, 1)) == (0, 0, 0)

    def test_the_last_key_ends_at_the_panel_edge(self):
        # Rounding each offset from the start, not stepping, keeps the last
        # tile inside the picture instead of padding it.
        picture = Image.new('RGB', panel_size(), (0, 0, 0))
        picture.paste((255, 255, 255), (panel_size()[0] - 2, panel_size()[1] - 2) + panel_size())

        tiles = tile_image(picture, KEY_COLUMNS, KEY_ROWS, (KEY_PIXELS, KEY_PIXELS),
                           gap=KEY_GAP_PIXELS)

        assert tiles[14].getpixel((KEY_PIXELS - 1, KEY_PIXELS - 1)) == (255, 255, 255)


class TestFolderImageSource:

    def test_it_walks_subfolders_and_skips_other_files(self, tmp_path):
        write_picture(tmp_path / 'a.png')
        (tmp_path / 'sub').mkdir()
        write_picture(tmp_path / 'sub' / 'b.jpg')
        (tmp_path / 'notes.txt').write_text('not a picture')

        source = FolderImageSource(str(tmp_path), shuffle=False)

        assert source.next_image() is not None
        assert source.next_image() is not None
        # Third call starts a new pass rather than running dry.
        assert source.next_image() is not None

    def test_unreadable_pictures_are_skipped(self, tmp_path):
        (tmp_path / 'a-broken.jpg').write_bytes(b'not a jpeg')
        write_picture(tmp_path / 'b.png', color=(0, 255, 0))

        image = FolderImageSource(str(tmp_path), shuffle=False).next_image()

        assert image.convert('RGB').getpixel((0, 0)) == (0, 255, 0)

    def test_an_empty_or_missing_folder_gives_nothing(self, tmp_path):
        assert FolderImageSource(str(tmp_path)).next_image() is None
        assert FolderImageSource(str(tmp_path / 'missing')).next_image() is None

    def test_only_broken_files_do_not_spin(self, tmp_path):
        for name in ('a.jpg', 'b.jpg'):
            (tmp_path / name).write_bytes(b'junk')

        assert FolderImageSource(str(tmp_path)).next_image() is None

    def test_new_pictures_are_found_on_the_next_pass(self, tmp_path):
        write_picture(tmp_path / 'a.png')
        source = FolderImageSource(str(tmp_path), shuffle=False)
        source.next_image()
        write_picture(tmp_path / 'b.png', color=(0, 0, 255))

        colors = {source.next_image().getpixel((0, 0)) for _ in range(2)}

        assert (0, 0, 255) in colors


class FakeWeb:
    def __init__(self, routes):
        self.routes = routes
        self.requested = []

    def __call__(self, url):
        self.requested.append(url)
        response = self.routes(url) if callable(self.routes) else self.routes[url]
        if isinstance(response, Exception):
            raise response
        return response


class TestOnlineImageSource:

    def test_picsum_is_asked_for_the_grid_size_and_cached(self, tmp_path):
        web = FakeWeb(lambda url: (jpeg_bytes(), {'Picsum-ID': '42'}))
        source = OnlineImageSource('picsum', (560, 336), cache_dir=tmp_path, fetch=web)

        assert source.next_image() is not None
        assert web.requested == ['https://picsum.photos/560/336']
        assert os.listdir(tmp_path / 'picsum') == ['picsum-42-560x336.jpg']

    def test_a_failed_download_falls_back_to_the_cache(self, tmp_path):
        (tmp_path / 'picsum').mkdir()
        cached = tmp_path / 'picsum' / 'picsum-1.jpg'
        cached.write_bytes(jpeg_bytes(color=(0, 255, 0)))
        web = FakeWeb(lambda url: OSError("network down"))
        source = OnlineImageSource('picsum', (560, 336), cache_dir=tmp_path, fetch=web)

        image = source.next_image()

        assert image is not None
        r, g, b = image.convert('RGB').getpixel((10, 10))
        assert g > 200 and r < 50

    def test_no_network_and_no_cache_gives_nothing(self, tmp_path):
        web = FakeWeb(lambda url: OSError("network down"))
        source = OnlineImageSource('picsum', (560, 336), cache_dir=tmp_path, fetch=web)

        assert source.next_image() is None

    def test_the_cache_is_pruned(self, tmp_path):
        counter = iter(range(100))
        web = FakeWeb(lambda url: (jpeg_bytes(), {'Picsum-ID': str(next(counter))}))
        source = OnlineImageSource('picsum', (560, 336), cache_dir=tmp_path, fetch=web,
                                   max_cached=3)
        for _ in range(5):
            source.next_image()

        assert len(os.listdir(tmp_path / 'picsum')) == 3

    def test_a_download_that_is_not_a_picture_is_dropped(self, tmp_path):
        web = FakeWeb(lambda url: (b'<html>rate limited</html>', {'Picsum-ID': '7'}))
        source = OnlineImageSource('picsum', (560, 336), cache_dir=tmp_path, fetch=web)

        assert source.next_image() is None
        assert os.listdir(tmp_path / 'picsum') == []

    def test_bing_walks_the_archive_and_downloads_each_picture_once(self, tmp_path):
        archive = json.dumps({'images': [{'urlbase': '/th?id=OHR.One'},
                                         {'urlbase': '/th?id=OHR.Two'}]}).encode()

        def routes(url):
            if 'HPImageArchive' in url:
                return archive, {}
            return jpeg_bytes(), {}

        web = FakeWeb(routes)
        source = OnlineImageSource('bing', (560, 336), cache_dir=tmp_path, fetch=web)
        for _ in range(4):
            assert source.next_image() is not None

        downloads = [url for url in web.requested if 'HPImageArchive' not in url]
        assert downloads == ['https://www.bing.com/th?id=OHR.One_1280x720.jpg',
                             'https://www.bing.com/th?id=OHR.Two_1280x720.jpg']

    def test_a_garbled_bing_archive_falls_back_to_the_cache(self, tmp_path):
        web = FakeWeb(lambda url: (b'{not json', {}))
        source = OnlineImageSource('bing', (560, 336), cache_dir=tmp_path, fetch=web)

        assert source.next_image() is None

    def test_the_fallback_avoids_repeating_the_last_picture(self, tmp_path):
        (tmp_path / 'picsum').mkdir()
        for name in ('a.jpg', 'b.jpg'):
            (tmp_path / 'picsum' / name).write_bytes(jpeg_bytes())
        web = FakeWeb(lambda url: OSError("down"))
        source = OnlineImageSource('picsum', (560, 336), cache_dir=tmp_path, fetch=web,
                                   rng=random.Random(0))
        source.next_image()
        first = source._last_path
        source.next_image()

        assert source._last_path != first


class TestHttpGet:

    def test_plain_http_is_refused(self):
        with pytest.raises(ValueError):
            http_get('http://picsum.photos/10/10')


class TestMakeImageSource:

    def test_it_follows_the_configured_source(self, tmp_path):
        folder = make_image_source(ScreensaverConfig(source='folder', folder=str(tmp_path)),
                                   (560, 336))
        online = make_image_source(ScreensaverConfig(source='online', provider='bing'),
                                   (560, 336))

        assert isinstance(folder, FolderImageSource)
        assert isinstance(online, OnlineImageSource)
