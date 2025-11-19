"""Mercado Livre <-> Inventory integration commands."""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm
from rich import box

from holocene.config import load_config
from holocene.storage.database import Database
from holocene.core.taxonomy import get_taxonomy

console = Console()


@click.group()
def ml_inventory():
    """Integrate Mercado Livre favorites with inventory."""
    pass


@ml_inventory.command()
@click.option("--enriched-only", is_flag=True, help="Only import enriched items")
@click.option("--limit", "-n", type=int, help="Limit number of items to import")
@click.option("--dry-run", is_flag=True, help="Preview without importing")
@click.option("--auto-categorize", is_flag=True, help="Use DeepSeek to suggest categories")
@click.option("--confidence-threshold", type=float, default=0.7, help="Minimum confidence for auto-category (default: 0.7)")
def import_favorites(enriched_only: bool, limit: int, dry_run: bool, auto_categorize: bool, confidence_threshold: float):
    """[DEPRECATED] Bulk import ML items. Use 'add-from-ml' instead for individual purchases."""
    config = load_config()
    db = Database(config.db_path)

    # Build query - only fetch unimported items
    query = """
        SELECT mf.* FROM mercadolivre_favorites mf
        LEFT JOIN items i ON mf.item_id = i.mercadolivre_item_id
        WHERE i.id IS NULL
    """
    params = []

    if enriched_only:
        query += " AND mf.enriched_at IS NOT NULL"

    query += " ORDER BY mf.enriched_at DESC, mf.first_synced DESC"

    if limit:
        query += " LIMIT ?"
        params.append(limit)

    # Get ML favorites
    cursor = db.conn.cursor()
    cursor.execute(query, params)

    favorites = []
    columns = [desc[0] for desc in cursor.description]
    for row in cursor.fetchall():
        favorites.append(dict(zip(columns, row)))

    if not favorites:
        console.print("[yellow]No unimported favorites found.[/yellow]")
        console.print("[dim]All favorites may already be imported, or none match the filters.[/dim]")
        db.close()
        return

    console.print(f"\n[bold cyan]Found {len(favorites)} unimported ML favorites[/bold cyan]\n")

    items_to_import = favorites

    # Preview table
    table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
    table.add_column("Title", max_width=50)
    table.add_column("Price", justify="right", width=12)
    table.add_column("Enriched", width=10)

    for fav in items_to_import[:10]:  # Show first 10
        enriched = "✓" if fav['enriched_at'] else "-"
        price_str = f"R$ {fav['price']:.2f}" if fav['price'] else "-"
        table.add_row(
            fav['title'] or "[dim]Untitled[/dim]",
            price_str,
            f"[green]{enriched}[/green]" if enriched == "✓" else f"[dim]{enriched}[/dim]"
        )

    console.print(table)

    if len(items_to_import) > 10:
        console.print(f"\n[dim]... and {len(items_to_import) - 10} more[/dim]")

    if dry_run:
        console.print("\n[yellow]Dry run - no items imported.[/yellow]")
        db.close()
        return

    # Confirm
    console.print()
    if not Confirm.ask(f"Import {len(items_to_import)} items as wishlist?"):
        console.print("[yellow]Import cancelled.[/yellow]")
        db.close()
        return

    # Auto-categorize if requested
    categorized_items = {}
    if auto_categorize:
        console.print("[cyan]Running DeepSeek categorization...[/cyan]")

        from holocene.llm.nanogpt import NanoGPTClient
        from holocene.core.categorizer import batch_suggest_categories

        llm_client = NanoGPTClient(
            api_key=config.llm.api_key,
            base_url=config.llm.base_url
        )
        taxonomy = get_taxonomy()

        # Batch categorize
        suggestions = batch_suggest_categories(
            items=[{'title': fav['title'], 'description': fav.get('description')} for fav in items_to_import],
            taxonomy=taxonomy,
            llm_client=llm_client,
            confidence_threshold=confidence_threshold,
            model=config.llm.primary
        )

        # Map suggestions to items
        for i, suggestion in enumerate(suggestions):
            if suggestion['category']:
                categorized_items[items_to_import[i]['item_id']] = suggestion

        console.print(f"[green]✓ Categorized {len([s for s in suggestions if s['category']])} items[/green]\n")

    # Import items
    console.print()
    imported = 0
    for fav in items_to_import:
        # Extract basic info
        name = fav['title']
        description = fav['description']
        price = fav['price']

        # Get category from DeepSeek if available
        category = None
        confidence = None
        reasoning = None

        if fav['item_id'] in categorized_items:
            cat_data = categorized_items[fav['item_id']]
            category = cat_data['category']
            confidence = cat_data['confidence']
            reasoning = cat_data['reasoning']

        # Create inventory item
        item_id = db.insert_item(
            name=name,
            description=description,
            category=category,
            status='wishlist',
            acquired_price=price,
            mercadolivre_item_id=fav['item_id']
        )

        # Store AI categorization metadata if present
        if category and confidence is not None:
            db.set_item_attribute(
                item_id,
                'ai_category_confidence',
                str(confidence),
                source='deepseek',
                confidence=confidence,
                confirmed=False
            )
            if reasoning:
                db.set_item_attribute(
                    item_id,
                    'ai_category_reasoning',
                    reasoning,
                    source='deepseek',
                    confirmed=False
                )

        # Add ML-specific attributes
        if fav['url']:
            db.set_item_attribute(item_id, 'ml_url', fav['url'], source='ml_import')

        if fav['thumbnail_url']:
            db.set_item_attribute(item_id, 'ml_thumbnail', fav['thumbnail_url'], source='ml_import')

        if fav['condition']:
            db.set_item_attribute(item_id, 'condition', fav['condition'], source='ml_import')

        if fav['seller_nickname']:
            db.set_item_attribute(item_id, 'seller', fav['seller_nickname'], source='ml_import')

        if fav['free_shipping']:
            db.set_item_attribute(item_id, 'free_shipping', 'yes', source='ml_import')

        imported += 1

        if imported % 50 == 0:
            console.print(f"[dim]Imported {imported}/{len(items_to_import)}...[/dim]")

    console.print(f"\n[green]✓ Imported {imported} items as wishlist![/green]")
    console.print(f"[dim]Use 'holo inventory list --status wishlist' to see them[/dim]")

    db.close()


