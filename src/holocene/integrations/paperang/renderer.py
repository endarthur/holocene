"""Text-to-image rendering for Paperang thermal printer."""

import os
import sys
from pathlib import Path

# Enable libraqm support for ligatures (if fribidi.dll is available)
# Solution from: https://stackoverflow.com/a/79583567/1457481
# Simply placing fribidi.dll in the Python directory and setting FRIBIDI_PATH
# enables full OpenType ligature support via libraqm
try:
    fribidi_dll = Path(sys.executable).parent / "fribidi.dll"
    if fribidi_dll.exists():
        os.environ['FRIBIDI_PATH'] = str(fribidi_dll)
except:
    pass  # Ligatures won't work, but basic rendering will

from PIL import Image, ImageDraw, ImageFont
from typing import Optional
import textwrap


class ThermalRenderer:
    """Renders text to monochrome bitmap for thermal printing."""

    # Paperang P1 specifications
    PRINT_WIDTH = 384  # pixels
    LINE_WIDTH = 48  # bytes (384 / 8)

    def __init__(self, font_size: int = 18, margin: int = 8, font_name: str = "FiraCode"):
        """
        Initialize renderer.

        Args:
            font_size: Font size in pixels (default: 18 for ~32 chars/line)
            margin: Margin in pixels on left and right
            font_name: Font name to use (FiraCode, JetBrainsMono, Iosevka, Consolas, Georgia)
        """
        self.font_size = font_size
        self.margin = margin
        self.content_width = self.PRINT_WIDTH - (2 * margin)

        # Try to load a font
        import os
        import platform

        font_loaded = False

        # Font mappings
        font_files = {
            "FiraCode": "FiraCode-Regular.ttf",
            "JetBrainsMono": "JetBrainsMonoNerdFont-Regular.ttf",
            "Iosevka": "IosevkaNerdFont-Regular.ttf",
            "Hack": "HackNerdFont-Regular.ttf",
            "CascadiaMono": "CascadiaMono.ttf",
            "Consolas": "consola.ttf",
            "Georgia": "georgia.ttf",
        }

        # Windows font paths
        if platform.system() == "Windows":
            win_fonts = os.environ.get('WINDIR', 'C:\\Windows') + '\\Fonts\\'
            user_fonts = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Windows', 'Fonts')

            # Try requested font first
            if font_name in font_files:
                font_file = font_files[font_name]
                font_options = [
                    os.path.join(user_fonts, font_file),
                    os.path.join(win_fonts, font_file),
                ]
            else:
                # Fallback order
                font_options = [
                    os.path.join(user_fonts, font_files["FiraCode"]),
                    os.path.join(win_fonts, font_files["Consolas"]),
                    os.path.join(win_fonts, font_files["Georgia"]),
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

        # Calculate exact chars per line for monospace fonts
        self._calculate_chars_per_line()

    def _calculate_chars_per_line(self):
        """Calculate exact characters per line based on actual font metrics."""
        # Test with 'M' (typically widest char in monospace)
        img = Image.new('1', (100, 100), 1)
        draw = ImageDraw.Draw(img)

        bbox = draw.textbbox((0, 0), 'M', font=self.font)
        char_width = bbox[2] - bbox[0]

        if char_width > 0:
            calculated = self.content_width // char_width
            # Conservative cap at 32 chars for safety (avoids edge-case wrapping issues)
            self.chars_per_line = min(calculated, 32)
        else:
            # Fallback to reasonable default
            self.chars_per_line = 32

    def _wrap_text(self, text: str) -> list[str]:
        """
        Wrap text to fit printer width.

        Args:
            text: Text to wrap

        Returns:
            List of wrapped lines
        """
        lines = []
        for paragraph in text.split('\n'):
            if not paragraph:
                lines.append('')
            else:
                wrapped = textwrap.fill(paragraph, width=self.chars_per_line)
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
            lines.append("=" * self.chars_per_line)

        # Center title
        lines.append(title.center(self.chars_per_line))

        if separator:
            lines.append("=" * self.chars_per_line)

        lines.append("")  # Blank line
        lines.append(body)

        if footer:
            lines.append("")  # Blank line
            lines.append("-" * self.chars_per_line)
            lines.append(footer)

        text = "\n".join(lines)
        return self.render_text(text)
