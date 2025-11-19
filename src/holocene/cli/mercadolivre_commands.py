"""Mercado Livre integration CLI commands."""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box
from pathlib import Path

from holocene.config import load_config, save_config
from holocene.storage.database import Database
from holocene.integrations.apify import ApifyClient
from holocene.integrations.http_fetcher import HTTPFetcher
import time
import random

console = Console()


@click.group()
def mercadolivre():
    """Manage Mercado Livre favorites."""
    pass


@mercadolivre.command()
def status():
    """Check Mercado Livre authentication status."""
    config = load_config()

    console.print(Panel.fit(
        "[bold cyan]Mercado Livre Integration Status[/bold cyan]",
        border_style="cyan"
    ))

    # Check if integration is configured
    ml_config = getattr(config, 'mercadolivre', None)

    if not ml_config:
        console.print("\n[yellow]Mercado Livre integration not configured.[/yellow]")
        console.print("\nTo set up:")
        console.print("  1. Create an app at: https://developers.mercadolivre.com.br")
        console.print("  2. Get your client_id and client_secret")
        console.print("  3. Run: [cyan]holo mercadolivre auth[/cyan]")
        return

    # Check if authenticated
    has_token = hasattr(ml_config, 'access_token') and ml_config.access_token

    if has_token:
        console.print("\n[green]✓ Authenticated[/green]")

        # Check token expiration
        if hasattr(ml_config, 'token_expires_at'):
            console.print(f"[dim]Token expires: {ml_config.token_expires_at}[/dim]")
    else:
        console.print("\n[yellow]✗ Not authenticated[/yellow]")
        console.print("\nRun: [cyan]holo mercadolivre auth[/cyan]")


@mercadolivre.command()
@click.option("--manual", is_flag=True, help="Use manual OAuth flow (recommended)")
def auth(manual: bool):
    """Authenticate with Mercado Livre (OAuth 2.0)."""
    from holocene.integrations.mercadolivre import MercadoLivreOAuth

    config = load_config()

    console.print(Panel.fit(
        "[bold cyan]Mercado Livre OAuth Setup[/bold cyan]",
        border_style="cyan"
    ))

    # Check for config
    ml_config = getattr(config, 'mercadolivre', None)

    if not ml_config or not hasattr(ml_config, 'client_id'):
        console.print("\n[red]Error: Mercado Livre not configured.[/red]")
        console.print("\nAdd to ~/.config/holocene/config.yml:")
        console.print("""
[cyan]mercadolivre:
  enabled: true
  client_id: "YOUR_CLIENT_ID"
  client_secret: "YOUR_CLIENT_SECRET"
  redirect_uri: "https://google.com"  # Use any HTTPS URL for manual flow[/cyan]
""")
        console.print("Get credentials at: https://developers.mercadolivre.com.br")
        return

    # Use manual flow by default (HTTPS requirement workaround)
    if manual or not hasattr(ml_config, 'redirect_uri') or 'localhost' in ml_config.redirect_uri:
        # Manual OAuth flow
        redirect_uri = getattr(ml_config, 'redirect_uri', 'https://google.com')

        oauth = MercadoLivreOAuth(
            client_id=ml_config.client_id,
            client_secret=ml_config.client_secret,
            redirect_uri=redirect_uri,
        )

        auth_url = oauth.get_authorization_url()

        console.print("\n[bold yellow]Manual OAuth Flow[/bold yellow]")
        console.print("(Required because Mercado Livre requires HTTPS redirect URIs)\n")

        console.print("[bold]Step 1:[/bold] Open this URL in your browser:")
        console.print(f"\n[cyan]{auth_url}[/cyan]\n")

        console.print("[bold]Step 2:[/bold] After authorizing, Mercado Livre will redirect to:")
        console.print(f"  {redirect_uri}?code=TG-...")
        console.print("\n[bold]Step 3:[/bold] Paste the full redirect URL or just the code")
        console.print("  Full URL: [dim]https://core.stdgeo.com/dummy?code=TG-abc123xyz[/dim]")
        console.print("  Or just: [yellow]TG-abc123xyz[/yellow]\n")

        code_or_url = click.prompt("Authorization code or URL", type=str).strip()

        # Extract code from URL if full URL was provided
        if code_or_url.startswith("http"):
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(code_or_url)
            query_params = parse_qs(parsed.query)
            if "code" in query_params:
                code = query_params["code"][0]
                console.print(f"[dim]Extracted code: {code}[/dim]\n")
            else:
                console.print("[red]Error: No 'code' parameter found in URL[/red]")
                return
        else:
            code = code_or_url

    else:
        # Standard OAuth flow (requires HTTPS or localhost HTTPS)
        oauth = MercadoLivreOAuth(
            client_id=ml_config.client_id,
            client_secret=ml_config.client_secret,
            redirect_uri=ml_config.redirect_uri,
        )

        auth_url = oauth.get_authorization_url()

        console.print("\n[bold]Step 1:[/bold] Open this URL in your browser:")
        console.print(f"\n[cyan]{auth_url}[/cyan]\n")

        console.print("[bold]Step 2:[/bold] After authorizing, you'll be redirected to:")
        console.print(f"  {ml_config.redirect_uri}?code=...")
        console.print("\n[bold]Step 3:[/bold] Paste the full redirect URL or just the code\n")

        code_or_url = click.prompt("Authorization code or URL", type=str).strip()

        # Extract code from URL if full URL was provided
        if code_or_url.startswith("http"):
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(code_or_url)
            query_params = parse_qs(parsed.query)
            if "code" in query_params:
                code = query_params["code"][0]
                console.print(f"[dim]Extracted code: {code}[/dim]\n")
            else:
                console.print("[red]Error: No 'code' parameter found in URL[/red]")
                return
        else:
            code = code_or_url

    # Exchange code for token
    with console.status("[cyan]Exchanging code for access token...", spinner="dots"):
        try:
            token_data = oauth.exchange_code_for_token(code)

            # Save to config
            ml_config.access_token = token_data["access_token"]
            if "refresh_token" in token_data:
                ml_config.refresh_token = token_data["refresh_token"]

            # Calculate expiration
            from datetime import datetime, timedelta
            expires_in = token_data.get("expires_in", 21600)  # Default 6 hours
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            ml_config.token_expires_at = expires_at.isoformat()

            save_config(config)

            console.print("\n[green]✓ Successfully authenticated![/green]")
            console.print(f"[dim]Token expires in {expires_in // 3600} hours[/dim]")
            console.print(f"[dim]Refresh token saved - will auto-refresh when needed[/dim]")

        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
            console.print("[yellow]Make sure your client ID/secret are correct.[/yellow]")
            console.print("[yellow]Check that you copied the FULL authorization code.[/yellow]")


