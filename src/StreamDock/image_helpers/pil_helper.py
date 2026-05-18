import logging
import os
import tempfile

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

try:
    import cairosvg
    SVG_SUPPORT = True
except ImportError:
    SVG_SUPPORT = False


def convert_svg_to_png(svg_path, target_size=None):
    """
    Convert SVG file to PNG format.

    :param svg_path: Path to the SVG file
    :param target_size: Optional tuple (width, height) for the output PNG
    :return: Path to the temporary PNG file
    """
    if not SVG_SUPPORT:
        # Provide clear, highly visible error message
        error_msg = (
            "\n" + "="*80 + "\n"
            "⚠️  ERROR: SVG IMAGE SUPPORT NOT AVAILABLE\n"
            + "="*80 + "\n"
            "\nThe 'cairosvg' library is required for SVG image support.\n"
            "\n📋 SOLUTION:\n"
            "   Install it with:\n"
            "   pip install cairosvg\n"
            "\n   Or activate your virtual environment if you have one.\n"
            + "="*80 + "\n"
        )
        print(error_msg, flush=True)
        logger.error("SVG support disabled: cairosvg not found")
        raise RuntimeError(
            "SVG support requires cairosvg library. "
            "Install with: pip install cairosvg"
        )

    # Create a temporary PNG file
    temp_fd, temp_png_path = tempfile.mkstemp(suffix='.png', prefix='svg_converted_')
    os.close(temp_fd)

    try:
        # Convert SVG to PNG
        if target_size:
            cairosvg.svg2png(
                url=svg_path,
                write_to=temp_png_path,
                output_width=target_size[0],
                output_height=target_size[1]
            )
        else:
            cairosvg.svg2png(
                url=svg_path,
                write_to=temp_png_path
            )

        return temp_png_path
    except Exception as e:
        # Clean up temp file on error
        if os.path.exists(temp_png_path):
            os.remove(temp_png_path)

        # Provide clear error message
        error_msg = (
            "\n" + "="*80 + "\n"
            "⚠️  SVG CONVERSION FAILED\n"
            + "="*80 + "\n"
            f"\nCould not convert SVG file: {svg_path}\n"
            f"\nReason: {str(e)}\n"
            "\n📋 POSSIBLE SOLUTIONS:\n"
            "   1. Ensure cairosvg is installed: pip install cairosvg\n"
            "   2. Check that the SVG file is valid\n"
            "   3. Try using a PNG image instead\n"
            + "="*80 + "\n"
        )
        print(error_msg, flush=True)
        logger.error("SVG conversion failed for %s: %s", svg_path, e)
        raise RuntimeError(f"Failed to convert SVG to PNG: {e}") from e


# Cache for resolved font paths to avoid repeated filesystem hits
_font_path_cache: dict = {}


def _resolve_font(font_size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    """
    Resolve the best available TrueType font for text rendering.

    Results are cached per (font_size, bold) combination.

    :param font_size: Desired font size in pixels
    :param bold: If True, prefer bold variant
    :return: PIL ImageFont instance
    """
    cache_key = (font_size, bold)
    if cache_key in _font_path_cache:
        cached = _font_path_cache[cache_key]
        # Re-create the font object from the cached path with the correct size
        if cached is None:
            return ImageFont.load_default()
        try:
            return ImageFont.truetype(cached, font_size)
        except Exception:
            pass

    if bold:
        candidates = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            '/usr/share/fonts/TTF/DejaVuSans-Bold.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
            '/usr/share/fonts/liberation/LiberationSans-Bold.ttf',
            '/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf',
            '/System/Library/Fonts/Helvetica.ttc',
            'C:\\Windows\\Fonts\\arialbd.ttf',
        ]
    else:
        candidates = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/TTF/DejaVuSans.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
            '/usr/share/fonts/liberation/LiberationSans-Regular.ttf',
            '/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf',
            '/System/Library/Fonts/Helvetica.ttc',
            'C:\\Windows\\Fonts\\arial.ttf',
        ]

    for path in candidates:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, font_size)
                _font_path_cache[cache_key] = path
                return font
            except Exception:  # pylint: disable=broad-exception-caught
                continue

    # Fall back to PIL built-in default
    _font_path_cache[cache_key] = None
    logger.warning("No TrueType font found – falling back to PIL default font")
    return ImageFont.load_default()


