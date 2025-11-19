"""CLI commands for thermal printer integration."""

import click
from rich.console import Console
from datetime import datetime
from pathlib import Path

from ..integrations.paperang import PaperangClient, ThermalRenderer
from ..integrations.paperang.spinitex import MarkdownRenderer
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


@print_group.command("summary")
@click.option("--font-size", "-s", type=int, default=18, help="Font size (default: 18)")
@click.option("--font", "-f", type=str, default="FiraCode", help="Font name")
@click.option("--max-height", "-h", type=int, default=120, help="Max height in mm (default: 120)")
def print_summary(font_size: int, font: str, max_height: int):
    """Print AI-generated summary of your entire Holocene collection."""
    config = load_config()
    db = Database(config.db_path)

    console.print("[cyan]Gathering collection statistics...[/cyan]")

    # Query database for statistics
    cursor = db.conn.cursor()

    # Get counts
    stats = {}

    cursor.execute("SELECT COUNT(*) FROM books")
    stats['books'] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM papers")
    stats['papers'] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM links")
    stats['links'] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM mercadolivre_favorites")
    stats['ml_favorites'] = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM items")
    stats['inventory_items'] = cursor.fetchone()[0]

    # Get some interesting details
    cursor.execute("""
        SELECT COUNT(*) FROM books
        WHERE classification_system IS NOT NULL
    """)
    stats['classified_books'] = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM links
        WHERE trust_tier = 'pre-llm'
    """)
    stats['pre_llm_links'] = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COUNT(*) FROM mercadolivre_favorites
        WHERE description IS NOT NULL
    """)
    stats['enriched_ml_items'] = cursor.fetchone()[0]

    # Sample some recent additions (titles only)
    cursor.execute("""
        SELECT title FROM books
        ORDER BY created_at DESC
        LIMIT 3
    """)
    recent_books = [row[0] for row in cursor.fetchall()]

    cursor.execute("""
        SELECT title FROM papers
        ORDER BY added_at DESC
        LIMIT 3
    """)
    recent_papers = [row[0] for row in cursor.fetchall()]

    console.print(f"[dim]Books: {stats['books']}, Papers: {stats['papers']}, "
                  f"Links: {stats['links']}, ML Favorites: {stats['ml_favorites']}, "
                  f"Inventory: {stats['inventory_items']}[/dim]")

    # Build prompt for DeepSeek
    current_date = datetime.now().strftime("%B %d, %Y")

    prompt = f"""You are creating a snapshot summary for a thermal receipt printer.

Today's date: {current_date}

Collection Statistics:
- Books: {stats['books']} ({stats['classified_books']} classified with Dewey)
- Papers: {stats['papers']}
- Links: {stats['links']} ({stats['pre_llm_links']} pre-LLM era)
- Mercado Livre favorites: {stats['ml_favorites']} ({stats['enriched_ml_items']} enriched)
- Inventory items: {stats['inventory_items']}

Recent additions:
Books: {', '.join(recent_books[:2]) if recent_books else 'None'}
Papers: {', '.join(recent_papers[:2]) if recent_papers else 'None'}

Create a concise summary (max 250 words) in markdown format. Include:
1. A centered title: "# HOLOCENE"
2. A centered subtitle with current date
3. A brief, direct paragraph about what this collection represents
4. The key statistics formatted clearly (use **bold** for numbers)
5. A thoughtful observation about patterns or focus areas in the collection
6. Centered footer with date stamp

Style: Direct and conversational, like a knowledgeable colleague summarizing findings.
Avoid flowery or grandiose language - be insightful but grounded.
Use markdown: # headers, **bold**, centered alignment (@align:center).
Use horizontal rules (---) to separate sections."""

    console.print("[cyan]Generating summary with DeepSeek...[/cyan]")

    # Use NanoGPT to generate summary
    from ..llm.nanogpt import NanoGPTClient

    llm = NanoGPTClient(
        api_key=config.llm.api_key,
        base_url=config.llm.base_url
    )

    with console.status("[cyan]Thinking...", spinner="dots"):
        summary = llm.simple_prompt(
            prompt=prompt,
            model=config.llm.primary,  # DeepSeek V3
            temperature=0.7  # Creative but coherent
        )

    console.print("[green]✓[/green] Summary generated")
    console.print(f"\n[dim]{summary[:200]}...[/dim]\n")

    # Render to bitmap with Spinitex markdown renderer
    renderer = MarkdownRenderer(
        width=384,
        ppi=203,
        margin_mm=2.0,
        font_name=font,
        base_size=font_size
    )
    bitmap = renderer.render(summary)

    num_lines = len(bitmap) // 48
    height_mm = (num_lines / 203) * 25.4  # Convert pixels to mm

    console.print(f"[dim]Rendered {num_lines} lines (~{height_mm:.1f}mm)[/dim]")

    if height_mm > max_height:
        console.print(f"[yellow]⚠[/yellow] Summary exceeds max height ({height_mm:.1f}mm > {max_height}mm)")
        console.print("[yellow]Consider using smaller font size (-s flag)[/yellow]")
        if not click.confirm("Continue anyway?"):
            db.close()
            return

    # Connect to printer
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
    console.print(f"[dim]Printed {height_mm:.1f}mm of knowledge[/dim]")

    import time
    time.sleep(1)
    client.disconnect()
    db.close()


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