@mercadolivre.command()
def sync():
    """Sync favorites from Mercado Livre."""
    from holocene.integrations.mercadolivre import MercadoLivreClient

    config = load_config()
    ml_config = getattr(config, 'mercadolivre', None)

    if not ml_config or not hasattr(ml_config, 'access_token'):
        console.print("[red]Error: Not authenticated with Mercado Livre.[/red]")
        console.print("Run: [cyan]holo mercadolivre auth[/cyan]")
        return

    db = Database(config.db_path)

    with console.status("[cyan]Fetching favorites from Mercado Livre...", spinner="dots"):
        try:
            client = MercadoLivreClient(ml_config.access_token)
            favorites = client.sync_favorites()

            new_count = 0
            updated_count = 0

            for item in favorites:
                existing = db.get_mercadolivre_favorite(item["item_id"])

                db.insert_mercadolivre_favorite(
                    item_id=item["item_id"],
                    title=item.get("title"),
                    price=item.get("price"),
                    currency=item.get("currency"),
                    category_id=item.get("category_id"),
                    category_name=item.get("category_name"),
                    url=item.get("url"),
                    thumbnail_url=item.get("thumbnail"),
                    condition=item.get("condition"),
                    available_quantity=item.get("available_quantity"),
                    bookmarked_date=item.get("bookmarked_date"),
                    is_available=item.get("is_available", True),
                )

                if existing:
                    updated_count += 1
                else:
                    new_count += 1

            console.print(f"\n[green]✓ Synced {len(favorites)} favorites[/green]")
            console.print(f"  [cyan]{new_count} new[/cyan], [yellow]{updated_count} updated[/yellow]")

        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
            console.print("[yellow]Your access token may have expired.[/yellow]")
            console.print("Try: [cyan]holo mercadolivre auth[/cyan]")

    db.close()


