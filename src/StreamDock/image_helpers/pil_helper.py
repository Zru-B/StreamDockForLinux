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
        logger.warning("SVG support disabled: cairosvg not found")
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
        logger.error(f"SVG conversion failed for {svg_path}: {e}")
        raise RuntimeError(f"Failed to convert SVG to PNG: {e}")


def create_text_image(text, size=(112, 112), text_color="white", background_color="black", font_size=20, bold=True):
    """
    Create an image from text with automatic wrapping and sizing.
    
    :param text: Text to display
    :param size: Tuple (width, height) for the image
    :param text_color: Color of the text (name or hex)
    :param background_color: Color of the background (name or hex)
    :param font_size: Font size in pixels (default: 20)
    :param bold: Use bold font (default: True)
    :return: PIL.Image object
    """
    # Create image with background color
    image = Image.new('RGB', size, background_color)
    draw = ImageDraw.Draw(image)
    
    # Try to load font
    font = None
    
    # Choose font paths based on bold setting
    if bold:
        font_paths = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
            '/usr/share/fonts/TTF/DejaVuSans-Bold.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
            '/usr/share/fonts/liberation/LiberationSans-Bold.ttf',
            '/System/Library/Fonts/Helvetica.ttc',
            'C:\\Windows\\Fonts\\arialbd.ttf',
        ]
    else:
        font_paths = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/TTF/DejaVuSans.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
            '/usr/share/fonts/liberation/LiberationSans-Regular.ttf',
            '/System/Library/Fonts/Helvetica.ttc',
            'C:\\Windows\\Fonts\\arial.ttf',
        ]
    
    for font_path in font_paths:
        if os.path.exists(font_path):
            try:
                font = ImageFont.truetype(font_path, font_size)
                break
            except:
                continue
    
    # Fall back to default font if no font found
    if font is None:
        try:
            font_name = "DejaVuSans-Bold" if bold else "DejaVuSans"
            font = ImageFont.truetype(font_name, font_size)
        except:
            font = ImageFont.load_default()
    
    # Word wrapping function
    def wrap_text(text, font, max_width):
        """Wrap text to fit within max_width."""
        words = text.split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            width = bbox[2] - bbox[0]
            
            if width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                    current_line = [word]
                else:
                    # Single word is too long, add it anyway
                    lines.append(word)
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines
    
    # Wrap text with padding
    padding = size[0] // 10  # 10% padding on each side
    max_width = size[0] - (2 * padding)
    lines = wrap_text(text, font, max_width)
    
    # Calculate starting y position to center text vertically
    total_height = 0
    line_heights = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_height = bbox[3] - bbox[1]
        line_heights.append(line_height)
        total_height += line_height
    
    # Add spacing between lines
    line_spacing = 5
    total_height += line_spacing * (len(lines) - 1)
    
    y = (size[1] - total_height) // 2
    
    # Draw each line centered
    for line, line_height in zip(lines, line_heights):
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        x = (size[0] - line_width) // 2
        draw.text((x, y), line, fill=text_color, font=font)
        y += line_height + line_spacing
    
    return image


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

    thumbnail_x = (margins[3] + (thumbnail_max_width - thumbnail.width) // 2)
    thumbnail_y = (margins[0] + (thumbnail_max_height - thumbnail.height) // 2)

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


def create_scaled_image(dock, image, margins=[0, 0, 0, 0], background='black'):
    return create_scaled_key_image(dock, image, margins, background)


def create_scaled_key_image(dock, image, margins=[0, 0, 0, 0], background='black'):
    return _scale_image(image, dock.key_image_format(), margins, background)


def create_scaled_touchscreen_image(dock, image, margins=[0, 0, 0, 0], background='black'):
    return _scale_image(image, dock.touchscreen_image_format(), margins, background)

def to_native_key_format(dock, image):
    return _to_native_format(image, dock.key_image_format())

def to_native_seondscreen_format(dock, image):
    return _to_native_format(image, dock.secondscreen_image_format())

def to_native_touchscreen_format(dock, image):
    return _to_native_format(image, dock.touchscreen_image_format())