@ml_inventory.command()
@click.argument("ml_item_id")
@click.option("--auto-categorize", is_flag=True, help="Use DeepSeek to suggest category")
def add_from_ml(ml_item_id: str, auto_categorize: bool):
    """Import a ML favorite as owned inventory item (when you buy it)."""
    config = load_config()
    db = Database(config.db_path)

    # Get ML favorite
    cursor = db.conn.cursor()
    cursor.execute("SELECT * FROM mercadolivre_favorites WHERE item_id = ?", (ml_item_id,))
    row = cursor.fetchone()

    if not row:
        console.print(f"[red]Error: ML item '{ml_item_id}' not found in favorites.[/red]")
        console.print("[dim]Sync your favorites first: holo mercadolivre sync[/dim]")
        db.close()
        return

    columns = [desc[0] for desc in cursor.description]
    fav = dict(zip(columns, row))

    # Check if already imported
    cursor.execute("SELECT id FROM items WHERE mercadolivre_item_id = ?", (ml_item_id,))
    existing = cursor.fetchone()

    if existing:
        console.print(f"[yellow]Item already in inventory (#{existing[0]})[/yellow]")
        db.close()
        return

    # Auto-categorize if requested
    category = None
    confidence = None
    reasoning = None

    if auto_categorize:
        console.print("[cyan]Running DeepSeek categorization...[/cyan]")

        from holocene.llm.nanogpt import NanoGPTClient
        from holocene.core.categorizer import suggest_category

        llm_client = NanoGPTClient(
            api_key=config.llm.api_key,
            base_url=config.llm.base_url
        )
        taxonomy = get_taxonomy()

        category, confidence, reasoning = suggest_category(
            title=fav['title'],
            description=fav.get('description'),
            taxonomy=taxonomy,
            llm_client=llm_client,
            model=config.llm.primary
        )

        if category:
            cat_info = taxonomy.get_category_info(category)
            console.print(f"[green]✓ Suggested: {category} ({cat_info['label']}) - {confidence:.0%} confidence[/green]")
            console.print(f"[dim]  {reasoning}[/dim]\n")

    # Create inventory item as OWNED
    item_id = db.insert_item(
        name=fav['title'],
        description=fav.get('description'),
        category=category,
        status='owned',
        acquired_price=fav.get('price'),
        mercadolivre_item_id=ml_item_id
    )

    # Store AI metadata if present
    if category and confidence is not None:
        db.set_item_attribute(item_id, 'ai_category_confidence', str(confidence),
                             source='deepseek', confidence=confidence, confirmed=False)
        if reasoning:
            db.set_item_attribute(item_id, 'ai_category_reasoning', reasoning,
                                 source='deepseek', confirmed=False)

    # Add ML attributes
    if fav.get('url'):
        db.set_item_attribute(item_id, 'ml_url', fav['url'], source='ml_import')
    if fav.get('thumbnail_url'):
        db.set_item_attribute(item_id, 'ml_thumbnail', fav['thumbnail_url'], source='ml_import')

    console.print(f"[green]✓ Added to inventory (#{item_id}):[/green] {fav['title']}")
    console.print(f"[dim]Price: R$ {fav.get('price', 0):.2f}[/dim]")

    db.close()


@ml_inventory.command()
def stats():
    """Show ML <-> inventory statistics."""
    config = load_config()
    db = Database(config.db_path)

    cursor = db.conn.cursor()

    # Total ML favorites
    cursor.execute("SELECT COUNT(*) FROM mercadolivre_favorites")
    total_ml = cursor.fetchone()[0]

    # Enriched ML favorites
    cursor.execute("SELECT COUNT(*) FROM mercadolivre_favorites WHERE enriched_at IS NOT NULL")
    enriched_ml = cursor.fetchone()[0]

    # Imported to inventory
    cursor.execute("SELECT COUNT(*) FROM items WHERE mercadolivre_item_id IS NOT NULL")
    imported = cursor.fetchone()[0]

    # Wishlist
    cursor.execute("SELECT COUNT(*) FROM items WHERE status = 'wishlist'")
    wishlist = cursor.fetchone()[0]

    # Owned
    cursor.execute("SELECT COUNT(*) FROM items WHERE status = 'owned'")
    owned = cursor.fetchone()[0]

    # Display
    console.print(Panel.fit(
        "[bold cyan]Mercado Livre ↔ Inventory Stats[/bold cyan]",
        border_style="cyan"
    ))

    table = Table(show_header=False, box=box.SIMPLE)
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right", style="white")

    table.add_row("ML Favorites (total)", str(total_ml))
    table.add_row("ML Favorites (enriched)", str(enriched_ml))
    table.add_row("", "")
    table.add_row("Imported to inventory", str(imported))
    table.add_row("Wishlist items", str(wishlist))
    table.add_row("Owned items", str(owned))

    console.print(table)
    console.print()

    # Show workflow hint
    console.print(f"\n[dim]💡 When you buy a ML favorite, add it:[/dim]")
    console.print(f"[dim]   holo ml-inventory add-from-ml MLB123456 --auto-categorize[/dim]")

    db.close()