@mercadolivre.command()
@click.argument("json_file", type=click.Path(exists=True))
def import_json(json_file: str):
    """Import favorites from exported JSON file (from Tampermonkey script)."""
    import json
    from pathlib import Path
    from datetime import datetime

    config = load_config()
    db = Database(config.db_path)

    json_path = Path(json_file)

    with console.status(f"[cyan]Loading {json_path.name}...", spinner="dots"):
        with open(json_path, 'r', encoding='utf-8') as f:
            favorites = json.load(f)

    if not favorites:
        console.print("[yellow]No favorites found in JSON file.[/yellow]")
        db.close()
        return

    console.print(f"\n[cyan]Importing {len(favorites)} favorites from {json_path.name}...[/cyan]\n")

    new_count = 0
    updated_count = 0

    for item in favorites:
        # Check if exists
        existing = db.get_mercadolivre_favorite(item["item_id"])

        # Insert/update in database
        db.insert_mercadolivre_favorite(
            item_id=item["item_id"],
            title=item.get("title"),
            price=item.get("price"),
            currency=item.get("currency"),
            url=item.get("permalink"),
            thumbnail_url=f"https://http2.mlstatic.com/D_NQ_NP_2X_{item.get('thumbnail_id')}-F.webp" if item.get("thumbnail_id") else None,
            condition=item.get("condition"),
            bookmarked_date=item.get("collected_at"),
            is_available=True,  # Assume available since it was in their favorites
        )

        if existing:
            updated_count += 1
        else:
            new_count += 1

    console.print(f"\n[green]✓ Imported {len(favorites)} favorites[/green]")
    console.print(f"  [cyan]{new_count} new[/cyan], [yellow]{updated_count} updated[/yellow]")

    console.print("\n[dim]Next steps:[/dim]")
    console.print("  [cyan]holo mercadolivre list[/cyan] - View imported favorites")
    console.print("  [cyan]holo mercadolivre classify --all[/cyan] - Classify with Extended Dewey")

    db.close()


@mercadolivre.command("list")
@click.option("--category", "-c", help="Filter by category")
@click.option("--available/--all", default=True, help="Show only available items")
@click.option("--limit", "-n", type=int, default=50, help="Limit number of results")
def list_favorites(category: str, available: bool, limit: int):
    """List synced Mercado Livre favorites."""
    config = load_config()
    db = Database(config.db_path)

    favorites = db.get_mercadolivre_favorites(
        category=category,
        available_only=available,
        limit=limit,
    )

    if not favorites:
        console.print("[yellow]No favorites found.[/yellow]")
        console.print("Run: [cyan]holo mercadolivre sync[/cyan]")
        db.close()
        return

    # Create table
    table = Table(show_header=True, header_style="bold cyan", box=box.ROUNDED)
    table.add_column("ID", style="dim", width=15)
    table.add_column("Title", max_width=40)
    table.add_column("Price", justify="right", width=12)
    table.add_column("Category", width=20)
    table.add_column("Status", width=10)

    for fav in favorites:
        # Format price
        price_str = f"{fav['currency']} {fav['price']:.2f}" if fav['price'] else "N/A"

        # Status indicator
        if fav['is_available']:
            status = "[green]✓ Available[/green]"
        else:
            status = "[red]✗ Unavailable[/red]"

        table.add_row(
            fav['item_id'],
            fav['title'] or "[dim]No title[/dim]",
            price_str,
            fav['category_name'] or "[dim]Unknown[/dim]",
            status,
        )

    console.print(table)
    console.print(f"\n[dim]Showing {len(favorites)} favorite(s)[/dim]")

    db.close()


@mercadolivre.command()
@click.argument("item_id")
def show(item_id: str):
    """Show details for a specific favorite."""
    config = load_config()
    db = Database(config.db_path)

    favorite = db.get_mercadolivre_favorite(item_id)

    if not favorite:
        console.print(f"[red]Error: Favorite {item_id} not found.[/red]")
        console.print("Run: [cyan]holo mercadolivre list[/cyan]")
        db.close()
        return

    # Display details
    console.print(Panel.fit(
        f"[bold cyan]{favorite['title'] or 'Untitled'}[/bold cyan]",
        border_style="cyan"
    ))

    # Details table
    details = Table(show_header=False, box=box.SIMPLE)
    details.add_column("Field", style="cyan")
    details.add_column("Value", style="white")

    details.add_row("Item ID", favorite['item_id'])
    if favorite['price']:
        details.add_row("Price", f"{favorite['currency']} {favorite['price']:.2f}")
    details.add_row("Category", favorite['category_name'] or "Unknown")
    details.add_row("Condition", favorite['condition'] or "N/A")
    details.add_row("Available", "Yes" if favorite['is_available'] else "No")
    if favorite['bookmarked_date']:
        details.add_row("Bookmarked", favorite['bookmarked_date'])
    if favorite['url']:
        details.add_row("URL", favorite['url'])
    if favorite['user_notes']:
        details.add_row("Notes", favorite['user_notes'])

    console.print(details)

    db.close()


