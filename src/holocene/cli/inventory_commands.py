"""Inventory management CLI commands."""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from holocene.config import load_config
from holocene.storage.database import Database
from holocene.core.taxonomy import get_taxonomy

console = Console()


@click.group()
def inventory():
    """Manage inventory items (tools, components, materials)."""
    pass


@inventory.command()
@click.argument("name")
@click.option("--description", "-d", help="Freeform description")
@click.option("--category", "-c", help="Category (e.g., 'tools-measurement-caliper' or 'T-MEAS-CAL')")
@click.option("--location", "-l", help="Where it's stored")
@click.option("--quantity", "-q", type=float, help="Quantity")
@click.option("--unit", "-u", help="Unit (pcs, kg, m, L, etc.)")
@click.option("--price", "-p", type=float, help="Acquired price")
@click.option("--photo", help="Path to photo")
def add(name: str, description: str, category: str, location: str,
        quantity: float, unit: str, price: float, photo: str):
    """Add a new item to inventory."""
    config = load_config()
    db = Database(config.db_path)
    taxonomy = get_taxonomy()

    # Normalize category if provided
    canonical_category = None
    if category:
        canonical_category = taxonomy.normalize_category(category)
        if canonical_category:
            cat_info = taxonomy.get_category_info(canonical_category)
            if cat_info:
                console.print(f"[dim]→ Category: {canonical_category} ({cat_info['label']})[/dim]")
        else:
            console.print(f"[yellow]⚠ Category '{category}' not recognized in taxonomy[/yellow]")
            console.print("[yellow]  Will store as-is. Use 'holo inventory categories' to browse.[/yellow]")
            canonical_category = category

    item_id = db.insert_item(
        name=name,
        description=description,
        category=canonical_category,
        location=location,
        quantity=quantity,
        unit=unit,
        acquired_price=price,
        photo_path=photo,
    )

    console.print(f"\n[green]✓ Added item #{item_id}:[/green] {name}")

    if canonical_category:
        console.print(f"  Category: {canonical_category}")
    if location:
        console.print(f"  Location: {location}")
    if quantity:
        console.print(f"  Quantity: {quantity} {unit or 'units'}")

    db.close()


@inventory.command("list")
@click.option("--category", "-c", help="Filter by category")
@click.option("--status", "-s", help="Filter by status (owned, wishlist, etc.)")
@click.option("--location", "-l", help="Filter by location")
@click.option("--limit", "-n", type=int, default=50, help="Max results")
def list_items(category: str, status: str, location: str, limit: int):
    """List inventory items."""
    config = load_config()
    db = Database(config.db_path)

    items = db.get_items(
        category=category,
        status=status,
        location=location,
        limit=limit,
    )

    if not items:
        console.print("[yellow]No items found.[/yellow]")
        console.print("\nAdd your first item: [cyan]holo inventory add \"Mitutoyo caliper\"[/cyan]")
        db.close()
        return

    # Create table
    table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
    table.add_column("ID", style="dim", width=6)
    table.add_column("Name", max_width=40)
    table.add_column("Category", width=15)
    table.add_column("Location", width=20)
    table.add_column("Qty", justify="right", width=8)
    table.add_column("Status", width=10)

    for item in items:
        qty_str = ""
        if item['quantity']:
            qty_str = f"{item['quantity']}"
            if item['unit']:
                qty_str += f" {item['unit']}"

        status_color = {
            'owned': 'green',
            'wishlist': 'yellow',
            'on_loan': 'blue',
            'broken': 'red',
            'sold': 'dim'
        }.get(item['status'], 'white')

        table.add_row(
            str(item['id']),
            item['name'] or "[dim]Untitled[/dim]",
            item['category'] or "[dim]-[/dim]",
            item['location'] or "[dim]-[/dim]",
            qty_str,
            f"[{status_color}]{item['status']}[/{status_color}]",
        )

    console.print(table)
    console.print(f"\n[dim]Showing {len(items)} item(s)[/dim]")

    db.close()


