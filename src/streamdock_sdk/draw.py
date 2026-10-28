"""Drawing helpers so widgets match the look of ordinary text keys."""

from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from StreamDock.image_helpers.pil_helper import _resolve_font

DEFAULT_SIZE = (112, 112)


def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    """The TrueType font text keys use, at ``size`` pixels."""
    return _resolve_font(size, bold)


def canvas(size: Tuple[int, int] = DEFAULT_SIZE, background: str = 'black') -> Tuple[Image.Image, ImageDraw.ImageDraw]:
    """A blank key image and a drawing context for it."""
    image = Image.new('RGB', tuple(size), background)
    return image, ImageDraw.Draw(image)


def fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, max_height: int,
             start: int = 64, bold: bool = True, minimum: int = 8) -> ImageFont.FreeTypeFont:
    """The largest font, from ``start`` down, that fits ``text`` in the box."""
    for size in range(start, minimum - 1, -2):
        candidate = font(size, bold)
        left, top, right, bottom = draw.multiline_textbbox((0, 0), text, font=candidate, align='center')
        if right - left <= max_width and bottom - top <= max_height:
            return candidate
    return font(minimum, bold)


def centered_text(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], text: str,
                  color: str = 'white', text_font: Optional[ImageFont.FreeTypeFont] = None,
                  bold: bool = True) -> None:
    """Draw ``text`` centred in ``box`` (left, top, right, bottom), shrinking it to fit."""
    left, top, right, bottom = box
    width, height = int(right - left), int(bottom - top)
    text_font = text_font or fit_font(draw, text, width, height, start=height, bold=bold)
    draw.multiline_text((left + width / 2, top + height / 2), text, fill=color,
                        font=text_font, anchor='mm', align='center')


def text_key(text: str, color: str = 'white', background: str = 'black',
             size: Tuple[int, int] = DEFAULT_SIZE, bold: bool = True, padding: int = 8) -> Image.Image:
    """A whole key showing ``text`` as large as it fits."""
    image, draw = canvas(size, background)
    centered_text(draw, (padding, padding, size[0] - padding, size[1] - padding), text, color, bold=bold)
    return image


def wrap(draw: ImageDraw.ImageDraw, text: str, text_font: ImageFont.FreeTypeFont,
         max_width: int, max_lines: int) -> list:
    """Word-wrap ``text`` into at most ``max_lines`` lines, ending in '…' if it doesn't fit."""
    def width(candidate: str) -> float:
        return draw.textlength(candidate, font=text_font)

    lines: list = []
    words = text.split()
    while words and len(lines) < max_lines:
        line = words.pop(0)
        while width(line) > max_width and len(line) > 1:
            # One word wider than the key: break it.
            cut = len(line) - 1
            while cut > 1 and width(line[:cut]) > max_width:
                cut -= 1
            words.insert(0, line[cut:])
            line = line[:cut]
        while words and width(f'{line} {words[0]}') <= max_width:
            line = f'{line} {words.pop(0)}'
        lines.append(line)
    if words and lines:
        last = lines[-1]
        while last and width(last + '…') > max_width:
            last = last[:-1]
        lines[-1] = last.rstrip() + '…'
    return lines