@mercadolivre.command()
@click.argument("item_id")
@click.argument("notes")
def note(item_id: str, notes: str):
    """Add notes to a favorite."""
    config = load_config()
    db = Database(config.db_path)

    # Check if exists
    favorite = db.get_mercadolivre_favorite(item_id)
    if not favorite:
        console.print(f"[red]Error: Favorite {item_id} not found.[/red]")
        db.close()
        return

    db.update_mercadolivre_favorite_notes(item_id, notes)
    console.print(f"[green]✓ Added notes to {item_id}[/green]")

    db.close()


@mercadolivre.command()
@click.option("--all", "enrich_all", is_flag=True, help="Enrich all favorites")
@click.option("--delay", type=float, default=7.0, help="Delay between requests in seconds (default: 7.0)")
@click.option("--batch-size", type=int, default=50, help="Items per batch before long break (default: 50)")
@click.option("--batch-break", type=float, default=30.0, help="Break between batches in seconds (default: 30)")
@click.option("--limit", "-n", type=int, help="Limit number of items to enrich")
@click.argument("item_id", required=False)
def enrich(item_id: str, enrich_all: bool, delay: float, batch_size: int, batch_break: float, limit: int):
    """Fetch detailed product info from Mercado Livre pages."""
    from holocene.integrations.mercadolivre import fetch_product_page
    import json as jsonlib
    import random
    import time

    config = load_config()
    db = Database(config.db_path)

    # Get items to enrich - SKIP ALREADY ENRICHED
    if enrich_all:
        cursor = db.conn.cursor()
        cursor.execute("""
            SELECT * FROM mercadolivre_favorites
            WHERE enriched_at IS NULL
            ORDER BY bookmarked_date DESC
            LIMIT ?
        """, (limit if limit else 999999,))
        favorites = [dict(row) for row in cursor.fetchall()]
    elif item_id:
        fav = db.get_mercadolivre_favorite(item_id)
        favorites = [fav] if fav else []
    else:
        console.print("[red]Error: Specify --all or provide an item_id[/red]")
        db.close()
        return

    if not favorites:
        console.print("[green]✓ All favorites already enriched![/green]")
        db.close()
        return

    # Add enriched columns if they don't exist
    cursor = db.conn.cursor()
    columns_to_add = [
        ("description", "TEXT"),
        ("original_price", "REAL"),
        ("specifications", "TEXT"),  # JSON
        ("seller_nickname", "TEXT"),
        ("seller_reputation", "TEXT"),
        ("reviews_rating", "REAL"),
        ("reviews_total", "INTEGER"),
        ("warranty", "TEXT"),
        ("free_shipping", "BOOLEAN"),
        ("enriched_at", "TEXT"),
    ]

    for col_name, col_type in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE mercadolivre_favorites ADD COLUMN {col_name} {col_type}")
        except Exception:
            pass  # Column already exists

    db.conn.commit()

    console.print(f"\n[cyan]Enriching {len(favorites)} favorite(s)...[/cyan]")
    console.print(f"[dim]Delay: {delay}s ± 2s between requests[/dim]")
    console.print(f"[dim]Batch size: {batch_size} items, then {batch_break}s break[/dim]\n")

    enriched_count = 0
    failed_count = 0

    for idx, fav in enumerate(favorites, 1):
        # Batch break
        if idx > 1 and (idx - 1) % batch_size == 0:
            console.print(f"\n[yellow]Taking {batch_break}s break after {batch_size} items...[/yellow]\n")
            time.sleep(batch_break)
        # Skip if no URL
        if not fav.get('url'):
            console.print(f"[yellow]✗ Skipped {fav['item_id']}: No URL[/yellow]")
            continue

        console.print(f"[cyan][{idx}/{len(favorites)}][/cyan] {fav['title'][:60]}...")

        try:
            # Fetch and parse product page with randomized delay
            actual_delay = delay + random.uniform(-2, 2)  # ±2s jitter
            with console.status("[dim]Fetching...", spinner="dots"):
                enriched_data = fetch_product_page(fav['url'], delay=actual_delay)

            # Update database
            specs_json = jsonlib.dumps(enriched_data.get('specifications')) if enriched_data.get('specifications') else None
            seller_info = enriched_data.get('seller_info', {})
            reviews = enriched_data.get('reviews', {})
            shipping = enriched_data.get('shipping', {})

            cursor.execute(
                """
                UPDATE mercadolivre_favorites
                SET description = ?,
                    original_price = ?,
                    specifications = ?,
                    seller_nickname = ?,
                    seller_reputation = ?,
                    reviews_rating = ?,
                    reviews_total = ?,
                    warranty = ?,
                    free_shipping = ?,
                    enriched_at = ?
                WHERE item_id = ?
                """,
                (
                    enriched_data.get('description'),
                    enriched_data.get('original_price'),
                    specs_json,
                    seller_info.get('nickname'),
                    seller_info.get('reputation_level'),
                    reviews.get('rating_average'),
                    reviews.get('total'),
                    enriched_data.get('warranty'),
                    1 if shipping.get('free_shipping') else 0,
                    enriched_data.get('fetched_at'),
                    fav['item_id'],
                ),
            )
            db.conn.commit()

            console.print(f"  [green]✓[/green] Enriched")
            if enriched_data.get('original_price') and enriched_data.get('price'):
                discount = (1 - enriched_data['price'] / enriched_data['original_price']) * 100
                if discount > 0:
                    console.print(f"    [yellow]{discount:.0f}% off[/yellow] (was R$ {enriched_data['original_price']:.2f})")
            if reviews.get('rating_average'):
                console.print(f"    [cyan]Rating: {reviews['rating_average']:.1f}[/cyan] ({reviews.get('total', 0)} reviews)")

            enriched_count += 1

        except Exception as e:
            console.print(f"  [red]✗ Failed: {e}[/red]")
            failed_count += 1

    console.print(f"\n[green]✓ Enriched {enriched_count}/{len(favorites)} favorites[/green]")
    if failed_count > 0:
        console.print(f"[yellow]⚠ {failed_count} failed[/yellow]")

    console.print("\n[dim]Next steps:[/dim]")
    console.print("  [cyan]holo mercadolivre classify --all[/cyan] - Classify with enriched descriptions")

    db.close()


