"""Statistics and analytics CLI commands."""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from datetime import datetime, timedelta
from collections import Counter
from pathlib import Path

from holocene.config import load_config
from holocene.storage.database import Database

console = Console()


@click.group()
def stats():
    """View collection statistics and analytics."""
    pass


@stats.command()
def overview():
    """Show overview of all collections."""
    config = load_config()
    db = Database(config.db_path)

    # Get counts for each collection
    # Note: This will need actual database queries once we have tables
    # For now, showing the structure

    console.print(Panel.fit(
        "[bold cyan]Holocene Collection Overview[/bold cyan]",
        border_style="cyan"
    ))

    # Create main stats table
    table = Table(title="Collection Summary", box=box.ROUNDED)
    table.add_column("Collection", style="cyan", no_wrap=True)
    table.add_column("Count", justify="right", style="green")
    table.add_column("Last Updated", style="yellow")

    # TODO: Get actual counts from database
    # For now, placeholder structure
    collections = [
        ("Books", 0, "Never"),
        ("Papers", 0, "Never"),
        ("Links", 0, "Never"),
        ("Activities", 0, "Never"),
        ("Research Reports", 0, "Never"),
    ]

    for name, count, last_updated in collections:
        table.add_row(name, str(count), last_updated)

    console.print(table)
    console.print()

    # Data location info
    info_table = Table(box=box.SIMPLE)
    info_table.add_column("Location", style="cyan")
    info_table.add_column("Path", style="green")

    info_table.add_row("Database", str(config.db_path))
    info_table.add_row("Data Directory", str(config.data_dir))

    console.print(info_table)

    db.close()


@stats.command()
def books():
    """Show book collection statistics."""
    config = load_config()

    console.print(Panel.fit(
        "[bold cyan]Book Collection Statistics[/bold cyan]",
        border_style="cyan"
    ))

    # Stats table
    stats_table = Table(title="Overview", box=box.ROUNDED)
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", justify="right", style="green")

    # TODO: Get actual stats from database
    stats_table.add_row("Total Books", "0")
    stats_table.add_row("With Dewey Classification", "0")
    stats_table.add_row("With Cutter Numbers", "0")
    stats_table.add_row("Missing Metadata", "0")
    stats_table.add_row("From Internet Archive", "0")
    stats_table.add_row("Linked to Calibre", "0")

    console.print(stats_table)
    console.print()

    # Top authors
    console.print("[bold]Top Authors:[/bold]")
    console.print("  (No books in collection yet)")
    console.print()

    # Top subjects/Dewey classes
    console.print("[bold]Top Subjects (Dewey Classes):[/bold]")
    console.print("  (No classifications yet)")


@stats.command()
def papers():
    """Show paper collection statistics."""
    config = load_config()

    console.print(Panel.fit(
        "[bold cyan]Paper Collection Statistics[/bold cyan]",
        border_style="cyan"
    ))

    # Stats table
    stats_table = Table(title="Overview", box=box.ROUNDED)
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", justify="right", style="green")

    # TODO: Get actual stats from database
    stats_table.add_row("Total Papers", "0")
    stats_table.add_row("With DOI", "0")
    stats_table.add_row("With arXiv ID", "0")
    stats_table.add_row("With PDF", "0")
    stats_table.add_row("Pre-LLM Era", "0")
    stats_table.add_row("Recent (2024+)", "0")

    console.print(stats_table)
    console.print()

    # Publication year distribution
    console.print("[bold]Publication Years:[/bold]")
    console.print("  (No papers in collection yet)")


@stats.command()
def links():
    """Show link collection statistics."""
    config = load_config()

    console.print(Panel.fit(
        "[bold cyan]Link Collection Statistics[/bold cyan]",
        border_style="cyan"
    ))

    # Stats table
    stats_table = Table(title="Overview", box=box.ROUNDED)
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", justify="right", style="green")

    # TODO: Get actual stats from database
    stats_table.add_row("Total Links", "0")
    stats_table.add_row("Archived (IA)", "0")
    stats_table.add_row("Pre-LLM Era", "0")
    stats_table.add_row("Trust Tier: High", "0")
    stats_table.add_row("With Tags", "0")
    stats_table.add_row("Dead Links", "0")

    console.print(stats_table)
    console.print()

    # Top domains
    console.print("[bold]Top Domains:[/bold]")
    console.print("  (No links in collection yet)")