@inventory.command()
@click.argument("item_id", type=int)
def show(item_id: int):
    """Show details for an item."""
    config = load_config()
    db = Database(config.db_path)

    item = db.get_item(item_id)

    if not item:
        console.print(f"[red]Error: Item #{item_id} not found.[/red]")
        db.close()
        return

    # Display details
    console.print(Panel.fit(
        f"[bold cyan]{item['name'] or 'Untitled Item'}[/bold cyan]",
        border_style="cyan"
    ))

    # Main details
    details = Table(show_header=False, box=box.SIMPLE)
    details.add_column("Field", style="cyan")
    details.add_column("Value", style="white")

    details.add_row("ID", str(item['id']))

    if item['category']:
        details.add_row("Category", item['category'])

    if item['description']:
        details.add_row("Description", item['description'])

    details.add_row("Status", item['status'])

    if item['location']:
        details.add_row("Location", item['location'])

    if item['quantity']:
        qty_str = str(item['quantity'])
        if item['unit']:
            qty_str += f" {item['unit']}"
        details.add_row("Quantity", qty_str)

    if item['acquired_price']:
        details.add_row("Acquired Price", f"R$ {item['acquired_price']:.2f}")

    if item['current_value']:
        details.add_row("Current Value", f"R$ {item['current_value']:.2f}")

    if item['acquired_date']:
        details.add_row("Acquired", item['acquired_date'])

    if item['photo_path']:
        details.add_row("Photo", item['photo_path'])

    console.print(details)

    # Show attributes
    attrs = db.get_item_attributes(item_id)
    if attrs:
        console.print("\n[bold cyan]Attributes:[/bold cyan]")
        for key, value in attrs.items():
            console.print(f"  {key}: {value}")

    # Show tags
    tags = db.get_item_tags(item_id)
    if tags:
        console.print(f"\n[bold cyan]Tags:[/bold cyan] {', '.join(tags)}")

    db.close()


@inventory.command()
@click.argument("item_id", type=int)
@click.argument("key")
@click.argument("value")
def attr_set(item_id: int, key: str, value: str):
    """Set an attribute on an item (EAV)."""
    config = load_config()
    db = Database(config.db_path)

    # Check if item exists
    item = db.get_item(item_id)
    if not item:
        console.print(f"[red]Error: Item #{item_id} not found.[/red]")
        db.close()
        return

    db.set_item_attribute(item_id, key, value)
    console.print(f"[green]✓ Set {key} = {value} for item #{item_id}[/green]")

    db.close()


@inventory.command()
@click.argument("item_id", type=int)
@click.argument("tag")
def tag(item_id: int, tag: str):
    """Add a tag to an item."""
    config = load_config()
    db = Database(config.db_path)

    # Check if item exists
    item = db.get_item(item_id)
    if not item:
        console.print(f"[red]Error: Item #{item_id} not found.[/red]")
        db.close()
        return

    db.add_item_tag(item_id, tag)
    console.print(f"[green]✓ Added tag '{tag}' to item #{item_id}[/green]")

    db.close()


@inventory.command()
@click.argument("item_id", type=int)
@click.option("--name", help="New name")
@click.option("--description", "-d", help="New description")
@click.option("--category", "-c", help="New category")
@click.option("--location", "-l", help="New location")
@click.option("--quantity", "-q", type=float, help="New quantity")
@click.option("--status", "-s", help="New status (owned, wishlist, etc.)")
def edit(item_id: int, **kwargs):
    """Edit an item."""
    config = load_config()
    db = Database(config.db_path)

    # Check if item exists
    item = db.get_item(item_id)
    if not item:
        console.print(f"[red]Error: Item #{item_id} not found.[/red]")
        db.close()
        return

    # Filter out None values
    updates = {k: v for k, v in kwargs.items() if v is not None}

    if not updates:
        console.print("[yellow]No changes specified.[/yellow]")
        db.close()
        return

    db.update_item(item_id, **updates)
    console.print(f"[green]✓ Updated item #{item_id}[/green]")

    for key, value in updates.items():
        console.print(f"  {key}: {value}")

    db.close()