@mercadolivre.command()
@click.option("--all", "classify_all", is_flag=True, help="Classify all favorites")
@click.argument("item_id", required=False)
def classify(item_id: str, classify_all: bool):
    """Classify favorites using Extended Dewey (W prefix)."""
    from holocene.research.extended_dewey import ExtendedDeweyClassifier

    config = load_config()
    db = Database(config.db_path)

    classifier = ExtendedDeweyClassifier()

    # Get items to classify
    if classify_all:
        favorites = db.get_mercadolivre_favorites()
    elif item_id:
        fav = db.get_mercadolivre_favorite(item_id)
        favorites = [fav] if fav else []
    else:
        console.print("[red]Error: Specify --all or provide an item_id[/red]")
        db.close()
        return

    if not favorites:
        console.print("[yellow]No favorites to classify.[/yellow]")
        db.close()
        return

    console.print(f"\n[cyan]Classifying {len(favorites)} favorite(s)...[/cyan]\n")

    classified_count = 0

    for fav in favorites:
        with console.status(f"[cyan]Classifying {fav['title'][:40]}...", spinner="dots"):
            try:
                result = classifier.classify_marketplace_item(
                    title=fav['title'],
                    price=fav.get('price'),
                    category=fav.get('category_name'),
                    condition=fav.get('condition'),
                )

                if 'error' not in result:
                    # Update database
                    cursor = db.conn.cursor()
                    cursor.execute(
                        """
                        UPDATE mercadolivre_favorites
                        SET dewey_class = ?, call_number = ?
                        WHERE item_id = ?
                        """,
                        (
                            result['dewey_number'],
                            result.get('call_number'),
                            fav['item_id'],
                        ),
                    )
                    db.conn.commit()

                    console.print(f"[green]✓[/green] {fav['title'][:50]}")
                    console.print(f"  [cyan]{result['dewey_number']}[/cyan] - {result['dewey_label']}")
                    if result.get('call_number'):
                        console.print(f"  Call Number: [yellow]{result['call_number']}[/yellow]")
                    console.print(f"  Confidence: {result['confidence']}\n")

                    classified_count += 1
                else:
                    console.print(f"[red]✗[/red] Failed: {fav['title'][:50]}")
                    console.print(f"  {result['error']}\n")

            except Exception as e:
                console.print(f"[red]✗ Error classifying {fav['title'][:50]}: {e}[/red]\n")

    console.print(f"\n[green]✓ Classified {classified_count}/{len(favorites)} favorites[/green]")

    db.close()