@stats.command()
def dewey():
    """Show Dewey Decimal classification distribution."""
    config = load_config()

    console.print(Panel.fit(
        "[bold cyan]Dewey Decimal Distribution[/bold cyan]",
        border_style="cyan"
    ))

    # Main classes table
    table = Table(title="Main Classes (000-900)", box=box.ROUNDED)
    table.add_column("Class", style="cyan", no_wrap=True)
    table.add_column("Name", style="white")
    table.add_column("Count", justify="right", style="green")
    table.add_column("Bar", style="blue")

    # Dewey main classes
    main_classes = [
        ("000", "Computer Science, Information & General Works"),
        ("100", "Philosophy & Psychology"),
        ("200", "Religion"),
        ("300", "Social Sciences"),
        ("400", "Language"),
        ("500", "Science"),
        ("600", "Technology"),
        ("700", "Arts & Recreation"),
        ("800", "Literature"),
        ("900", "History & Geography"),
    ]

    # TODO: Get actual counts from database
    for code, name in main_classes:
        count = 0
        bar = "█" * (count // 2) if count > 0 else ""
        table.add_row(code, name, str(count), bar)

    console.print(table)
    console.print()

    console.print("[dim]Use 'holo books list --dewey 500' to see books in a specific class[/dim]")


@stats.command()
def cache():
    """Show cache statistics."""
    config = load_config()
    cache_dir = config.data_dir / "cache"

    console.print(Panel.fit(
        "[bold cyan]Cache Statistics[/bold cyan]",
        border_style="cyan"
    ))

    if not cache_dir.exists():
        console.print("[yellow]No cache directory found[/yellow]")
        return

    # Get stats for each API cache
    table = Table(title="API Caches", box=box.ROUNDED)
    table.add_column("API", style="cyan")
    table.add_column("Files", justify="right", style="green")
    table.add_column("Size", justify="right", style="yellow")
    table.add_column("Oldest", style="dim")

    total_files = 0
    total_size = 0

    for api_dir in cache_dir.iterdir():
        if api_dir.is_dir():
            files = list(api_dir.glob("*.json"))
            file_count = len(files)
            size = sum(f.stat().st_size for f in files)
            total_files += file_count
            total_size += size

            # Get oldest file
            if files:
                oldest = min(files, key=lambda f: f.stat().st_mtime)
                oldest_date = datetime.fromtimestamp(oldest.stat().st_mtime)
                oldest_str = oldest_date.strftime("%Y-%m-%d")
            else:
                oldest_str = "N/A"

            # Format size
            size_str = format_size(size)

            table.add_row(api_dir.name, str(file_count), size_str, oldest_str)

    console.print(table)
    console.print()

    # Totals
    console.print(f"[bold]Total:[/bold] {total_files} files, {format_size(total_size)}")
    console.print(f"[dim]Cache location: {cache_dir}[/dim]")


@stats.command()
def embeddings():
    """Show vector embedding statistics."""
    config = load_config()
    embeddings_dir = config.data_dir / "embeddings"

    console.print(Panel.fit(
        "[bold cyan]Embedding Store Statistics[/bold cyan]",
        border_style="cyan"
    ))

    if not embeddings_dir.exists():
        console.print("[yellow]No embeddings directory found[/yellow]")
        console.print("[dim]Embeddings are created when you use similarity search[/dim]")
        return

    # Try to load ChromaDB stats
    try:
        from holocene.core.embeddings import EmbeddingStore

        store = EmbeddingStore(embeddings_dir)
        collections = store.list_collections()

        if not collections:
            console.print("[yellow]No collections found[/yellow]")
            return

        # Stats table
        table = Table(title="Collections", box=box.ROUNDED)
        table.add_column("Collection", style="cyan")
        table.add_column("Items", justify="right", style="green")

        for collection_name in collections:
            stats = store.get_collection_stats(collection_name)
            table.add_row(collection_name, str(stats["count"]))

        console.print(table)

    except ImportError:
        console.print("[yellow]ChromaDB not installed[/yellow]")
        console.print("[dim]Install with: pip install chromadb sentence-transformers[/dim]")
    except Exception as e:
        console.print(f"[red]Error loading embeddings: {e}[/red]")


@stats.command()
def storage():
    """Show disk space usage."""
    config = load_config()
    data_dir = config.data_dir

    console.print(Panel.fit(
        "[bold cyan]Storage Usage[/bold cyan]",
        border_style="cyan"
    ))

    table = Table(title="Disk Usage", box=box.ROUNDED)
    table.add_column("Location", style="cyan")
    table.add_column("Size", justify="right", style="green")
    table.add_column("Files", justify="right", style="yellow")

    # Calculate sizes for each subdirectory
    locations = [
        ("Database", config.db_path),
        ("Books", data_dir / "books"),
        ("Papers", data_dir / "papers"),
        ("Research", data_dir / "research"),
        ("Cache", data_dir / "cache"),
        ("Embeddings", data_dir / "embeddings"),
    ]

    total_size = 0

    for name, path in locations:
        if not path.exists():
            table.add_row(name, "0 B", "0")
            continue

        if path.is_file():
            size = path.stat().st_size
            file_count = 1
        else:
            size, file_count = get_dir_size(path)

        total_size += size
        table.add_row(name, format_size(size), str(file_count))

    console.print(table)
    console.print()
    console.print(f"[bold]Total Storage:[/bold] {format_size(total_size)}")


def format_size(bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes < 1024.0:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.1f} PB"


def get_dir_size(path: Path) -> tuple[int, int]:
    """Get total size and file count for directory."""
    total_size = 0
    file_count = 0

    try:
        for item in path.rglob("*"):
            if item.is_file():
                total_size += item.stat().st_size
                file_count += 1
    except PermissionError:
        pass

    return total_size, file_count
