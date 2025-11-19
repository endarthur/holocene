"""Text-to-image rendering for Paperang thermal printer."""

from PIL import Image, ImageDraw, ImageFont
from typing import Optional
import textwrap


class ThermalRenderer:
    """Renders text to monochrome bitmap for thermal printing."""

    # Paperang P1 specifications
    PRINT_WIDTH = 384  # pixels
    LINE_WIDTH = 48  # bytes (384 / 8)

    def __init__(self, font_size: int = 16, margin: int = 8):
        """
        Initialize renderer.

        Args:
            font_size: Font size in pixels
            margin: Margin in pixels on left and right
        """
        self.font_size = font_size
        self.margin = margin
        self.content_width = self.PRINT_WIDTH - (2 * margin)

        # Try to load a font
        import os
        import platform

        font_loaded = False

        # Windows font paths
        if platform.system() == "Windows":
            win_fonts = os.environ.get('WINDIR', 'C:\\Windows') + '\\Fonts\\'
            font_options = [
                win_fonts + 'georgia.ttf',   # Georgia (elegant serif)
                win_fonts + 'calibri.ttf',   # Calibri (modern sans-serif)
                win_fonts + 'consola.ttf',   # Consolas (monospace)
                win_fonts + 'arial.ttf',     # Arial (fallback)
            ]

            for font_path in font_options:
                try:
                    self.font = ImageFont.truetype(font_path, font_size)
                    font_loaded = True
                    break
                except:
                    continue

        # Fallback to default if nothing loaded
        if not font_loaded:
            self.font = ImageFont.load_default()

    def _wrap_text(self, text: str, chars_per_line: int = 42) -> list[str]:
        """
        Wrap text to fit printer width.

        Args:
            text: Text to wrap
            chars_per_line: Approximate characters per line

        Returns:
            List of wrapped lines
        """
        lines = []
        for paragraph in text.split('\n'):
            if not paragraph:
                lines.append('')
            else:
                wrapped = textwrap.fill(paragraph, width=chars_per_line)
                lines.extend(wrapped.split('\n'))
        return lines

    def _text_to_image(self, text: str) -> Image.Image:
        """
        Convert text to PIL Image.

        Args:
            text: Text to render

        Returns:
            PIL Image in monochrome
        """
        # Wrap text
        lines = self._wrap_text(text)

        # Calculate image height
        line_height = self.font_size + 4  # Add some line spacing
        height = len(lines) * line_height + (2 * self.margin)

        # Create image
        img = Image.new('1', (self.PRINT_WIDTH, height), 1)  # White background
        draw = ImageDraw.Draw(img)

        # Draw text
        y = self.margin
        for line in lines:
            draw.text((self.margin, y), line, font=self.font, fill=0)  # Black text
            y += line_height

        return img

    def _image_to_bitmap(self, img: Image.Image) -> bytes:
        """
        Convert PIL Image to printer bitmap format.

        Args:
            img: PIL Image in mode '1' (monochrome)

        Returns:
            Raw bitmap data (48 bytes per line)
        """
        # Ensure image is correct width
        if img.width != self.PRINT_WIDTH:
            raise ValueError(f"Image must be {self.PRINT_WIDTH} pixels wide")

        # Convert to bitmap
        bitmap = bytearray()

        for y in range(img.height):
            line_bytes = bytearray(self.LINE_WIDTH)

            for x in range(self.PRINT_WIDTH):
                # Get pixel (0 = black, 1 = white)
                pixel = img.getpixel((x, y))

                # Calculate byte and bit position
                byte_idx = x // 8
                bit_idx = 7 - (x % 8)

                # Set bit (inverted: 0 = white, 1 = black for printer)
                if pixel == 0:  # Black pixel
                    line_bytes[byte_idx] |= (1 << bit_idx)

            bitmap.extend(line_bytes)

        return bytes(bitmap)

    def render_text(self, text: str) -> bytes:
        """
        Render text to printer bitmap format.

        Args:
            text: Text to render

        Returns:
            Raw bitmap data ready for printing
        """
        img = self._text_to_image(text)
        return self._image_to_bitmap(img)

    def _floyd_steinberg_dither(self, img: Image.Image) -> Image.Image:
        """
        Apply Floyd-Steinberg dithering to grayscale image.

        Args:
            img: Grayscale PIL Image

        Returns:
            Dithered monochrome image
        """
        # Convert to grayscale if not already
        if img.mode != 'L':
            img = img.convert('L')

        # Create a mutable copy
        img = img.copy()
        pixels = img.load()
        width, height = img.size

        # Create output image
        output = Image.new('1', (width, height), 1)
        output_pixels = output.load()

        # Floyd-Steinberg dithering
        for y in range(height):
            for x in range(width):
                old_pixel = pixels[x, y]
                new_pixel = 255 if old_pixel > 128 else 0
                output_pixels[x, y] = 1 if new_pixel == 255 else 0

                quant_error = old_pixel - new_pixel

                # Distribute error to neighboring pixels
                if x + 1 < width:
                    pixels[x + 1, y] = max(0, min(255, pixels[x + 1, y] + quant_error * 7 // 16))
                if y + 1 < height:
                    if x > 0:
                        pixels[x - 1, y + 1] = max(0, min(255, pixels[x - 1, y + 1] + quant_error * 3 // 16))
                    pixels[x, y + 1] = max(0, min(255, pixels[x, y + 1] + quant_error * 5 // 16))
                    if x + 1 < width:
                        pixels[x + 1, y + 1] = max(0, min(255, pixels[x + 1, y + 1] + quant_error * 1 // 16))

        return output

    def render_image(self, img: Image.Image, dither: bool = True) -> bytes:
        """
        Convert PIL Image to printer bitmap format.

        Args:
            img: PIL Image (will be converted to monochrome and resized)
            dither: Whether to apply Floyd-Steinberg dithering (default: True)

        Returns:
            Raw bitmap data ready for printing
        """
        # Resize to fit width while maintaining aspect ratio
        if img.width != self.PRINT_WIDTH:
            aspect_ratio = img.height / img.width
            new_height = int(self.PRINT_WIDTH * aspect_ratio)
            img = img.resize((self.PRINT_WIDTH, new_height), Image.Resampling.LANCZOS)

        # Convert to monochrome with optional dithering
        if dither:
            img = self._floyd_steinberg_dither(img)
        else:
            img = img.convert('1')

        return self._image_to_bitmap(img)

    def render_formatted(
        self,
        title: str,
        body: str,
        footer: Optional[str] = None,
        separator: bool = True
    ) -> bytes:
        """
        Render formatted document with title, body, and optional footer.

        Args:
            title: Title text (will be centered)
            body: Main body text
            footer: Optional footer text
            separator: Whether to add separator lines

        Returns:
            Raw bitmap data ready for printing
        """
        # Build formatted text
        lines = []

        if separator:
            lines.append("=" * 42)

        # Center title
        lines.append(title.center(42))

        if separator:
            lines.append("=" * 42)

        lines.append("")  # Blank line
        lines.append(body)

        if footer:
            lines.append("")  # Blank line
            lines.append("-" * 42)
            lines.append(footer)

        text = "\n".join(lines)
        return self.render_text(text)