@mercadolivre.command()
@click.option("--limit", "-n", type=int, help="Limit number of items to enrich")
@click.option("--dry-run", is_flag=True, help="Preview without running")
def enrich_apify(limit: int, dry_run: bool):
    """Enrich ML favorites using Apify scraper ($0.50/1K items)."""
    config = load_config()
    db = Database(config.db_path)

    # Check for Apify API key
    apify_key = config.integrations.apify_api_key
    if not apify_key:
        console.print("[red]Error: Apify API key not configured.[/red]")
        console.print("\nTo configure:")
        console.print("  1. Sign up at: [cyan]https://apify.com[/cyan]")
        console.print("  2. Get your API token from Settings > Integrations")
        console.print("  3. Run: [cyan]holo config set integrations.apify_api_key YOUR_KEY[/cyan]")
        db.close()
        return

    # Debug: Check key format (show first/last chars only)
    console.print(f"[dim]Using Apify key: {apify_key[:10]}...{apify_key[-4:]}[/dim]")

    # Get unenriched favorites
    cursor = db.conn.cursor()
    query = """
        SELECT item_id, title, url
        FROM mercadolivre_favorites
        WHERE enriched_at IS NULL AND url IS NOT NULL
        ORDER BY first_synced DESC
    """

    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query)
    favorites = []
    for row in cursor.fetchall():
        favorites.append({
            'item_id': row[0],
            'title': row[1],
            'url': row[2]
        })

    if not favorites:
        console.print("[yellow]No unenriched favorites found.[/yellow]")
        console.print("[dim]All favorites may already be enriched.[/dim]")
        db.close()
        return

    # Calculate cost
    count = len(favorites)
    estimated_cost = (count / 1000) * 0.50

    console.print(Panel.fit(
        f"[bold cyan]Apify ML Enrichment[/bold cyan]\n"
        f"Items to enrich: {count}\n"
        f"Estimated cost: [green]${estimated_cost:.2f}[/green]",
        border_style="cyan"
    ))

    # Preview
    console.print("\n[bold]Sample items:[/bold]")
    for fav in favorites[:5]:
        console.print(f"  • {fav['title'][:60]}")
    if count > 5:
        console.print(f"  [dim]... and {count - 5} more[/dim]")

    if dry_run:
        console.print("\n[yellow]Dry run - no scraping performed.[/yellow]")
        db.close()
        return

    console.print()
    if not click.confirm(f"Scrape {count} items via Apify for ~${estimated_cost:.2f}?"):
        console.print("[yellow]Cancelled.[/yellow]")
        db.close()
        return

    # Prepare URLs for Apify
    urls = [fav['url'] for fav in favorites]

    console.print("\n[cyan]Starting Apify scraper...[/cyan]")
    console.print("[dim]This may take a few minutes...[/dim]\n")

    try:
        # Call Apify
        client = ApifyClient(api_token=apify_key)

        # Use Apify's generic Web Scraper - simple and flexible
        results = client.run_actor_and_get_results(
            actor_id="apify/web-scraper",
            run_input={
                "startUrls": [{"url": url} for url in urls],
                "maxCrawlDepth": 0,  # Don't follow links, just scrape the URLs we give
                "maxCrawlPages": len(urls),
                "pseudoUrls": [],  # Don't follow any links
                "pageFunction": """
                    async function pageFunction(context) {
                        const { request, log, page } = context;

                        // Wait for page to load (ML is JS-heavy)
                        await page.waitForSelector('body', { timeout: 10000 });
                        await page.waitForTimeout(2000); // Extra 2s for JS

                        // Get item ID from URL
                        const itemId = request.url.match(/MLB[\\d-]+/)?.[0] || '';

                        // Extract all text content
                        const pageData = await page.evaluate(() => {
                            // Get all text from page
                            const title = document.querySelector('h1')?.innerText || '';
                            const fullHtml = document.body.innerHTML;

                            return {
                                title: title,
                                html: fullHtml.substring(0, 5000) // First 5K chars for debugging
                            };
                        });

                        return {
                            id: itemId,
                            item_id: itemId,
                            title: pageData.title,
                            description: pageData.html,
                            url: request.url
                        };
                    }
                """
            },
            timeout=900
        )

        console.print(f"[green]✓ Scraped {len(results)} items[/green]\n")

        # Update database
        enriched_count = 0
        for result in results:
            try:
                # Find matching favorite by URL or item ID
                item_id = result.get('id') or result.get('item_id')
                if not item_id:
                    console.print(f"[yellow]⚠ Skipping result without ID[/yellow]")
                    continue

                # Update database
                cursor.execute(
                    """
                    UPDATE mercadolivre_favorites
                    SET
                        description = ?,
                        specifications = ?,
                        seller_nickname = ?,
                        seller_reputation = ?,
                        reviews_rating = ?,
                        reviews_total = ?,
                        warranty = ?,
                        free_shipping = ?,
                        original_price = ?,
                        enriched_at = CURRENT_TIMESTAMP
                    WHERE item_id = ?
                    """,
                    (
                        result.get('description'),
                        str(result.get('specifications', '')),
                        result.get('seller', {}).get('nickname'),
                        str(result.get('seller', {}).get('reputation')),
                        result.get('reviews', {}).get('rating'),
                        result.get('reviews', {}).get('total'),
                        result.get('warranty'),
                        result.get('shipping', {}).get('free_shipping'),
                        result.get('original_price'),
                        item_id
                    )
                )

                if cursor.rowcount > 0:
                    enriched_count += 1
                    title = result.get('title', 'Unknown')[:50]
                    console.print(f"[green]✓[/green] {title}")

            except Exception as e:
                console.print(f"[red]✗ Error updating {result.get('title', 'unknown')[:50]}: {e}[/red]")

        db.conn.commit()

        console.print(f"\n[green]✓ Enriched {enriched_count}/{count} favorites![/green]")
        console.print(f"[dim]Cost: ~${estimated_cost:.2f}[/dim]")

    except Exception as e:
        console.print(f"\n[red]Error during Apify scraping: {e}[/red]")
        console.print("[dim]No changes were made to the database.[/dim]")

    db.close()


