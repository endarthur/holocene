# Thermal Printer Architecture

## Design Principles

The thermal printing system is designed with clear separation between **rendering/typesetting** and **printer drivers**.

### Layer Separation

```
┌─────────────────────────────────────┐
│  Spinitex Markdown Renderer         │  ← Printer-agnostic
│  (Typesetting, font rendering)      │
└─────────────────┬───────────────────┘
                  │ Outputs: PIL Image / Bitmap
                  ↓
┌─────────────────────────────────────┐
│  Printer Drivers                    │  ← Printer-specific
│  (Protocol, chunking, commands)     │
├─────────────────────────────────────┤
│  • Paperang P1 (58mm, USB custom)   │
│  • Generic 58mm (ESC/POS)           │
│  • Generic 80mm (ESC/POS)           │
│  • Others...                        │
└─────────────────────────────────────┘
```

## Spinitex (Rendering Layer)

**Location:** `src/holocene/integrations/paperang/spinitex.py`

**Responsibilities:**
- Markdown parsing
- Font loading and switching (regular, bold, italic)
- Text layout and wrapping
- Line breaking algorithms
- Inline styling
- Block rendering (headers, paragraphs, lists, code, quotes)
- Output: Bitmap (PIL Image or raw bytes)

**Printer-agnostic parameters:**
- `width`: Print width in pixels (e.g., 384px for 58mm, 576px for 80mm)
- `margin`: Margins in pixels
- `font_name`: Font family to use
- `base_size`: Base font size

**Output:** Pure bitmap data (1 bit per pixel, line-by-line)

## Printer Drivers

**Responsibilities:**
- Hardware communication (USB, Bluetooth, Serial, Network)
- Protocol implementation (custom, ESC/POS, etc.)
- Bitmap chunking/formatting for specific printer
- Printer-specific commands (init, feed, cut, etc.)
- Paper width constants

### Requirements for New Drivers

Any thermal printer that accepts **bitmap line data** can be supported:

```python
class ThermalPrinterDriver:
    """Abstract base for thermal printer drivers."""

    PRINT_WIDTH: int  # Width in pixels (e.g., 384, 576)

    def print_bitmap(self, bitmap: bytes, autofeed: bool = True):
        """
        Send bitmap to printer.

        Args:
            bitmap: Raw bitmap data (PRINT_WIDTH/8 bytes per line)
            autofeed: Feed paper after printing
        """
        pass
```

### Existing Drivers

#### Paperang P1 (58mm, Custom Protocol)
- **Location:** `src/holocene/integrations/paperang/client.py`
- **Width:** 384 pixels (58mm)
- **Protocol:** Custom USB bulk transfer
- **Chunking:** 1536 bytes per chunk, 100ms delay
- **Special:** Handshake required, CRC validation

#### Future: Generic ESC/POS (58mm/80mm)
- **Width:** 384px (58mm) or 576px (80mm)
- **Protocol:** Standard ESC/POS commands
- **Library:** `python-escpos`
- **Commands:** `GS v 0` for bitmap mode

## Usage Example

```python
# Render markdown with Spinitex (printer-agnostic)
from holocene.integrations.paperang.spinitex import MarkdownRenderer

renderer = MarkdownRenderer(
    width=384,  # 58mm printer
    ppi=203,    # 8 dots/mm
    margin_mm=2.0,
    font_name="FiraCode",
    base_size=18
)

bitmap = renderer.render("""
# Hello World

This is **bold** and *italic* text.

- List item 1
- List item 2
""")

# Print with specific driver
from holocene.integrations.paperang import PaperangClient

client = PaperangClient()
if client.find_printer():
    client.handshake()
    client.print_bitmap(bitmap, autofeed=True)
    client.disconnect()
```

## Adding a New Printer

1. **Implement driver** in `src/holocene/integrations/<printer_name>/`
2. **Set PRINT_WIDTH** constant (384 for 58mm, 576 for 80mm, etc.)
3. **Implement `print_bitmap()`** to send bitmap data using printer's protocol
4. **Use Spinitex** with appropriate width and PPI parameters
5. **No changes needed** to Spinitex itself!

## Design Benefits

✓ Single markdown renderer works with any printer
✓ Easy to add new printer models
✓ Consistent typography across all printers
✓ Test rendering without hardware
✓ Swap printers without changing rendering code

## Bitmap Format

All printers receive the same bitmap format:

- **1 bit per pixel** (0=white, 1=black)
- **Line-by-line** format
- **Width in bytes:** `PRINT_WIDTH / 8`
- **Total size:** `(PRINT_WIDTH / 8) * height_in_lines`

Each printer driver handles the conversion to its specific protocol.