@inventory.command()
@click.argument("item_id", type=int)
@click.confirmation_option(prompt="Are you sure you want to delete this item?")
def delete(item_id: int):
    """Delete an item from inventory."""
    config = load_config()
    db = Database(config.db_path)

    # Check if item exists
    item = db.get_item(item_id)
    if not item:
        console.print(f"[red]Error: Item #{item_id} not found.[/red]")
        db.close()
        return

    db.delete_item(item_id)
    console.print(f"[green]✓ Deleted item #{item_id}: {item['name']}[/green]")

    db.close()


@inventory.command()
@click.option("--search", "-s", help="Search categories by name/alias")
@click.option("--show", help="Show specific category tree (e.g., 'T' or 'T-MEAS')")
def categories(search: str, show: str):
    """Browse inventory categories."""
    taxonomy = get_taxonomy()

    if search:
        # Search and display results
        results = taxonomy.search_categories(search)

        if not results:
            console.print(f"[yellow]No categories found matching '{search}'[/yellow]")
            return

        table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
        table.add_column("Code", style="cyan", width=20)
        table.add_column("Label", width=40)

        for code, label in results:
            table.add_row(code, label)

        console.print(f"\n[bold]Search results for '{search}':[/bold]\n")
        console.print(table)
        console.print(f"\n[dim]Found {len(results)} categor{'y' if len(results) == 1 else 'ies'}[/dim]")

    elif show:
        # Show specific category tree
        show_upper = show.upper()
        cat_info = taxonomy.get_category_info(show_upper)

        if not cat_info:
            console.print(f"[red]Error: Category '{show}' not found.[/red]")
            console.print("[dim]Try browsing all categories with: holo inventory categories[/dim]")
            return

        console.print(Panel.fit(
            f"[bold cyan]{show_upper}[/bold cyan]: {cat_info['label']}",
            border_style="cyan"
        ))

        if cat_info['description']:
            console.print(f"\n[dim]{cat_info['description']}[/dim]\n")

        # Show aliases
        if cat_info['aliases']:
            console.print(f"[cyan]Aliases:[/cyan] {', '.join(cat_info['aliases'])}\n")

        # Show external references
        refs = []
        if cat_info['wikipedia']:
            refs.append(f"Wikipedia: {cat_info['wikipedia']}")
        if cat_info['wikidata']:
            refs.append(f"Wikidata: {cat_info['wikidata']}")
        if cat_info['schema_org']:
            refs.append(f"Schema.org: {cat_info['schema_org']}")

        if refs:
            console.print("[cyan]References:[/cyan]")
            for ref in refs:
                console.print(f"  [dim]{ref}[/dim]")
            console.print()

        # Show children if any
        children = taxonomy.get_children(show_upper)
        if children:
            console.print("[bold cyan]Subcategories:[/bold cyan]\n")
            table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
            table.add_column("Code", style="cyan", width=20)
            table.add_column("Label", width=40)

            for code, label in children:
                table.add_row(code, label)

            console.print(table)

    else:
        # Show root categories
        console.print(Panel.fit(
            "[bold cyan]Holocene Inventory Taxonomy[/bold cyan]\n"
            "[dim]CC0 1.0 Universal (Public Domain)[/dim]",
            border_style="cyan"
        ))

        console.print("\n[bold]Root Categories:[/bold]\n")

        root_cats = [(code, data) for code, data in taxonomy.canonical_map.items() if '-' not in code]

        table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
        table.add_column("Code", style="cyan", width=10)
        table.add_column("Label", width=30)
        table.add_column("Description", style="dim", width=50)

        for code, data in sorted(root_cats):
            table.add_row(
                code,
                data['label'],
                data['description'] or ""
            )

        console.print(table)

        console.print("\n[dim]Usage:[/dim]")
        console.print("  [cyan]holo inventory categories --show T[/cyan]        # Show Tools category tree")
        console.print("  [cyan]holo inventory categories --search caliper[/cyan] # Search for categories")
        console.print("  [cyan]holo inventory add --category T-MEAS-CAL[/cyan]  # Use category code")
        console.print("  [cyan]holo inventory add --category tools-measurement-caliper[/cyan]  # Or freeform")
