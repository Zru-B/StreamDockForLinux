"""
Tests for the icon cache in image_helpers.pil_helper.
"""

import os
from unittest.mock import patch

from PIL import Image

from StreamDock.image_helpers import pil_helper

SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
       '<rect width="10" height="10" fill="red"/></svg>')


def test_svg_is_rasterised_once_and_in_memory(tmp_path):
    # Guards re-rasterising an SVG on every page switch, and PNG temp files in /tmp.
    path = tmp_path / "icon.svg"
    path.write_text(SVG)
    pil_helper._load_image_cached.cache_clear()

    with patch.object(pil_helper.cairosvg, "svg2png", wraps=pil_helper.cairosvg.svg2png) as svg2png:
        first, temp = pil_helper.load_image(str(path), target_size=(20, 20))
        second, _ = pil_helper.load_image(str(path), target_size=(20, 20))

    assert temp is None
    assert svg2png.call_count == 1
    assert svg2png.call_args.kwargs["write_to"] is None
    assert first.size == (20, 20)
    assert first is not second


def test_edited_file_is_reloaded(tmp_path):
    # Guards a stale icon after the user replaces the file in place.
    path = tmp_path / "icon.png"
    Image.new("RGB", (4, 4), "red").save(path)
    pil_helper._load_image_cached.cache_clear()
    assert pil_helper.load_image(str(path))[0].getpixel((0, 0)) == (255, 0, 0)

    Image.new("RGB", (4, 4), "blue").save(path)
    stat = os.stat(path)
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

    assert pil_helper.load_image(str(path))[0].getpixel((0, 0)) == (0, 0, 255)


def test_callers_cannot_mutate_the_cached_image(tmp_path):
    # Guards one key's drawing leaking onto every other key using the same icon.
    path = tmp_path / "icon.png"
    Image.new("RGB", (4, 4), "red").save(path)
    pil_helper._load_image_cached.cache_clear()

    pil_helper.load_image(str(path))[0].putpixel((0, 0), (0, 255, 0))

    assert pil_helper.load_image(str(path))[0].getpixel((0, 0)) == (255, 0, 0)
