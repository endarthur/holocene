"""CLI commands for thermal printer integration."""

import click
from rich.console import Console
from datetime import datetime
from pathlib import Path

from ..integrations.paperang import PaperangClient, ThermalRenderer
from ..storage.database import Database
from ..config import load_config

console = Console()


@click.group()
def print_group():
    """Print research content to thermal printer."""
    pass


@print_group.command("book")
@click.argument("book_id", type=int)
@click.option("--font-size", "-s", type=int, default=18, help="Font size (default: 18)")
@click.option("--font", "-f", type=str, default="FiraCode", help="Font name (FiraCode, JetBrainsMono, Iosevka, Consolas)")
def print_book(book_id: int, font_size: int, font: str):
    """Print book summary to thermal printer."""
    config = load_config()
    db = Database(config.db_path)

    # Get book
    book = db.get_book(book_id)

    if not book:
        console.print(f"[red]✗[/red] Book #{book_id} not found")
        db.close()
        return

    # Format book summary
    title = book.get("title", "Unknown")
    author = book.get("author", "Unknown author")
    year = book.get("publication_year", "")
    subjects = book.get("subjects", "")
    notes = book.get("notes", "")

    year_str = f" ({year})" if year else ""

    summary = f"""{title}
by {author}{year_str}

{notes if notes else ""}

{f"Subjects: {subjects}" if subjects else ""}

Printed: {datetime.now().strftime("%Y-%m-%d")}"""

    console.print(f"[cyan]Printing book summary:[/cyan] {title}")

    # Connect to printer
    renderer = ThermalRenderer(font_size=font_size, font_name=font)
    bitmap = renderer.render_text(summary)

    num_lines = len(bitmap) // 48
    console.print(f"[dim]Rendering {num_lines} lines...[/dim]")

    client = PaperangClient()
    if not client.find_printer():
        console.print("[red]✗[/red] Printer not found!")
        console.print("[dim]Make sure the Paperang P1 is connected via USB[/dim]")
        db.close()
        return

    console.print("[green]✓[/green] Printer connected")
    client.handshake()

    with console.status("[cyan]Printing...", spinner="dots"):
        client.print_bitmap(bitmap, autofeed=True)

    console.print("[green]✓[/green] Print complete!")

    import time
    time.sleep(1)
    client.disconnect()
    db.close()


@print_group.command("paper")
@click.argument("paper_id", type=int)
@click.option("--font-size", "-s", type=int, default=18, help="Font size (default: 18)")
@click.option("--font", "-f", type=str, default="FiraCode", help="Font name (FiraCode, JetBrainsMono, Iosevka, Consolas)")
@click.option("--include-abstract", "-a", is_flag=True, help="Include abstract")
def print_paper(paper_id: int, font_size: int, font: str, include_abstract: bool):
    """Print paper summary to thermal printer."""
    config = load_config()
    db = Database(config.db_path)

    # Get paper
    paper = db.get_paper(paper_id)

    if not paper:
        console.print(f"[red]✗[/red] Paper #{paper_id} not found")
        db.close()
        return

    # Format paper summary
    title = paper.get("title", "Unknown")
    authors = paper.get("authors", [])
    authors_str = ", ".join(authors[:3]) if authors else "Unknown authors"
    if len(authors) > 3:
        authors_str += " et al."

    journal = paper.get("journal", "")
    date = paper.get("publication_date", "")
    doi = paper.get("doi", "")
    abstract = paper.get("abstract", "")

    summary = f"""{title}

{authors_str}

{journal if journal else ""}
{date if date else ""}

DOI: {doi}
"""

    if include_abstract and abstract:
        summary += f"\nAbstract:\n{abstract}\n"

    summary += f"\nPrinted: {datetime.now().strftime('%Y-%m-%d')}"

    console.print(f"[cyan]Printing paper summary:[/cyan] {title}")

    # Connect to printer
    renderer = ThermalRenderer(font_size=font_size, font_name=font)
    bitmap = renderer.render_text(summary)

    num_lines = len(bitmap) // 48
    console.print(f"[dim]Rendering {num_lines} lines...[/dim]")

    client = PaperangClient()
    if not client.find_printer():
        console.print("[red]✗[/red] Printer not found!")
        console.print("[dim]Make sure the Paperang P1 is connected via USB[/dim]")
        db.close()
        return

    console.print("[green]✓[/green] Printer connected")
    client.handshake()

    with console.status("[cyan]Printing...", spinner="dots"):
        client.print_bitmap(bitmap, autofeed=True)

    console.print("[green]✓[/green] Print complete!")

    import time
    time.sleep(1)
    client.disconnect()
    db.close()


