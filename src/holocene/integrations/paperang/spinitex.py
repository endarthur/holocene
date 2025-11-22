"""Spinitex - Minimal TeX-like markdown renderer for thermal printing.

Named after the spinifex texture in komatiites - ultra-basic rocks.
A geology pun: ultra-basic TeX (Spini-tex) for thermal printing.

Thermal-specific directives:
    ---break---              # Page break / cut line
    @align:center            # Center alignment
    @align:right             # Right alignment
    @align:left              # Left alignment (default)
    \hfill                  # Fill space (left/right split on same line)
    @image:path                    # Insert image (resized to width)
    @image:path:0.5                # Insert image at 50% width (0.0-1.0)
    @image:path:0.5:atkinson       # With Atkinson dithering
                                   # Dithering: floyd_steinberg (default), atkinson,
                                   # jarvis, stucki, burkes, sierra, ordered, threshold
    @font:name               # Font switching
    @size:N                  # Size override
"""

import re
from typing import List, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import os
import numpy as np
import logging

logger = logging.getLogger(__name__)

# Import hitherdither for advanced dithering
try:
    import hitherdither
    HITHERDITHER_AVAILABLE = True
except ImportError:
    HITHERDITHER_AVAILABLE = False


class MarkdownRenderer:
    """Renders markdown to bitmap for thermal printing."""

    def __init__(
        self,
        width: int = 384,
        ppi: int = 203,
        margin_mm: float = 2.0,
        font_name: str = "FiraCode",
        base_size: int = 16
    ):
        """
        Initialize markdown renderer.

        Args:
            width: Print width in pixels (384 for 58mm, 576 for 80mm)
            ppi: Printer resolution in pixels per inch (203 DPI = 8 dots/mm standard)
            margin_mm: Margin in millimeters
            font_name: Base font name (FiraCode, JetBrainsMono, etc.)
            base_size: Base font size in pixels
        """
        self.width = width
        self.ppi = ppi

        # Convert physical margin to pixels
        self.margin = int(margin_mm * ppi / 25.4)  # mm to inches to pixels
        self.content_width = width - (2 * self.margin)
        self.base_size = base_size

        # Load font variants
        self._load_fonts(font_name, base_size)

        # Calculate char width for wrapping
        self._calculate_char_width()

        # Styling
        self.line_spacing = 4
        self.paragraph_spacing = 8
        self.current_align = 'left'  # Default alignment

    def _load_fonts(self, font_name: str, size: int):
        """Load Regular, Bold, and Italic variants."""
        import platform

        if platform.system() != "Windows":
            # Use default font
            self.fonts = {
                'regular': ImageFont.load_default(),
                'bold': ImageFont.load_default(),
                'italic': ImageFont.load_default(),
            }
            return

        win_fonts = os.environ.get('WINDIR', 'C:\\Windows') + '\\Fonts\\'
        user_fonts = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Windows', 'Fonts')

        # Font file mappings
        font_files = {
            'FiraCode': {
                'regular': 'FiraCode-Regular.ttf',
                'bold': 'FiraCode-Bold.ttf',
                'italic': 'FiraCode-Regular.ttf',  # No italic variant
            },
            'JetBrainsMono': {
                'regular': 'JetBrainsMonoNerdFont-Regular.ttf',
                'bold': 'JetBrainsMonoNerdFont-Bold.ttf',
                'italic': 'JetBrainsMonoNerdFont-Italic.ttf',
            },
            'Iosevka': {
                'regular': 'IosevkaNerdFont-Regular.ttf',
                'bold': 'IosevkaNerdFont-Bold.ttf',
                'italic': 'IosevkaNerdFont-Italic.ttf',
            },
        }

        files = font_files.get(font_name, font_files['FiraCode'])
        self.fonts = {}

        for variant, filename in files.items():
            for base_dir in [user_fonts, win_fonts]:
                font_path = os.path.join(base_dir, filename)
                try:
                    self.fonts[variant] = ImageFont.truetype(font_path, size)
                    break
                except:
                    continue

            # Fallback to regular if variant not found
            if variant not in self.fonts:
                self.fonts[variant] = self.fonts.get('regular', ImageFont.load_default())

    def _calculate_char_width(self):
        """Calculate average character width for wrapping."""
        img = Image.new('1', (100, 100), 1)
        draw = ImageDraw.Draw(img)

        bbox = draw.textbbox((0, 0), 'M', font=self.fonts['regular'])
        char_width = bbox[2] - bbox[0]

        if char_width > 0:
            self.chars_per_line = min(self.content_width // char_width, 32)
        else:
            self.chars_per_line = 32

    def parse_markdown(self, text: str) -> List[dict]:
        """
        Parse markdown into structured blocks.

        Returns list of blocks: {'type': 'header'|'para'|'list'|'code', 'content': ...}
        """
        blocks = []
        lines = text.split('\n')
        i = 0
        current_align = 'left'  # Track current alignment state

        while i < len(lines):
            line = lines[i]

            # Alignment directives
            if line.startswith('@align:'):
                align_value = line.split(':', 1)[1].strip()
                if align_value in ['left', 'center', 'right']:
                    current_align = align_value
                i += 1
                continue

            # Image directives
            if line.startswith('@image:'):
                # Parse @image:path or @image:path:fraction or @image:path:fraction:dithering
                parts = line.split(':', 3)[1:]  # Skip '@image'
                image_path = parts[0].strip()
                width_fraction = 1.0
                dithering = 'floyd_steinberg'
                
                if len(parts) > 1:
                    try:
                        width_fraction = float(parts[1].strip())
                        width_fraction = max(0.0, min(1.0, width_fraction))  # Clamp to [0, 1]
                    except ValueError:
                        width_fraction = 1.0
                
                if len(parts) > 2:
                    dithering = parts[2].strip()
                
                blocks.append({'type': 'image', 'path': image_path, 'width_fraction': width_fraction, 
                              'dithering': dithering, 'align': current_align})
                i += 1
                continue

            # Headers
            if line.startswith('#'):
                level = len(re.match(r'^#+', line).group())
                content = line.lstrip('#').strip()
                blocks.append({'type': 'header', 'level': level, 'content': content, 'align': 'center'})  # Headers default to center
                i += 1

            # Code blocks (indented)
            elif line.startswith('    ') or line.startswith('\t'):
                code_lines = []
                while i < len(lines) and (lines[i].startswith('    ') or lines[i].startswith('\t')):
                    code_lines.append(lines[i][4:] if lines[i].startswith('    ') else lines[i][1:])
                    i += 1
                blocks.append({'type': 'code', 'content': '\n'.join(code_lines)})

            # Block quotes
            elif line.startswith('>'):
                quote_lines = []
                while i < len(lines) and lines[i].startswith('>'):
                    quote_lines.append(lines[i][1:].strip())
                    i += 1
                blocks.append({'type': 'quote', 'content': ' '.join(quote_lines), 'align': current_align})

            # Lists
            elif re.match(r'^[\-\*\+]\s', line) or re.match(r'^\d+\.\s', line):
                list_items = []
                while i < len(lines) and (re.match(r'^[\-\*\+]\s', lines[i]) or re.match(r'^\d+\.\s', lines[i])):
                    item = re.sub(r'^[\-\*\+]\s|^\d+\.\s', '', lines[i])
                    list_items.append(item)
                    i += 1
                blocks.append({'type': 'list', 'items': list_items, 'align': current_align})

            # Empty line
            elif not line.strip():
                i += 1

            # Regular paragraph
            else:
                para_lines = []
                while i < len(lines) and lines[i].strip() and not lines[i].startswith('#') and not lines[i].startswith('>') and not re.match(r'^[\-\*\+]\s|^\d+\.\s', lines[i]):
                    para_lines.append(lines[i])
                    i += 1
                blocks.append({'type': 'para', 'content': ' '.join(para_lines), 'align': current_align})

        return blocks

    def parse_inline(self, text: str) -> List[Tuple[str, str]]:
        """
        Parse inline markdown (bold, italic, code).

        Returns: [(text, style), ...] where style is 'regular', 'bold', 'italic', 'code'
        """
        segments = []
        pos = 0

        # Pattern: **bold** *italic* `code`
        # Use [^*] and [^`] to prevent matching across delimiters
        pattern = r'(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)'

        for match in re.finditer(pattern, text):
            # Add regular text before match
            if match.start() > pos:
                segments.append((text[pos:match.start()], 'regular'))

            # Add styled text
            matched = match.group()
            if matched.startswith('**'):
                segments.append((matched[2:-2], 'bold'))
            elif matched.startswith('*'):
                segments.append((matched[1:-1], 'italic'))
            elif matched.startswith('`'):
                segments.append((matched[1:-1], 'code'))

            pos = match.end()

        # Add remaining text
        if pos < len(text):
            segments.append((text[pos:], 'regular'))

        return segments

    def render(self, markdown_text: str) -> bytes:
        """
        Render markdown to bitmap.

        Returns: Raw bitmap data (48 bytes per line)
        """
        blocks = self.parse_markdown(markdown_text)

        # Render each block to image
        images = []

        for block in blocks:
            align = block.get('align', 'left')
            
            if block['type'] == 'header':
                img = self._render_header(block['content'], block['level'], align)
            elif block['type'] == 'para':
                img = self._render_paragraph(block['content'], align)
            elif block['type'] == 'code':
                img = self._render_code(block['content'], align)
            elif block['type'] == 'quote':
                img = self._render_quote(block['content'], align)
            elif block['type'] == 'list':
                img = self._render_list(block['items'], align)
            elif block['type'] == 'image':
                img = self._render_image(block['path'], block['width_fraction'], block.get('dithering', 'floyd_steinberg'), align)
            else:
                continue

            if img:
                images.append(img)

        # Combine images vertically
        if not images:
            return bytes()

        total_height = sum(img.height for img in images) + self.margin * 2
        combined = Image.new('1', (self.width, total_height), 1)

        y_offset = self.margin
        for img in images:
            combined.paste(img, (0, y_offset))
            y_offset += img.height + self.paragraph_spacing

        # Convert to bitmap
        return self._image_to_bitmap(combined)

    def _render_header(self, text: str, level: int, align: str = 'center') -> Image.Image:
        """Render header with appropriate size and alignment (non-breaking)."""
        # Scale font size based on level
        size_scale = {1: 1.5, 2: 1.3, 3: 1.1}.get(level, 1.0)
        font_size = int(self.base_size * size_scale)

        # Use bold font for headers
        font = ImageFont.truetype(self.fonts['bold'].path, font_size)

        img = Image.new('1', (self.width, 100), 1)
        draw = ImageDraw.Draw(img)

        # Measure text
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Make headers non-breaking: reduce font size if text doesn't fit
        max_width = self.width - (2 * self.margin)
        while text_width > max_width and font_size > 8:
            font_size -= 1
            font = ImageFont.truetype(self.fonts['bold'].path, font_size)
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

        # Calculate x position based on alignment
        if align == 'center':
            x = (self.width - text_width) // 2
        elif align == 'right':
            x = self.width - text_width - self.margin
        else:  # left
            x = self.margin

        # Create final image
        img = Image.new('1', (self.width, text_height + 8), 1)
        draw = ImageDraw.Draw(img)
        draw.text((x, 4), text, font=font, fill=0)

        return img

    def _render_hfill_line(self, text: str) -> Image.Image:
        """Render a line with \hfill (left/right split)."""
        # Split on \hfill
        parts = text.split('\hfill', 1)
        if len(parts) != 2:
            # Fallback if something goes wrong
            return self._render_paragraph(text.replace('\hfill', ' '), 'left')
        
        left_text = parts[0].strip()
        right_text = parts[1].strip()
        
        # Parse inline styles for both parts
        left_segments = self.parse_inline(left_text)
        right_segments = self.parse_inline(right_text)
        
        # Measure both parts
        temp_img = Image.new('1', (1000, 50), 1)
        temp_draw = ImageDraw.Draw(temp_img)
        
        # Measure left side
        left_x = 0
        for seg_text, style in left_segments:
            font = self.fonts[style if style != 'code' else 'regular']
            bbox = temp_draw.textbbox((left_x, 0), seg_text, font=font)
            left_x = bbox[2]
        left_width = left_x
        
        # Measure right side
        right_x = 0
        for seg_text, style in right_segments:
            font = self.fonts[style if style != 'code' else 'regular']
            bbox = temp_draw.textbbox((right_x, 0), seg_text, font=font)
            right_x = bbox[2]
        right_width = right_x
        
        # Create image
        line_height = self.base_size + self.line_spacing
        img = Image.new('1', (self.width, line_height + 8), 1)
        draw = ImageDraw.Draw(img)
        
        # Render left part
        x = self.margin
        y = 4
        for seg_text, style in left_segments:
            font = self.fonts[style if style != 'code' else 'regular']
            draw.text((x, y), seg_text, font=font, fill=0)
            bbox = draw.textbbox((x, y), seg_text, font=font)
            x = bbox[2]
        
        # Render right part (aligned to right margin)
        x = self.width - right_width - self.margin
        for seg_text, style in right_segments:
            font = self.fonts[style if style != 'code' else 'regular']
            draw.text((x, y), seg_text, font=font, fill=0)
            bbox = draw.textbbox((x, y), seg_text, font=font)
            x = bbox[2]
        
        return img

    def _render_paragraph(self, text: str, align: str = 'left') -> Image.Image:
        """Render paragraph with inline styling and alignment."""
        # Check for \hfill (left/right split)
        if '\hfill' in text:
            return self._render_hfill_line(text)
        
        segments = self.parse_inline(text)

        # Simple wrapping - render all segments
        lines = []
        current_line = []
        current_width = 0

        for segment_text, style in segments:
            words = segment_text.split()
            font = self.fonts[style if style != 'code' else 'regular']

            for word in words:
                # Measure word width
                img = Image.new('1', (1000, 50), 1)
                draw = ImageDraw.Draw(img)
                bbox = draw.textbbox((0, 0), word + ' ', font=font)
                word_width = bbox[2] - bbox[0]

                if current_width + word_width > self.content_width:
                    lines.append(current_line)
                    current_line = [(word + ' ', style)]
                    current_width = word_width
                else:
                    current_line.append((word + ' ', style))
                    current_width += word_width

        if current_line:
            lines.append(current_line)

        # Render lines
        line_height = self.base_size + self.line_spacing
        img = Image.new('1', (self.width, len(lines) * line_height + 8), 1)
        draw = ImageDraw.Draw(img)

        y = 4
        for line in lines:
            # Measure line width for alignment
            if align != 'left':
                temp_img = Image.new('1', (1000, 50), 1)
                temp_draw = ImageDraw.Draw(temp_img)
                line_x = 0
                for text, style in line:
                    font = self.fonts[style if style != 'code' else 'regular']
                    bbox = temp_draw.textbbox((line_x, 0), text, font=font)
                    line_x = bbox[2]
                line_width = line_x
                
                if align == 'center':
                    x = (self.width - line_width) // 2
                else:  # right
                    x = self.width - line_width - self.margin
            else:
                x = self.margin
            
            for text, style in line:
                font = self.fonts[style if style != 'code' else 'regular']
                draw.text((x, y), text, font=font, fill=0)
                bbox = draw.textbbox((x, y), text, font=font)
                x = bbox[2]
            y += line_height

        return img

    def _render_code(self, text: str, align: str = 'left') -> Image.Image:
        """Render code block with alignment."""
        lines = text.split('\n')
        line_height = self.base_size + self.line_spacing

        img = Image.new('1', (self.width, len(lines) * line_height + 16), 1)
        draw = ImageDraw.Draw(img)

        # Draw indent bar
        draw.rectangle([self.margin, 4, self.margin + 2, img.height - 4], fill=0)

        y = 8
        for line in lines:
            draw.text((self.margin + 8, y), line[:self.chars_per_line - 2], font=self.fonts['regular'], fill=0)
            y += line_height

        return img

    def _render_quote(self, text: str, align: str = 'left') -> Image.Image:
        """Render block quote with alignment."""
        # Similar to paragraph but indented
        img = Image.new('1', (self.width, 100), 1)
        draw = ImageDraw.Draw(img)

        # Draw quote bar
        draw.rectangle([self.margin, 0, self.margin + 2, 100], fill=0)

        # Wrap text
        import textwrap
        wrapped = textwrap.fill(text, width=self.chars_per_line - 4)
        lines = wrapped.split('\n')

        line_height = self.base_size + self.line_spacing
        img = Image.new('1', (self.width, len(lines) * line_height + 8), 1)
        draw = ImageDraw.Draw(img)

        # Draw quote bar
        draw.rectangle([self.margin, 0, self.margin + 2, img.height], fill=0)

        y = 4
        for line in lines:
            draw.text((self.margin + 8, y), line, font=self.fonts['italic'], fill=0)
            y += line_height

        return img

    def _render_list(self, items: List[str], align: str = 'left') -> Image.Image:
        """Render list items with alignment and inline markdown support."""
        line_height = self.base_size + self.line_spacing

        # Estimate height
        total_lines = sum(len(item) // self.chars_per_line + 1 for item in items)
        img = Image.new('1', (self.width, total_lines * line_height + 16), 1)
        draw = ImageDraw.Draw(img)

        y = 8
        for item in items:
            # Draw bullet
            draw.text((self.margin, y), '•', font=self.fonts['regular'], fill=0)

            # Parse inline markdown for the item
            segments = self.parse_inline(item)

            # Word-level wrapping with inline styles
            available_width = self.content_width - 16  # Account for bullet indent
            lines = []
            current_line = []
            current_width = 0

            for segment_text, style in segments:
                words = segment_text.split()
                font = self.fonts[style if style != 'code' else 'regular']

                for word in words:
                    # Measure word width
                    temp_img = Image.new('1', (1000, 50), 1)
                    temp_draw = ImageDraw.Draw(temp_img)
                    bbox = temp_draw.textbbox((0, 0), word + ' ', font=font)
                    word_width = bbox[2] - bbox[0]

                    if current_width + word_width > available_width and current_line:
                        lines.append(current_line)
                        current_line = [(word + ' ', style)]
                        current_width = word_width
                    else:
                        current_line.append((word + ' ', style))
                        current_width += word_width

            if current_line:
                lines.append(current_line)

            # Render the wrapped lines with styled segments
            for line in lines:
                x = self.margin + 16
                for text, style in line:
                    font = self.fonts[style if style != 'code' else 'regular']
                    draw.text((x, y), text, font=font, fill=0)
                    bbox = draw.textbbox((x, y), text, font=font)
                    x = bbox[2]
                y += line_height

        # Trim image to actual height
        return img.crop((0, 0, self.width, y))

    def _render_image(self, image_path: str, width_fraction: float = 1.0, dithering: str = 'floyd_steinberg', align: str = 'left') -> Image.Image:
        """Render an image, resizing to fit thermal printer width."""
        try:
            # Load image
            img = Image.open(image_path)
            
            # Calculate target width
            target_width = int(self.content_width * width_fraction)
            
            # Calculate height maintaining aspect ratio
            aspect_ratio = img.height / img.width
            target_height = int(target_width * aspect_ratio)
            
            # Resize image
            img = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
            
            # Convert to grayscale for dithering
            img_gray = img.convert('L')
            
            # Apply dithering
            if HITHERDITHER_AVAILABLE and dithering != 'floyd_steinberg':
                try:
                    # Convert grayscale to RGB for hitherdither (it expects 3 channels)
                    img_rgb = img_gray.convert('RGB')
                    
                    # Create black and white palette
                    palette = hitherdither.palette.Palette([(0, 0, 0), (255, 255, 255)])
                    
                    if dithering == 'threshold':
                        # Simple threshold - no dithering
                        img_array = np.array(img_gray)
                        img_thresh = (img_array > 128).astype('uint8') * 255
                        img = Image.fromarray(img_thresh).convert('1')
                    elif dithering == 'ordered':
                        # Bayer ordered dithering
                        # For 2-color palette, use single threshold value (128 = middle gray)
                        threshold = 128
                        img_dithered = hitherdither.ordered.bayer.bayer_dithering(
                            img_rgb, palette, [threshold], order=8
                        )
                        img = img_dithered.convert('1')
                    else:
                        # Error diffusion methods
                        method_map = {
                            'atkinson': 'atkinson',
                            'jarvis': 'jarvis-judice-ninke',
                            'stucki': 'stucki',
                            'burkes': 'burkes',
                            'sierra': 'sierra3',
                        }
                        method = method_map.get(dithering, 'floyd-steinberg')
                        img_dithered = hitherdither.diffusion.error_diffusion_dithering(
                            img_rgb, palette, method=method, order=2
                        )
                        img = img_dithered.convert('1')
                except Exception as e:
                    logger.debug(f"Dithering '{dithering}' failed: {e}", exc_info=True)
                    # Fallback to Floyd-Steinberg (PIL default)
                    img = img_gray.convert('1')
            else:
                # Use PIL's default Floyd-Steinberg
                img = img_gray.convert('1')
            
            # Create final image with margins and alignment
            final_img = Image.new('1', (self.width, target_height + 16), 1)
            
            # Calculate x position based on alignment
            if align == 'center':
                x = (self.width - target_width) // 2
            elif align == 'right':
                x = self.width - target_width - self.margin
            else:  # left
                x = self.margin
            
            # Paste the image
            final_img.paste(img, (x, 8))
            
            return final_img
            
        except Exception as e:
            # On error, render error message as text
            logger.debug(f"Image rendering failed for {image_path}: {type(e).__name__}: {str(e)}", exc_info=True)
            error_text = f"[Image error: {image_path}] - {type(e).__name__}"
            return self._render_paragraph(error_text, 'left')

    def _image_to_bitmap(self, img: Image.Image) -> bytes:
        """Convert PIL Image to printer bitmap format."""
        if img.width != self.width:
            raise ValueError(f"Image must be {self.width} pixels wide")

        bitmap = bytearray()
        line_width = self.width // 8

        for y in range(img.height):
            line_bytes = bytearray(line_width)

            for x in range(self.width):
                pixel = img.getpixel((x, y))
                byte_idx = x // 8
                bit_idx = 7 - (x % 8)

                if pixel == 0:  # Black pixel
                    line_bytes[byte_idx] |= (1 << bit_idx)

            bitmap.extend(line_bytes)

        return bytes(bitmap)