@mercadolivre.command()
@click.option("--limit", "-n", type=int, help="Limit number of items to enrich")
@click.option("--delay", "-d", type=int, default=3, help="Delay between requests in seconds (default: 3)")
def enrich_proxy(limit: int, delay: int):
    """Enrich ML favorites using Bright Data proxy (simple & cheap)."""
    config = load_config()
    db = Database(config.db_path)

    # Check for Bright Data credentials
    bd_user = config.integrations.brightdata_username
    bd_pass = config.integrations.brightdata_password

    if not bd_user or not bd_pass:
        console.print("[red]Error: Bright Data credentials not configured.[/red]")
        console.print("\nTo configure:")
        console.print("  1. Get your proxy credentials from Bright Data dashboard")
        console.print("  2. Run: [cyan]holo config set integrations.brightdata_username YOUR_USERNAME[/cyan]")
        console.print("  3. Run: [cyan]holo config set integrations.brightdata_password YOUR_PASSWORD[/cyan]")
        db.close()
        return

    # Ensure columns exist
    cursor = db.conn.cursor()
    try:
        cursor.execute("ALTER TABLE mercadolivre_favorites ADD COLUMN cached_html_path TEXT")
        db.conn.commit()
    except Exception:
        pass  # Column already exists

    try:
        cursor.execute("ALTER TABLE mercadolivre_favorites ADD COLUMN brightdata_blocked BOOLEAN DEFAULT 0")
        db.conn.commit()
    except Exception:
        pass  # Column already exists

    # Get unenriched favorites (excluding Bright Data blocked items)
    query = """
        SELECT item_id, title, url
        FROM mercadolivre_favorites
        WHERE enriched_at IS NULL
          AND url IS NOT NULL
          AND (brightdata_blocked IS NULL OR brightdata_blocked = 0)
        ORDER BY first_synced DESC
    """

    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query)
    favorites = []
    for row in cursor.fetchall():
        favorites.append({
            'item_id': row[0],
            'title': row[1],
            'url': row[2]
        })

    if not favorites:
        console.print("[yellow]No unenriched favorites found.[/yellow]")
        db.close()
        return

    # Estimate data usage (rough: ~500KB per page)
    estimated_mb = (len(favorites) * 0.5)
    console.print(Panel.fit(
        f"[bold cyan]Bright Data Proxy Enrichment[/bold cyan]\n"
        f"Items to enrich: {len(favorites)}\n"
        f"Estimated data: ~{estimated_mb:.1f} MB\n"
        f"Delay: {delay}s between requests",
        border_style="cyan"
    ))

    console.print("\n[bold]Sample items:[/bold]")
    for fav in favorites[:5]:
        console.print(f"  • {fav['title'][:60]}")
    if len(favorites) > 5:
        console.print(f"  [dim]... and {len(favorites) - 5} more[/dim]")

    console.print()
    if not click.confirm(f"Scrape {len(favorites)} items via Bright Data?"):
        console.print("[yellow]Cancelled.[/yellow]")
        db.close()
        return

    # Setup HTTP fetcher with proxy and caching
    fetcher = HTTPFetcher.from_config(
        config=config,
        use_proxy=True,  # Use Bright Data proxy
        integration_name='mercadolivre'
    )

    console.print(f"[dim]Using proxy: {bd_user}@{config.integrations.brightdata_host}[/dim]")
    if fetcher.cache_enabled:
        console.print(f"[dim]HTML caching enabled: {fetcher.cache_dir}[/dim]")

    console.print("\n[cyan]Starting scraping...[/cyan]\n")

    enriched_count = 0
    robots_txt_errors = 0
    other_errors = 0

    for i, fav in enumerate(favorites, 1):
        try:
            # Fetch page through proxy with caching
            console.print(f"[dim][{i}/{len(favorites)}][/dim] {fav['title'][:50]}... ", end="")

            soup, cached_html_path = fetcher.fetch_and_parse(
                url=fav['url'],
                cache_key=fav['item_id'],
                timeout=30
            )

            # Extract data - try multiple selectors (ML changes their HTML frequently)
            title = soup.find('h1')
            title_text = title.get_text(strip=True) if title else fav['title']

            # Description - ML uses ui-pdp-description class
            description = None
            desc_elem = soup.find('div', class_='ui-pdp-description')
            if desc_elem:
                description = desc_elem.get_text(strip=True, separator=' ')[:5000]  # Limit to 5K chars

            # Specifications - try multiple table selectors
            specs = {}
            for table_class in ['andes-table', 'ui-pdp-table', None]:
                spec_table = soup.find('table', class_=table_class)
                if spec_table:
                    for row in spec_table.find_all('tr'):
                        cells = row.find_all(['th', 'td'])
                        if len(cells) >= 2:
                            key = cells[0].get_text(strip=True)
                            val = cells[1].get_text(strip=True)
                            specs[key] = val
                    if specs:
                        break

            # Seller - try multiple selectors
            seller_nickname = None
            for selector in [
                ('div', {'class': 'ui-pdp-seller__header__title'}),
                ('span', {'class': lambda x: x and 'seller' in x.lower() if x else False}),
                ('a', {'class': lambda x: x and 'seller' in x.lower() if x else False}),
            ]:
                seller_elem = soup.find(*selector) if isinstance(selector, tuple) else soup.find(**selector)
                if seller_elem:
                    seller_nickname = seller_elem.get_text(strip=True)
                    break

            # Update database
            cursor.execute(
                """
                UPDATE mercadolivre_favorites
                SET
                    description = ?,
                    specifications = ?,
                    seller_nickname = ?,
                    cached_html_path = ?,
                    enriched_at = CURRENT_TIMESTAMP
                WHERE item_id = ?
                """,
                (
                    description,
                    str(specs) if specs else None,
                    seller_nickname,
                    cached_html_path,
                    fav['item_id']
                )
            )
            db.conn.commit()

            enriched_count += 1

            # Debug output
            desc_preview = f" ({len(description)} chars)" if description else " (no desc)"
            seller_info = f" | Seller: {seller_nickname[:20]}" if seller_nickname else ""
            console.print(f"[green]✓[/green]{desc_preview}{seller_info}")

            # Delay between requests (be polite!)
            if i < len(favorites):
                sleep_time = delay + random.uniform(-0.5, 0.5)
                time.sleep(sleep_time)

        except Exception as e:
            error_str = str(e)
            console.print(f"[red]✗ Error: {error_str[:120]}[/red]")

            # Track robots.txt errors for reporting
            if "robots.txt" in error_str:
                robots_txt_errors += 1
                console.print(f"[dim]  (Bright Data blocked - won't retry)[/dim]")

                # Mark as Bright Data blocked so we don't retry
                cursor.execute(
                    """
                    UPDATE mercadolivre_favorites
                    SET brightdata_blocked = 1
                    WHERE item_id = ?
                    """,
                    (fav['item_id'],)
                )
                db.conn.commit()
            else:
                other_errors += 1

    console.print(f"\n[green]✓ Enriched {enriched_count}/{len(favorites)} favorites![/green]")
    console.print(f"[dim]Data used: ~{(enriched_count * 0.5):.1f} MB[/dim]")

    # Error summary
    if robots_txt_errors > 0 or other_errors > 0:
        console.print(f"\n[yellow]Errors encountered:[/yellow]")
        if robots_txt_errors > 0:
            console.print(f"  • {robots_txt_errors} robots.txt restrictions (marked as blocked, won't retry)")
            console.print(f"    [dim]→ These items will be skipped in future runs[/dim]")
            console.print(f"    [dim]→ Contact Bright Data support if you need them whitelisted[/dim]")
        if other_errors > 0:
            console.print(f"  • {other_errors} other errors (will retry next time)")

    db.close()