@print_group.command("text")
@click.argument("text")
@click.option("--font-size", "-s", type=int, default=18, help="Font size (default: 18)")
@click.option("--font", "-f", type=str, default="FiraCode", help="Font name (FiraCode, JetBrainsMono, Iosevka, Consolas)")
def print_text(text: str, font_size: int, font: str):
    """Print custom text to thermal printer."""
    console.print(f"[cyan]Printing text...[/cyan]")

    # Add timestamp
    full_text = f"""{text}

---
Printed: {datetime.now().strftime('%Y-%m-%d %H:%M')}"""

    # Connect to printer
    renderer = ThermalRenderer(font_size=font_size, font_name=font)
    bitmap = renderer.render_text(full_text)

    num_lines = len(bitmap) // 48
    console.print(f"[dim]Rendering {num_lines} lines...[/dim]")

    client = PaperangClient()
    if not client.find_printer():
        console.print("[red]✗[/red] Printer not found!")
        console.print("[dim]Make sure the Paperang P1 is connected via USB[/dim]")
        return

    console.print("[green]✓[/green] Printer connected")
    client.handshake()

    with console.status("[cyan]Printing...", spinner="dots"):
        client.print_bitmap(bitmap, autofeed=True)

    console.print("[green]✓[/green] Print complete!")

    import time
    time.sleep(1)
    client.disconnect()


@print_group.command("image")
@click.argument("image_path", type=click.Path(exists=True))
@click.option("--no-dither", is_flag=True, help="Disable Floyd-Steinberg dithering")
def print_image(image_path: str, no_dither: bool):
    """Print image to thermal printer."""
    from PIL import Image

    console.print(f"[cyan]Loading image:[/cyan] {image_path}")

    try:
        img = Image.open(image_path)
        console.print(f"[dim]Original size: {img.width}x{img.height}[/dim]")
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to load image: {e}")
        return

    # Connect to printer
    renderer = ThermalRenderer()

    with console.status("[cyan]Rendering image...", spinner="dots"):
        bitmap = renderer.render_image(img, dither=not no_dither)

    num_lines = len(bitmap) // 48
    console.print(f"[dim]Rendered {num_lines} lines[/dim]")

    client = PaperangClient()
    if not client.find_printer():
        console.print("[red]✗[/red] Printer not found!")
        console.print("[dim]Make sure the Paperang P1 is connected via USB[/dim]")
        return

    console.print("[green]✓[/green] Printer connected")
    client.handshake()

    with console.status("[cyan]Printing...", spinner="dots"):
        client.print_bitmap(bitmap, autofeed=True)

    console.print("[green]✓[/green] Print complete!")

    import time
    time.sleep(1)
    client.disconnect()


@print_group.command("status")
def print_status():
    """Check thermal printer status."""
    console.print("[cyan]Checking printer status...[/cyan]")

    client = PaperangClient()

    if client.find_printer():
        console.print("[green]✓[/green] Paperang P1 printer found")
        console.print(f"[dim]VID: {hex(client.VID)}, PID: {hex(client.PID)}[/dim]")
        client.disconnect()
    else:
        console.print("[red]✗[/red] Printer not found")
        console.print("\n[yellow]Troubleshooting:[/yellow]")
        console.print("1. Make sure the printer is connected via USB")
        console.print("2. Ensure WinUSB driver is installed (use Zadig)")
        console.print("3. Check that the printer is powered on")