def _wrap_and_draw_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    canvas_size: tuple,
    text_color: str,
    padding_fraction: float = 0.10,
    line_spacing: int = 4,
    y_offset_fraction: float = 0.0,
) -> None:
    """
    Wrap text and draw it centred on *draw*.

    :param draw: ImageDraw context
    :param text: Text string to render
    :param font: Font to use
    :param canvas_size: (width, height) of the canvas
    :param text_color: Text fill colour
    :param padding_fraction: Fraction of width to use as horizontal padding
    :param line_spacing: Extra pixels between lines
    :param y_offset_fraction: Shift the text block vertically by this fraction
                              of the canvas height (negative = up, positive = down)
    """
    width, height = canvas_size
    padding = int(width * padding_fraction)
    max_width = width - 2 * padding

    # --- Word-wrap ---
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        test = ' '.join(current + [word])
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(' '.join(current))
            current = [word]
    if current:
        lines.append(' '.join(current))

    if not lines:
        return

    # --- Measure each line ---
    line_heights: list[int] = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_heights.append(bbox[3] - bbox[1])

    total_text_height = sum(line_heights) + line_spacing * (len(lines) - 1)

    # --- Vertical start position (centred + optional offset) ---
    y = (height - total_text_height) // 2 + int(height * y_offset_fraction)

    # --- Draw lines ---
    for line, lh in zip(lines, line_heights):
        bbox = draw.textbbox((0, 0), line, font=font)
        lw = bbox[2] - bbox[0]
        x = (width - lw) // 2
        draw.text((x, y), line, fill=text_color, font=font)
        y += lh + line_spacing


def create_text_image(
    text: str,
    size: tuple = (112, 112),
    text_color: str = "white",
    background_color: str = "black",
    font_size: int = 20,
    bold: bool = True,
) -> 'Image.Image':
    """
    Create an image that contains centred, word-wrapped text.

    :param text: Text to display
    :param size: (width, height) of the resulting image
    :param text_color: Colour of the text
    :param background_color: Background fill colour
    :param font_size: Font size in pixels
    :param bold: Use bold variant when available
    :return: PIL Image object (RGB)
    """
    image = Image.new('RGB', size, background_color)
    draw = ImageDraw.Draw(image)
    font = _resolve_font(font_size, bold)
    _wrap_and_draw_text(draw, text, font, size, text_color)
    return image


def render_key_image(
    size: tuple = (112, 112),
    icon_path: str = '',
    text: str = '',
    text_color: str = 'white',
    background_color: str = 'black',
    font_size: int = 20,
    bold: bool = True,
    text_position: str = 'center',
    icon_padding_bottom: int = 0,
) -> 'Image.Image':
    """
    Render a complete key image supporting three modes:

    1. **Text-only** – ``icon_path`` is empty or missing; renders centred text
       on a solid background.
    2. **Icon-only** – ``text`` is empty; loads and scales the icon.
    3. **Icon + text overlay** – loads the icon, then draws the text label
       at the bottom of the image so both are visible.

    :param size: (width, height) in pixels for the key image
    :param icon_path: Absolute path to an image/SVG file, or empty string
    :param text: Label string to render, or empty string
    :param text_color: Font colour (name or hex)
    :param background_color: Background/fill colour used for text-only mode
                             and as the canvas background for icon mode
    :param font_size: Font size in pixels
    :param bold: Use bold font variant when available
    :param text_position: Where to draw the text when both icon and text are
                          present.  Accepted values: ``'bottom'`` (default
                          when icon present), ``'top'``, ``'center'``.
    :param icon_padding_bottom: Extra pixels to shift the icon upward when
                                text is overlaid at the bottom (default 0 –
                                auto-calculated).
    :return: PIL Image object (RGB)
    """
    width, height = size
    has_icon = bool(icon_path)
    has_text = bool(text and text.strip())

    # ---- Text-only mode ----
    if not has_icon:
        return create_text_image(
            text=text if has_text else '',
            size=size,
            text_color=text_color,
            background_color=background_color,
            font_size=font_size,
            bold=bold,
        )

    # ---- Load icon ----
    temp_file = None
    try:
        img, temp_file = load_image(icon_path, target_size=size)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.error("render_key_image: cannot load icon '%s': %s", icon_path, exc)
        # Fall back to text-only if icon fails
        return create_text_image(
            text=text if has_text else icon_path,
            size=size,
            text_color=text_color,
            background_color=background_color,
            font_size=font_size,
            bold=bold,
        )
    finally:
        # We'll clean up the temp file after we've used the image
        pass

    try:
        # Scale icon to fill the canvas
        canvas = Image.new('RGB', size, background_color)
        icon = img.convert('RGBA')
        icon.thumbnail(size, Image.LANCZOS)
        ix = (width - icon.width) // 2
        iy = (height - icon.height) // 2
        canvas.paste(icon, (ix, iy), icon)

        # ---- Icon-only mode ----
        if not has_text:
            return canvas

        # ---- Icon + text overlay mode ----
        font = _resolve_font(font_size, bold)
        draw = ImageDraw.Draw(canvas)

        # Determine text position
        if text_position == 'top':
            y_offset = -0.35
        elif text_position == 'center':
            y_offset = 0.0
        else:  # 'bottom' (default for icon+text)
            y_offset = 0.35

        _wrap_and_draw_text(
            draw=draw,
            text=text,
            font=font,
            canvas_size=size,
            text_color=text_color,
            y_offset_fraction=y_offset,
        )
        return canvas
    finally:
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass


def load_image(image_path, target_size=None):
    """
    Load an image from path, with automatic SVG to PNG conversion.

    :param image_path: Path to the image file (supports PNG, JPG, GIF, SVG, etc.)
    :param target_size: Optional tuple (width, height) for SVG rendering
    :return: Tuple of (PIL.Image object, temporary_file_path or None)
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    # Check if file is SVG
    _, ext = os.path.splitext(image_path)
    is_svg = ext.lower() in ['.svg', '.svgz']

    temp_file = None

    if is_svg:
        # Convert SVG to PNG
        temp_file = convert_svg_to_png(image_path, target_size)
        image = Image.open(temp_file)
    else:
        # Load image directly
        image = Image.open(image_path)

    return image, temp_file


def _create_image(image_format, background):
    return Image.new("RGB", image_format['size'], background)


def _scale_image(image, image_format, margins=[0, 0, 0, 0], background='black'):
    if len(margins) != 4:
        raise ValueError("Margins should be given as an array of four integers.")

    final_image = _create_image(image_format, background=background)

    thumbnail_max_width = final_image.width - (margins[1] + margins[3])
    thumbnail_max_height = final_image.height - (margins[0] + margins[2])

    thumbnail = image.convert("RGBA")
    thumbnail.thumbnail((thumbnail_max_width, thumbnail_max_height), Image.LANCZOS)

    thumbnail_x = margins[3] + (thumbnail_max_width - thumbnail.width) // 2
    thumbnail_y = margins[0] + (thumbnail_max_height - thumbnail.height) // 2

    final_image.paste(thumbnail, (thumbnail_x, thumbnail_y), thumbnail)

    return final_image


def _to_native_format(image, image_format):
    if image_format["format"].lower() != "jpeg" and image_format["format"].lower() != "jpg":
        raise ValueError(f"no support format: {image_format['format']}. only 'jpeg' or 'jpg' is supported")

    _expand = True
    if image.size[1] == image_format["size"][0] and image.size[0] == image_format["size"][1]:
        _expand = False

    # must rotate the picture first then resize the picture
    if image_format["rotation"] == 90 or image_format["rotation"] == -90:
        swapped_tuple = (image_format["size"][1], image_format["size"][0])
        image_format["size"] = swapped_tuple

    if image_format['rotation']:
        image = image.rotate(image_format['rotation'], expand = _expand)

    if image.size != image_format['size']:
        image = image.resize(image_format["size"])

    if image_format['flip'][0]:
        image = image.transpose(Image.FLIP_LEFT_RIGHT)

    if image_format['flip'][1]:
        image = image.transpose(Image.FLIP_TOP_BOTTOM)

    image = image.convert('RGB')

    return image


def create_image(dock, background='black'):
    return create_key_image(dock, background)


def create_key_image(dock, background='black'):
    return _create_image(dock.key_image_format(), background)


def create_touchscreen_image(dock, background='black'):
    return _create_image(dock.touchscreen_image_format(), background)


def create_scaled_image(dock, image, margins=None, background='black'):
    if margins is None:
        margins = [0, 0, 0, 0]
    return create_scaled_key_image(dock, image, margins, background)


def create_scaled_key_image(dock, image, margins=None, background='black'):
    if margins is None:
        margins = [0, 0, 0, 0]
    return _scale_image(image, dock.key_image_format(), margins, background)


def create_scaled_touchscreen_image(dock, image, margins=None, background='black'):
    if margins is None:
        margins = [0, 0, 0, 0]
    return _scale_image(image, dock.touchscreen_image_format(), margins, background)

def to_native_key_format(dock, image):
    return _to_native_format(image, dock.key_image_format())

def to_native_seondscreen_format(dock, image):
    return _to_native_format(image, dock.secondscreen_image_format())

def to_native_touchscreen_format(dock, image):
    return _to_native_format(image, dock.touchscreen_image_format())
