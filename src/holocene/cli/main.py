"""Main CLI interface for Holocene."""

import click
import json
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from datetime import datetime, timedelta
from pathlib import Path

from ..core.models import Activity, ActivityType, Context
from ..core.sanitizer import PrivacySanitizer
from ..storage.database import Database
from ..config import load_config, save_config, get_config_path, DEFAULT_CONFIG

# Import command groups
from .config_commands import config
from .stats_commands import stats
from .inventory_commands import inventory
from .ml_inventory_commands import ml_inventory
from .daemon_commands import daemon
from .ask_commands import ask_shortcut
from .auth_commands import auth

# Optional: MercadoLivre (requires beautifulsoup4)
try:
    from .mercadolivre_commands import mercadolivre
    MERCADOLIVRE_CLI_AVAILABLE = True
except ImportError:
    mercadolivre = None
    MERCADOLIVRE_CLI_AVAILABLE = False

console = Console()


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """
    Holocene - Your personal geological record of the present.

    A privacy-focused activity tracking and AI assistant system.
    """
    pass


# Register command groups
cli.add_command(config)
cli.add_command(stats)
cli.add_command(auth)
if MERCADOLIVRE_CLI_AVAILABLE:
    cli.add_command(mercadolivre)
cli.add_command(inventory)
cli.add_command(ml_inventory)
cli.add_command(daemon)
cli.add_command(ask_shortcut, name="ask")


@cli.command()
def init():
    """Initialize Holocene configuration and database."""
    config_path = get_config_path()

    if config_path.exists():
        console.print(f"[yellow]Config already exists at {config_path}[/yellow]")
        if not click.confirm("Overwrite?"):
            console.print("[green]Keeping existing config.[/green]")
            return

    # Create config directory
    config_path.parent.mkdir(parents=True, exist_ok=True)

    # Write default config
    with open(config_path, "w") as f:
        f.write(DEFAULT_CONFIG)

    console.print(Panel.fit(
        f"[green]✓[/green] Created config at {config_path}\n\n"
        f"[yellow]Next steps:[/yellow]\n"
        f"1. Edit config and add your NANOGPT_API_KEY\n"
        f"2. Or set environment variable: NANOGPT_API_KEY=your-key\n"
        f"3. Run: [cyan]holo log \"your first activity\"[/cyan]",
        title="Holocene Initialized"
    ))

    # Initialize database
    config = load_config()
    db = Database(config.db_path)
    console.print(f"[green]✓[/green] Created database at {config.db_path}")
    db.close()


@cli.command()
@click.argument("description")
@click.option("--tags", "-t", help="Comma-separated tags")
@click.option("--type", "-T", "activity_type",
              type=click.Choice([t.value for t in ActivityType]),
              default="other",
              help="Activity type")
@click.option("--context", "-c",
              type=click.Choice([c.value for c in Context]),
              default="unknown",
              help="Context (work, personal, open_source)")
@click.option("--duration", "-d", type=int, help="Duration in minutes")
def log(description: str, tags: str, activity_type: str, context: str, duration: int):
    """Log a manual activity."""
    config = load_config()
    db = Database(config.db_path)

    # Parse tags
    tag_list = [t.strip() for t in tags.split(",")] if tags else []

    # Create activity
    activity = Activity(
        description=description,
        tags=tag_list,
        activity_type=ActivityType(activity_type),
        context=Context(context),
        duration_minutes=duration,
        source="manual",
    )

    # Sanitize for privacy
    sanitizer = PrivacySanitizer(
        blacklist_domains=config.privacy.blacklist_domains,
        blacklist_keywords=config.privacy.blacklist_keywords,
        blacklist_paths=config.privacy.blacklist_paths,
        whitelist_domains=config.privacy.whitelist_domains,
    )

    sanitized = sanitizer.sanitize_activity(activity)

    if sanitized is None:
        console.print("[red]✗ Activity blocked by privacy filters[/red]")
        db.close()
        return

    # Insert into database
    activity_id = db.insert_activity(sanitized)
    console.print(f"[green]✓[/green] Logged activity #{activity_id}")

    # Show what was logged
    console.print(f"  Type: {sanitized.activity_type.value}")
    console.print(f"  Context: {sanitized.context.value}")
    console.print(f"  Tags: {', '.join(sanitized.tags) if sanitized.tags else '(none)'}")
    if sanitized.duration_minutes:
        console.print(f"  Duration: {sanitized.duration_minutes}m")

    db.close()


@cli.command()
@click.option("--limit", "-n", type=int, default=10, help="Number of activities to show")
def status(limit: int):
    """Show today's activity summary."""
    config = load_config()
    db = Database(config.db_path)

    activities = db.get_activities_today()
    total_count = len(activities)

    if not activities:
        console.print("[yellow]No activities logged today yet.[/yellow]")
        console.print(f"Start logging with: [cyan]holo log \"activity description\"[/cyan]")
        db.close()
        return

    # Show summary
    console.print(Panel(
        f"[bold]{total_count}[/bold] activities logged today",
        title=f"Today - {datetime.now().strftime('%A, %B %d')}"
    ))

    # Create table
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Time", style="dim")
    table.add_column("Type")
    table.add_column("Description", max_width=50)
    table.add_column("Tags", style="green")

    # Show most recent activities (up to limit)
    for activity in activities[:limit]:
        time_str = activity.timestamp.strftime("%H:%M")
        tags_str = ", ".join(activity.tags) if activity.tags else ""

        table.add_row(
            time_str,
            activity.activity_type.value,
            activity.description,
            tags_str
        )

    console.print(table)

    if total_count > limit:
        console.print(f"\n[dim]Showing {limit} of {total_count} activities. "
                     f"Use --limit to see more.[/dim]")

    db.close()


@cli.command()
@click.option("--today", is_flag=True, help="Show today's activities")
@click.option("--yesterday", is_flag=True, help="Show yesterday's activities")
@click.option("--week", is_flag=True, help="Show this week's activities")
@click.option("--limit", "-n", type=int, help="Limit number of results")
def show(today: bool, yesterday: bool, week: bool, limit: int):
    """Show activities for specific time periods."""
    config = load_config()
    db = Database(config.db_path)

    now = datetime.now()

    if yesterday:
        start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        title = "Yesterday"
    elif week:
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
        title = "This Week"
    else:  # today is default
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
        title = "Today"

    activities = db.get_activities(start_date=start, end_date=end, limit=limit)

    if not activities:
        console.print(f"[yellow]No activities found for {title.lower()}.[/yellow]")
        db.close()
        return

    # Group by type
    by_type = {}
    for activity in activities:
        type_name = activity.activity_type.value
        by_type.setdefault(type_name, []).append(activity)

    # Show summary
    console.print(Panel(
        f"[bold]{len(activities)}[/bold] activities",
        title=title
    ))

    # Summary by type
    console.print("\n[bold]By Type:[/bold]")
    for type_name, acts in sorted(by_type.items()):
        total_duration = sum(a.duration_minutes or 0 for a in acts)
        duration_str = f" ({total_duration}m)" if total_duration > 0 else ""
        console.print(f"  {type_name}: {len(acts)}{duration_str}")

    # Detailed list
    if len(activities) <= 20:
        console.print("\n[bold]Activities:[/bold]")
        for activity in activities:
            time_str = activity.timestamp.strftime("%H:%M")
            tags_str = f" [{', '.join(activity.tags)}]" if activity.tags else ""
            console.print(f"  {time_str} - {activity.description}{tags_str}")

    db.close()


@cli.command()
@click.option("--today", is_flag=True, help="Analyze today's activities")
@click.option("--week", is_flag=True, help="Analyze this week's activities")
@click.option("--cheap", is_flag=True, help="Use cheaper model")
@click.option("--no-journel", is_flag=True, help="Skip journel integration")
@click.option("--xkcd", is_flag=True, help="Include relevant XKCD comic reference (fun!)")
def analyze(today: bool, week: bool, cheap: bool, no_journel: bool, xkcd: bool):
    """Analyze your activity patterns using AI."""
    from ..llm import NanoGPTClient, ModelRouter, BudgetTracker
    from ..core.aggregator import ActivityAggregator
    from ..integrations import JournelReader, GitScanner

    config = load_config()

    # Check API key
    if not config.llm.api_key:
        console.print("[red]Error: NANOGPT_API_KEY not set[/red]")
        console.print("Set it in config or as environment variable")
        return

    # Initialize components
    budget = BudgetTracker(config.data_dir, config.llm.daily_budget)
    router = ModelRouter(config.llm)
    client = NanoGPTClient(config.llm.api_key, config.llm.base_url)
    db = Database(config.db_path)

    # Check budget
    remaining = budget.remaining_budget()
    if remaining <= 0:
        console.print(f"[red]Daily budget exhausted ({config.llm.daily_budget} calls)[/red]")
        console.print("Try again tomorrow or increase daily_budget in config")
        db.close()
        return

    console.print(f"[dim]Budget: {remaining}/{config.llm.daily_budget} calls remaining today[/dim]\n")

    # Get activities
    now = datetime.now()
    if week:
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        period = "this week"
    else:  # today is default
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period = "today"

    activities = db.get_activities(start_date=start)

    if not activities:
        console.print(f"[yellow]No activities found for {period}.[/yellow]")
        console.print("Log some activities first with: [cyan]holo log \"activity\"[/cyan]")
        db.close()
        return

    # Get journel context if enabled
    journel_context = ""
    journel_projects = []
    if config.integrations.journel_enabled and not no_journel:
        try:
            journel = JournelReader(
                journel_path=config.integrations.journel_path,
                ignore_projects=config.integrations.journel_ignore_projects
            )
            journel_projects = journel.get_active_projects()
            journel_context = journel.summarize_active_projects()
            console.print(f"[dim]✓ Loaded {len(journel_projects)} active journel projects[/dim]")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not load journel data: {e}[/yellow]")

    # Get git context if enabled
    git_context = ""
    if config.integrations.github_enabled and config.integrations.github_scan_path:
        try:
            git_scanner = GitScanner(
                scan_path=config.integrations.github_scan_path,
                github_token=config.integrations.github_token
            )

            # Get activity for the period
            if week:
                start_date = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)

            git_context = git_scanner.summarize_activity(start_date)

            # If we have journel projects, show alignment
            if journel_projects:
                matches = git_scanner.match_with_journel_projects(journel_projects)
                matched_count = sum(1 for repo in matches.values() if repo is not None)
                console.print(f"[dim]✓ Scanned git repos, matched {matched_count}/{len(journel_projects)} journel projects[/dim]")
            else:
                activity = git_scanner.get_activity_since(start_date)
                console.print(f"[dim]✓ Found {activity['total_commits']} commits in {len(activity['active_repos'])} repos[/dim]")

        except Exception as e:
            console.print(f"[yellow]Warning: Could not scan git repos: {e}[/yellow]")

    # Select model
    model = router.select_for_analysis(len(activities), use_cheap=cheap)
    console.print(f"[dim]Using model: {model}[/dim]")

    # Create prompt
    prompt = ActivityAggregator.create_analysis_prompt(
        activities,
        period,
        journel_context=journel_context,
        git_context=git_context,
        include_xkcd=xkcd
    )
    estimated_tokens = ActivityAggregator.estimate_tokens(prompt)
    console.print(f"[dim]Estimated prompt size: ~{estimated_tokens} tokens[/dim]\n")

    # Confirm
    if not click.confirm(f"This will use 1 API call. Continue?"):
        console.print("[yellow]Cancelled.[/yellow]")
        db.close()
        return

    # Call LLM
    with console.status("[bold cyan]Analyzing your activities...", spinner="dots"):
        try:
            response = client.simple_prompt(
                prompt=prompt,
                model=model,
                temperature=0.7,
            )

            # Increment budget
            budget.increment_usage(1)

        except Exception as e:
            console.print(f"[red]Error calling LLM: {e}[/red]")
            db.close()
            return

    # Display analysis
    console.print(Panel(
        response,
        title=f"Analysis - {period.title()}",
        border_style="cyan",
    ))

    # Save analysis to file
    analyses_dir = config.data_dir / "analyses"
    analyses_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    period_slug = period.replace(" ", "-")
    filename = f"{timestamp}_{period_slug}.md"
    analysis_path = analyses_dir / filename

    with open(analysis_path, "w", encoding="utf-8") as f:
        f.write(f"# Analysis - {period.title()}\n\n")
        f.write(f"**Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"**Model**: {model}\n")
        f.write(f"**Activities**: {len(activities)}\n\n")
        f.write("---\n\n")
        f.write(response)

    console.print(f"\n[dim]✓ Saved to {analysis_path}[/dim]")

    # Show new budget
    new_remaining = budget.remaining_budget()
    console.print(f"[dim]Remaining budget: {new_remaining}/{config.llm.daily_budget}[/dim]")

    db.close()


@cli.command()
@click.argument("urls", nargs=-1, required=True)
@click.option("--force", is_flag=True, help="Force archiving even if already archived")
@click.option("--check-only", is_flag=True, help="Only check if archived, don't save")
def archive(urls: tuple, force: bool, check_only: bool):
    """Archive URLs to Internet Archive Wayback Machine."""
    from ..integrations import InternetArchiveClient

    config = load_config()

    if not config.integrations.internet_archive_enabled:
        console.print("[yellow]Internet Archive integration is disabled[/yellow]")
        console.print("Enable in config: integrations.internet_archive_enabled = true")
        return

    # Initialize IA client
    ia = InternetArchiveClient(
        access_key=config.integrations.ia_access_key,
        secret_key=config.integrations.ia_secret_key,
        rate_limit=getattr(config.integrations, 'ia_rate_limit', 0.5)
    )

    rate_limit = getattr(config.integrations, 'ia_rate_limit', 0.5)
    seconds_between = 1.0 / rate_limit if rate_limit > 0 else 0
    console.print(f"[dim]Rate limit: {seconds_between:.1f}s between requests[/dim]\n")

    if check_only:
        # Just check availability
        for url in urls:
            with console.status(f"[cyan]Checking {url}...", spinner="dots"):
                result = ia.check_availability(url)

            if result.get("available"):
                console.print(f"[green]✓[/green] {url}")
                console.print(f"  Archived: {result.get('timestamp')}")
                console.print(f"  Snapshot: {result.get('snapshot_url')}")
            else:
                console.print(f"[yellow]✗[/yellow] {url}")
                console.print(f"  Not archived yet")

            if result.get("error"):
                console.print(f"  [red]Error: {result['error']}[/red]")

            console.print()

    else:
        # Archive URLs
        total = len(urls)
        console.print(f"Archiving {total} URL{'s' if total != 1 else ''}...\n")

        for idx, url in enumerate(urls, 1):
            console.print(f"[{idx}/{total}] {url}")

            with console.status(f"[cyan]Archiving...", spinner="dots"):
                result = ia.save_url(url, force=force)

            status = result.get("status")

            if status == "already_archived":
                console.print(f"  [blue]ℹ[/blue] Already archived")
                console.print(f"  Snapshot: {result.get('snapshot_url')}")
            elif status == "archived":
                console.print(f"  [green]✓[/green] Archived successfully")
                console.print(f"  Snapshot: {result.get('snapshot_url')}")
            else:
                console.print(f"  [red]✗[/red] {result.get('message')}")
                if result.get("error"):
                    console.print(f"  Error: {result['error']}")

            console.print()


@cli.group()
def links():
    """Manage tracked links and prevent link rot."""
    pass


@links.command()
@click.option("--limit", "-n", type=int, help="Limit number of links to show")
@click.option("--archived/--unarchived", default=None, help="Filter by archive status")
@click.option("--source", "-s", help="Filter by source (activity, journel, bookmarks)")
def list_links(limit: int, archived: bool, source: str):
    """List all tracked links."""
    config = load_config()
    db = Database(config.db_path)

    links_list = db.get_links(archived=archived, source=source, limit=limit)

    if not links_list:
        console.print("[yellow]No links found.[/yellow]")
        console.print("Scan for links with: [cyan]holo links scan[/cyan]")
        console.print("Import bookmarks with: [cyan]holo links import-bookmarks[/cyan]")
        db.close()
        return

    # Create table
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", width=5)
    table.add_column("URL", max_width=40)
    table.add_column("Source", width=10)
    table.add_column("Archived", width=8)
    table.add_column("Trust", width=10)
    table.add_column("Last Seen", width=16)

    # Trust tier colors
    trust_colors = {
        "pre-llm": "green",
        "early-llm": "yellow",
        "recent": "red",
        "unknown": "dim"
    }

    for link in links_list:
        archived_icon = "[green]✓[/green]" if link["archived"] else "[dim]-[/dim]"
        last_seen = datetime.fromisoformat(link["last_seen"]).strftime("%Y-%m-%d %H:%M")

        # Format trust tier with color
        trust_tier = link.get("trust_tier", "unknown")
        color = trust_colors.get(trust_tier, "dim")
        trust_display = f"[{color}]{trust_tier}[/{color}]" if link["archived"] else "[dim]-[/dim]"

        table.add_row(
            str(link["id"]),
            link["url"],
            link["source"],
            archived_icon,
            trust_display,
            last_seen
        )

    console.print(table)
    console.print(f"\n[dim]Showing {len(links_list)} link(s)[/dim]")

    db.close()


@links.command()
@click.option("--today", is_flag=True, help="Scan only today's activities")
@click.option("--week", is_flag=True, help="Scan this week's activities")
@click.option("--all", "scan_all", is_flag=True, help="Scan all activities")
@click.option("--journel/--no-journel", default=True, help="Scan journel projects")
def scan(today: bool, week: bool, scan_all: bool, journel: bool):
    """Scan activities and journel for links."""
    from ..core.link_utils import extract_urls, should_archive_url
    from ..integrations import JournelReader

    config = load_config()
    db = Database(config.db_path)

    found_links = set()

    # Determine time range for activities
    now = datetime.now()
    if week:
        start_date = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        period = "this week"
    elif today:
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period = "today"
    elif scan_all:
        start_date = None
        period = "all time"
    else:
        # Default to today
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period = "today"

    # Scan activities
    with console.status(f"[cyan]Scanning activities from {period}...", spinner="dots"):
        activities = db.get_activities(start_date=start_date)

        for activity in activities:
            # Extract from description
            urls = extract_urls(activity.description)
            for url in urls:
                if should_archive_url(url):
                    found_links.add((url, "activity"))

            # Extract from metadata if present
            if activity.metadata:
                metadata_str = str(activity.metadata)
                urls = extract_urls(metadata_str)
                for url in urls:
                    if should_archive_url(url):
                        found_links.add((url, "activity"))

    console.print(f"[green]✓[/green] Scanned {len(activities)} activities")

    # Scan journel projects if enabled
    journel_count = 0
    if journel and config.integrations.journel_enabled:
        try:
            with console.status("[cyan]Scanning journel projects...", spinner="dots"):
                journel_reader = JournelReader(
                    journel_path=config.integrations.journel_path,
                    ignore_projects=config.integrations.journel_ignore_projects
                )
                projects = journel_reader.get_active_projects()
                journel_count = len(projects)

                for project in projects:
                    # Extract from all project text fields
                    text = f"{project.name} {project.next_steps or ''} {project.blockers or ''} {project.github or ''}"
                    urls = extract_urls(text)
                    for url in urls:
                        if should_archive_url(url):
                            found_links.add((url, "journel"))

            console.print(f"[green]✓[/green] Scanned {journel_count} journel projects")
        except Exception as e:
            console.print(f"[yellow]Warning: Could not scan journel: {e}[/yellow]")

    if not found_links:
        console.print(f"\n[yellow]No links found in {period}.[/yellow]")
        db.close()
        return

    # Insert links into database
    console.print(f"\n[cyan]Found {len(found_links)} unique link(s)[/cyan]")
    new_count = 0
    updated_count = 0

    for url, source in found_links:
        # Check if link already exists
        existing = db.get_links(limit=1)
        existing_urls = {link["url"] for link in db.get_links()}

        if url in existing_urls:
            updated_count += 1
        else:
            new_count += 1

        db.insert_link(url=url, source=source)

    console.print(f"[green]✓[/green] Added {new_count} new link(s)")
    if updated_count > 0:
        console.print(f"[blue]ℹ[/blue] Updated {updated_count} existing link(s)")

    db.close()


@links.command("import-bookmarks")
@click.option("--browser", type=click.Choice(["auto", "edge", "chrome", "firefox"]), default="auto",
              help="Browser to import from")
def import_bookmarks(browser: str):
    """Import browser bookmarks into links database."""
    from ..integrations import BookmarksReader
    from ..core.link_utils import should_archive_url

    config = load_config()
    db = Database(config.db_path)

    reader = BookmarksReader()

    with console.status(f"[cyan]Reading {browser} bookmarks...", spinner="dots"):
        bookmarks = reader.read_bookmarks(browser=browser)

    if not bookmarks:
        console.print(f"[yellow]No bookmarks found for {browser}[/yellow]")
        console.print("Make sure browser is closed or try a different browser")
        db.close()
        return

    console.print(f"[green]✓[/green] Found {len(bookmarks)} bookmarks")

    # Filter and insert
    valid_count = 0
    new_count = 0
    updated_count = 0

    existing_urls = {link["url"] for link in db.get_links()}

    for bookmark in bookmarks:
        if not bookmark.url or not should_archive_url(bookmark.url):
            continue

        valid_count += 1

        if bookmark.url in existing_urls:
            updated_count += 1
        else:
            new_count += 1

        db.insert_link(
            url=bookmark.url,
            source="bookmarks",
            title=bookmark.name
        )

    console.print(f"[green]✓[/green] Processed {valid_count} valid bookmarks")
    console.print(f"[green]✓[/green] Added {new_count} new link(s)")
    if updated_count > 0:
        console.print(f"[blue]ℹ[/blue] Updated {updated_count} existing link(s)")

    db.close()


@links.command("import-telegram")
@click.argument("json_file", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Preview import without saving to database")
def import_telegram(json_file: str, dry_run: bool):
    """Import links from Telegram JSON export.

    Parses Telegram export JSON and imports all URLs found in messages.
    Each link is tagged with source='telegram_export' and the message timestamp.

    Example:
        holo links import-telegram personal/telegram.json
        holo links import-telegram telegram.json --dry-run
    """
    import builtins
    from ..core.link_utils import should_archive_url
    from urllib.parse import urlparse

    config = load_config()
    db = Database(config.db_path)

    # Load JSON file (use builtins.open to avoid conflict with 'open' command group)
    with console.status(f"[cyan]Reading {json_file}...", spinner="dots"):
        with builtins.open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

    if 'messages' not in data:
        console.print("[red]Error:[/red] No 'messages' field found in JSON")
        console.print("Make sure this is a valid Telegram export JSON file")
        db.close()
        return

    messages = data['messages']
    console.print(f"[green]✓[/green] Found {len(messages)} messages")

    # Extract all links from messages
    links_found = []
    for msg in messages:
        if msg.get('type') != 'message':
            continue

        # Check text_entities for links
        text_entities = msg.get('text_entities', [])
        for entity in text_entities:
            if entity.get('type') == 'link':
                url = entity.get('text', '').strip()
                if url and should_archive_url(url):
                    # Parse domain for display
                    try:
                        domain = urlparse(url).netloc
                    except:
                        domain = 'unknown'

                    links_found.append({
                        'url': url,
                        'date': msg.get('date', ''),
                        'domain': domain,
                        'message_id': msg.get('id'),
                    })

    console.print(f"[green]✓[/green] Extracted {len(links_found)} valid URLs")

    if not links_found:
        console.print("[yellow]No valid URLs found to import[/yellow]")
        db.close()
        return

    # Show domain breakdown
    from collections import Counter
    domain_counts = Counter(link['domain'] for link in links_found)
    console.print("\n[bold]Top domains:[/bold]")
    for domain, count in domain_counts.most_common(10):
        console.print(f"  {domain}: {count}")

    if dry_run:
        console.print(f"\n[yellow]Dry run - would import {len(links_found)} links[/yellow]")
        console.print("Run without --dry-run to actually import")
        db.close()
        return

    # Get existing URLs to avoid duplicates
    existing_urls = {link["url"] for link in db.get_links()}

    # Import to database
    new_count = 0
    updated_count = 0
    skipped_count = 0

    with console.status("[cyan]Importing links...", spinner="dots"):
        for link_data in links_found:
            url = link_data['url']

            if url in existing_urls:
                updated_count += 1
            else:
                new_count += 1

            try:
                db.insert_link(
                    url=url,
                    source="telegram_export",
                    title=None,  # No titles in Telegram export
                    metadata=json.dumps({
                        'telegram_message_id': link_data['message_id'],
                        'telegram_date': link_data['date'],
                    })
                )
            except Exception as e:
                console.print(f"[red]Error importing {url}:[/red] {e}")
                skipped_count += 1

    console.print(f"\n[green]✓[/green] Import complete!")
    console.print(f"[green]✓[/green] Added {new_count} new link(s)")
    if updated_count > 0:
        console.print(f"[blue]ℹ[/blue] Updated {updated_count} existing link(s)")
    if skipped_count > 0:
        console.print(f"[yellow]⚠[/yellow] Skipped {skipped_count} link(s) due to errors")

    console.print(f"\n[dim]💡 Tip: Use 'holo links archive-queue start' to gradually archive these links[/dim]")

    db.close()


@links.command("archive")
@click.option("--limit", "-n", type=int, help="Limit number of links to archive")
@click.option("--force", is_flag=True, help="Ignore exponential backoff and retry failed links")
@click.option("--retry-failed", is_flag=True, help="Only retry previously failed links that are ready")
def archive_links(limit: int, force: bool, retry_failed: bool):
    """Archive unarchived links to Internet Archive.

    By default, respects exponential backoff for previously failed links.
    Use --force to ignore backoff and retry immediately.
    Use --retry-failed to only process links ready for retry.
    """
    from ..integrations import InternetArchiveClient

    config = load_config()

    if not config.integrations.internet_archive_enabled:
        console.print("[yellow]Internet Archive integration is disabled[/yellow]")
        console.print("Enable in config: integrations.internet_archive_enabled = true")
        return

    db = Database(config.db_path)
    ia = InternetArchiveClient(
        access_key=config.integrations.ia_access_key,
        secret_key=config.integrations.ia_secret_key,
        rate_limit=getattr(config.integrations, 'ia_rate_limit', 0.5)
    )

    # Get links to archive
    if retry_failed:
        # Only get failed links that are ready to retry
        links_to_archive = db.get_links_ready_for_retry()
        if limit:
            links_to_archive = links_to_archive[:limit]
        console.print(f"[dim]Retrying {len(links_to_archive)} failed link(s) ready for retry[/dim]")
    elif force:
        # Force mode: get all unarchived, ignore backoff
        links_to_archive = db.get_links(archived=False, limit=limit)
        console.print(f"[dim]Force mode: ignoring exponential backoff[/dim]")
    else:
        # Default: get unarchived links that haven't failed, or failed but ready to retry
        all_unarchived = db.get_links(archived=False, limit=limit)
        links_to_archive = []
        now = datetime.now()

        for link in all_unarchived:
            # Skip if failed and not yet ready for retry
            if link.get("archive_attempts", 0) > 0:
                next_retry = link.get("next_retry_after")
                if next_retry:
                    next_retry_dt = datetime.fromisoformat(next_retry)
                    if next_retry_dt > now:
                        # Not ready yet, skip
                        continue

            links_to_archive.append(link)

    if not links_to_archive:
        console.print("[green]✓[/green] No unarchived links found")
        db.close()
        return

    total = len(links_to_archive)
    rate_limit = getattr(config.integrations, 'ia_rate_limit', 0.5)
    seconds_between = 1.0 / rate_limit if rate_limit > 0 else 0
    console.print(f"[cyan]Archiving {total} link(s)...[/cyan]")
    console.print(f"[dim]Rate limit: {seconds_between:.1f}s between requests[/dim]\n")

    archived_count = 0
    already_archived_count = 0
    error_count = 0

    for idx, link in enumerate(links_to_archive, 1):
        url = link["url"]
        console.print(f"[{idx}/{total}] {url}")

        with console.status("[cyan]Archiving...", spinner="dots"):
            result = ia.save_url(url, force=force)

        status = result.get("status")

        if status == "already_archived":
            already_archived_count += 1
            archive_date = result.get("archive_date")

            console.print(f"  [blue]ℹ[/blue] Already archived")
            console.print(f"  Snapshot: {result.get('snapshot_url')}")

            # Show trust tier if available
            if archive_date:
                from ..storage.database import calculate_trust_tier
                trust_tier = calculate_trust_tier(archive_date)
                console.print(f"  [dim]Trust tier: {trust_tier} ({archive_date[:8]})[/dim]")

            # Update database
            db.update_link_archive_status(
                url=url,
                archived=True,
                archive_url=result.get("snapshot_url"),
                archive_date=archive_date
            )
        elif status == "archived":
            archived_count += 1
            archive_date = result.get("archive_date")

            console.print(f"  [green]✓[/green] Archived successfully")
            console.print(f"  Snapshot: {result.get('snapshot_url')}")

            # Show trust tier if available
            if archive_date:
                from ..storage.database import calculate_trust_tier
                trust_tier = calculate_trust_tier(archive_date)
                console.print(f"  [dim]Trust tier: {trust_tier} ({archive_date[:8]})[/dim]")

            # Update database
            db.update_link_archive_status(
                url=url,
                archived=True,
                archive_url=result.get("snapshot_url"),
                archive_date=archive_date
            )
        else:
            error_count += 1
            error_msg = result.get("error") or result.get("message") or "Unknown error"

            # Record failure with exponential backoff
            backoff_info = db.record_archive_failure(url, error_msg)

            console.print(f"  [red]✗[/red] {result.get('message')}")
            if result.get("error"):
                console.print(f"  Error: {result['error']}")

            # Show backoff info
            attempts = backoff_info["attempts"]
            delay_days = backoff_info["delay_days"]
            next_retry = backoff_info["next_retry_after"].strftime("%Y-%m-%d")

            console.print(f"  [dim]Attempt {attempts} - will retry after {next_retry} ({delay_days} days)[/dim]")

        console.print()

    # Summary
    console.print(Panel.fit(
        f"[green]✓[/green] Newly archived: {archived_count}\n"
        f"[blue]ℹ[/blue] Already archived: {already_archived_count}\n"
        f"[red]✗[/red] Errors: {error_count}",
        title="Archive Summary"
    ))

    db.close()


@links.command("auto-archive")
@click.option("--scan/--no-scan", default=True, help="Scan for new links before archiving")
@click.option("--limit", "-n", type=int, default=50, help="Maximum links to archive per run")
@click.option("--scan-period", type=click.Choice(["today", "week", "all"]), default="today",
              help="Period to scan for new links")
def auto_archive(scan: bool, limit: int, scan_period: str):
    """Automated link discovery and archiving (cron-friendly).

    This command combines scanning and archiving into a single operation
    suitable for scheduled runs via cron:

    1. Scans for new links (optional, default: yes)
    2. Archives unarchived links
    3. Retries failed links that are ready (respects exponential backoff)

    Example cron entry (daily at 3 AM):
        0 3 * * * /usr/bin/holo links auto-archive --limit 50 >> /var/log/holocene/archive.log 2>&1
    """
    from ..core.link_utils import extract_urls, should_archive_url
    from ..integrations import JournelReader, InternetArchiveClient

    config = load_config()
    db = Database(config.db_path)

    # Step 1: Scan for new links (if enabled)
    if scan:
        console.print("[bold cyan]Step 1: Scanning for new links[/bold cyan]")

        found_links = set()
        now = datetime.now()

        # Determine time range
        if scan_period == "week":
            start_date = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            period = "this week"
        elif scan_period == "all":
            start_date = None
            period = "all time"
        else:  # today
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            period = "today"

        # Scan activities
        activities = db.get_activities(start_date=start_date)
        for activity in activities:
            urls = extract_urls(activity.description)
            for url in urls:
                if should_archive_url(url):
                    found_links.add((url, "activity"))

            if activity.metadata:
                metadata_str = str(activity.metadata)
                urls = extract_urls(metadata_str)
                for url in urls:
                    if should_archive_url(url):
                        found_links.add((url, "activity"))

        console.print(f"  [green]✓[/green] Scanned {len(activities)} activities from {period}")

        # Scan journel projects if enabled
        if config.integrations.journel_enabled:
            try:
                journel_reader = JournelReader(
                    journel_path=config.integrations.journel_path,
                    ignore_projects=config.integrations.journel_ignore_projects
                )
                projects = journel_reader.get_active_projects()

                for project in projects:
                    text = f"{project.name} {project.next_steps or ''} {project.blockers or ''} {project.github or ''}"
                    urls = extract_urls(text)
                    for url in urls:
                        if should_archive_url(url):
                            found_links.add((url, "journel"))

                console.print(f"  [green]✓[/green] Scanned {len(projects)} journel projects")
            except Exception as e:
                console.print(f"  [yellow]Warning: Could not scan journel: {e}[/yellow]")

        # Insert discovered links
        if found_links:
            new_count = 0
            existing_urls = {link["url"] for link in db.get_links()}

            for url, source in found_links:
                if url not in existing_urls:
                    new_count += 1
                db.insert_link(url=url, source=source)

            console.print(f"  [green]✓[/green] Found {len(found_links)} link(s), {new_count} new\n")
        else:
            console.print(f"  [dim]No new links found[/dim]\n")

    # Step 2: Archive unarchived links
    console.print("[bold cyan]Step 2: Archiving links[/bold cyan]")

    if not config.integrations.internet_archive_enabled:
        console.print("  [yellow]Internet Archive integration is disabled[/yellow]")
        console.print("  [dim]Enable in config: integrations.internet_archive_enabled = true[/dim]")
        db.close()
        return

    ia = InternetArchiveClient(
        access_key=config.integrations.ia_access_key,
        secret_key=config.integrations.ia_secret_key,
        rate_limit=getattr(config.integrations, 'ia_rate_limit', 0.5)
    )

    # Get unarchived links (respects exponential backoff)
    all_unarchived = db.get_links(archived=False)
    links_to_archive = []
    now_dt = datetime.now()

    for link in all_unarchived:
        # Skip if failed and not yet ready for retry
        if link.get("archive_attempts", 0) > 0:
            next_retry = link.get("next_retry_after")
            if next_retry:
                next_retry_dt = datetime.fromisoformat(next_retry)
                if next_retry_dt > now_dt:
                    continue  # Not ready yet

        links_to_archive.append(link)

        if len(links_to_archive) >= limit:
            break

    if not links_to_archive:
        console.print("  [green]✓[/green] No links ready for archiving\n")
        db.close()
        return

    total = len(links_to_archive)
    rate_limit = getattr(config.integrations, 'ia_rate_limit', 0.5)
    seconds_between = 1.0 / rate_limit if rate_limit > 0 else 0
    console.print(f"  [dim]Archiving {total} link(s) (rate limit: {seconds_between:.1f}s)[/dim]")

    archived_count = 0
    already_archived_count = 0
    error_count = 0

    for idx, link in enumerate(links_to_archive, 1):
        url = link["url"]

        result = ia.save_url(url, force=False)
        status = result.get("status")

        if status == "already_archived":
            already_archived_count += 1
            archive_date = result.get("archive_date")

            db.update_link_archive_status(
                url=url,
                archived=True,
                archive_url=result.get("snapshot_url"),
                archive_date=archive_date
            )
        elif status == "archived":
            archived_count += 1
            archive_date = result.get("archive_date")

            db.update_link_archive_status(
                url=url,
                archived=True,
                archive_url=result.get("snapshot_url"),
                archive_date=archive_date
            )
        else:
            error_count += 1
            error_msg = result.get("error") or result.get("message") or "Unknown error"
            backoff_info = db.record_archive_failure(url, error_msg)

    # Summary
    console.print()
    console.print(Panel.fit(
        f"[green]✓[/green] Newly archived: {archived_count}\n"
        f"[blue]ℹ[/blue] Already archived: {already_archived_count}\n"
        f"[red]✗[/red] Errors: {error_count}",
        title="Auto-Archive Summary"
    ))

    db.close()


@links.command("archive-queue")
@click.option("--batch-size", "-n", type=int, default=10, help="Number of links to archive in this batch")
@click.option("--delay", "-d", type=int, default=60, help="Delay in seconds between archives (default: 60)")
@click.option("--service", type=click.Choice(["archivebox", "local", "ia"]), default="archivebox",
              help="Which archiving service to use")
@click.option("--source", help="Only archive links from specific source (e.g., telegram_export)")
def archive_queue(batch_size: int, delay: int, service: str, source: str):
    """Gradually archive links from the queue (safe for cron).

    Processes unarchived links in small batches with delays to avoid rate limiting.
    Designed to be run periodically via cron for gradual background archiving.

    Examples:
        # Archive 10 links with 60s delays (safe default)
        holo links archive-queue

        # Faster batch: 20 links with 30s delays
        holo links archive-queue --batch-size 20 --delay 30

        # Only archive telegram imports
        holo links archive-queue --source telegram_export

    Cron example (every hour):
        0 * * * * cd /home/holocene/holocene && venv/bin/holo links archive-queue
    """
    import time
    import random
    from ..storage.archiving import ArchivingService
    from ..integrations.local_archive import LocalArchiveClient
    from ..integrations.archivebox import ArchiveBoxClient
    from ..integrations.internet_archive import InternetArchiveClient

    config = load_config()
    db = Database(config.db_path)

    # Initialize archiving clients based on service choice
    local_client = None
    ia_client = None
    archivebox_client = None

    if service == "archivebox":
        if getattr(config.integrations, 'archivebox_enabled', False):
            archivebox_client = ArchiveBoxClient(
                ssh_host=config.integrations.archivebox_host,
                ssh_user=config.integrations.archivebox_user,
                data_dir=config.integrations.archivebox_data_dir,
            )
        else:
            console.print("[red]Error:[/red] ArchiveBox not enabled in config")
            db.close()
            return
    elif service == "local":
        local_client = LocalArchiveClient()
    elif service == "ia":
        if getattr(config.integrations, 'internet_archive_enabled', False):
            ia_client = InternetArchiveClient(
                access_key=config.integrations.ia_access_key,
                secret_key=config.integrations.ia_secret_key,
                rate_limit=getattr(config.integrations, 'ia_rate_limit_seconds', 2.0)
            )
        else:
            console.print("[red]Error:[/red] Internet Archive not enabled in config")
            db.close()
            return

    archiving = ArchivingService(
        db=db,
        local_client=local_client,
        ia_client=ia_client,
        archivebox_client=archivebox_client
    )

    # Get unarchived links
    filters = {"archived": False}
    if source:
        filters["source"] = source

    # Get links without any successful archive snapshots
    cursor = db.conn.cursor()
    query = """
        SELECT l.id, l.url, l.source
        FROM links l
        LEFT JOIN archive_snapshots a ON l.id = a.link_id AND a.status = 'success'
        WHERE a.id IS NULL
    """
    params = []

    if source:
        query += " AND l.source = ?"
        params.append(source)

    query += " LIMIT ?"
    params.append(batch_size)

    cursor.execute(query, params)
    links_to_archive = [{'id': row[0], 'url': row[1], 'source': row[2]} for row in cursor.fetchall()]

    if not links_to_archive:
        console.print("[green]✓[/green] No unarchived links in queue")
        db.close()
        return

    console.print(f"[cyan]Processing {len(links_to_archive)} link(s) with {delay}s delays[/cyan]")
    console.print(f"[dim]Service: {service}[/dim]\n")

    success_count = 0
    error_count = 0

    for i, link in enumerate(links_to_archive, 1):
        console.print(f"[{i}/{len(links_to_archive)}] {link['url'][:60]}...")

        try:
            # Archive using selected service
            result = archiving.archive_url(
                link_id=link['id'],
                url=link['url'],
                local_format='monolith' if service == 'local' else None,
                use_ia=(service == 'ia'),
                use_archivebox=(service == 'archivebox')
            )

            if result.get('success'):
                console.print(f"  [green]✓[/green] Archived")
                success_count += 1
            else:
                errors = ', '.join(result.get('errors', ['Unknown error']))
                console.print(f"  [red]✗[/red] {errors}")
                error_count += 1

        except Exception as e:
            console.print(f"  [red]✗[/red] Exception: {e}")
            error_count += 1

        # Delay between archives (except after last one)
        if i < len(links_to_archive):
            # Add random jitter (±20%) to avoid patterns
            jitter = random.uniform(0.8, 1.2)
            actual_delay = int(delay * jitter)
            console.print(f"  [dim]Waiting {actual_delay}s...[/dim]")
            time.sleep(actual_delay)

    # Summary
    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"[green]✓[/green] Success: {success_count}")
    console.print(f"[red]✗[/red] Errors: {error_count}")
    console.print(f"\n[dim]Remaining: Check with 'holo links list --unarchived'[/dim]")

    db.close()


@cli.group()
def books():
    """Manage your book collection for research."""
    pass


@books.command("import")
@click.argument("file_path", type=click.Path(exists=True))
def books_import(file_path: str):
    """Import books from LibraryCat CSV or LibraryThing JSON export."""
    from ..research import LibraryCatImporter

    file_path_obj = Path(file_path)
    config = load_config()
    db = Database(config.db_path)

    console.print(f"[cyan]Importing books from {file_path_obj.name}...[/cyan]")

    importer = LibraryCatImporter()

    try:
        count = importer.import_to_database(file_path_obj, db)
        console.print(Panel.fit(
            f"[green]✓[/green] Successfully imported {count} books!",
            title="Import Complete"
        ))
    except Exception as e:
        console.print(f"[red]✗[/red] Import failed: {e}")
    finally:
        db.close()


@books.command("list")
@click.option("--limit", "-n", type=int, default=20, help="Number of books to show")
@click.option("--search", "-s", help="Search in title, author, or subjects")
@click.option("--author", "-a", help="Filter by author")
@click.option("--subject", help="Filter by subject/genre")
@click.option("--by-dewey", is_flag=True, help="Sort by Dewey/call number (library order)")
def books_list(limit: int, search: str, author: str, subject: str, by_dewey: bool):
    """List books in your collection."""
    config = load_config()
    db = Database(config.db_path)

    order_by = "dewey" if by_dewey else "title"
    books_list = db.get_books(search=search, author=author, subject=subject, limit=limit, order_by=order_by)

    if not books_list:
        console.print("[yellow]No books found.[/yellow]")
        console.print("Import books with: [cyan]holo books import <file>[/cyan]")
        db.close()
        return

    # Create table
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim", width=5)

    if by_dewey:
        table.add_column("Call #", width=15, style="green")

    table.add_column("Title", max_width=40)
    table.add_column("Author", max_width=25)
    table.add_column("Year", width=6)

    if not by_dewey:
        table.add_column("Subjects", max_width=30)

    import json
    for book in books_list:
        book_id = str(book["id"])
        title = book.get("title", "Unknown")
        author = book.get("author", "Unknown")
        year = str(book.get("publication_year", "")) if book.get("publication_year") else ""

        if by_dewey:
            # Show call number or classification number
            call_num = book.get("call_number") or book.get("udc_classification") or "[dim]—[/dim]"
            table.add_row(book_id, call_num, title, author, year)
        else:
            # Parse subjects from JSON
            subjects_json = book.get("subjects", "[]")
            try:
                subjects = json.loads(subjects_json) if subjects_json else []
                subjects_str = ", ".join(subjects[:3])  # Show first 3
                if len(subjects) > 3:
                    subjects_str += "..."
            except (json.JSONDecodeError, TypeError):
                subjects_str = ""

            table.add_row(book_id, title, author, year, subjects_str)

    console.print(table)

    if by_dewey:
        console.print(f"\n[dim]Showing {len(books_list)} books sorted by call number[/dim]")
    else:
        console.print(f"\n[dim]Showing {len(books_list)} books[/dim]")

    db.close()


@books.command("search")
@click.argument("query")
@click.option("--limit", "-n", type=int, default=10, help="Number of results")
def books_search(query: str, limit: int):
    """Search your book collection."""
    config = load_config()
    db = Database(config.db_path)

    books_list = db.get_books(search=query, limit=limit)

    if not books_list:
        console.print(f"[yellow]No books found matching '{query}'[/yellow]")
        db.close()
        return

    console.print(f"\n[cyan]Found {len(books_list)} books matching '{query}':[/cyan]\n")

    import json
    for book in books_list:
        title = book.get("title", "Unknown")
        author = book.get("author", "Unknown")
        year = book.get("publication_year", "")

        year_str = f" ({year})" if year else ""
        console.print(f"[bold]{title}[/bold]{year_str}")
        console.print(f"  by {author}")

        # Show subjects
        subjects_json = book.get("subjects", "[]")
        try:
            subjects = json.loads(subjects_json) if subjects_json else []
            if subjects:
                console.print(f"  [dim]Subjects: {', '.join(subjects[:5])}[/dim]")
        except (json.JSONDecodeError, TypeError):
            pass

        if book.get("notes"):
            console.print(f"  [dim]{book['notes'][:100]}...[/dim]")

        console.print()

    db.close()


@books.command("enrich")
@click.option("--batch-size", "-b", type=int, default=20, help="Books per batch (default: 20)")
def books_enrich(batch_size: int):
    """Enrich book metadata with LLM-generated summaries and tags (batch processed)."""
    from ..research.book_enrichment import BookEnricher

    console.print("[cyan]Starting book enrichment...[/cyan]")
    console.print(f"[dim]Processing in batches of {batch_size} books[/dim]\n")

    enricher = BookEnricher()

    try:
        stats = enricher.enrich_all_books(batch_size=batch_size)

        console.print()
        console.print(Panel.fit(
            f"[green]✓[/green] Enrichment complete!\n\n"
            f"Total books: {stats['total']}\n"
            f"Enriched: {stats['enriched']}\n"
            f"Failed: {stats['failed']}",
            title="Book Enrichment Results"
        ))

    except Exception as e:
        console.print(f"[red]✗[/red] Enrichment failed: {e}")
    finally:
        enricher.close()


@books.command("classify")
@click.argument("book_id", type=int, required=False)
@click.option("--all", "classify_all", is_flag=True, help="Classify all unclassified books")
@click.option("--system", type=click.Choice(["UDC", "Dewey"]), default=None,
              help="Classification system to use (overrides config)")
def classify_books(book_id, classify_all, system):
    """Classify books using configured classification system (Dewey or UDC)."""
    from holocene.research import UDCClassifier, DeweyClassifier
    from holocene.config import load_config
    from rich.table import Table

    # Load config to determine which system to use
    config = load_config()

    # Use --system flag if provided, otherwise use config
    if system is None:
        system = config.classification.system

    # Instantiate the appropriate classifier
    if system == "Dewey":
        classifier = DeweyClassifier()
        system_name = "Dewey Decimal"
        number_key = "dewey_number"
        label_key = "dewey_label"
    elif system == "UDC":
        classifier = UDCClassifier()
        system_name = "UDC"
        number_key = "udc_number"
        label_key = "udc_label"
    else:
        console.print(f"[red]✗[/red] Unknown classification system: {system}")
        return

    db = classifier.db

    try:
        if classify_all:
            # Get all unclassified books
            books = db.get_unclassified_books()

            if not books:
                console.print("[green]✓[/green] All books are already classified!")
                return

            console.print(f"\n[cyan]Classifying {len(books)} books using {system_name}...[/cyan]\n")

            for i, book in enumerate(books, 1):
                console.print(f"[{i}/{len(books)}] {book['title']}")

                # Classify the book
                result = classifier.classify_book(
                    title=book['title'],
                    author=book['author'],
                    subtitle=book['subtitle'],
                    subjects=book['subjects'],
                    publisher=book['publisher'],
                    publication_year=book['publication_year'],
                    enriched_summary=book.get('enriched_summary')
                )

                if "error" in result:
                    console.print(f"  [red]✗[/red] {result['error']}")
                    continue

                # Update database
                db.update_book_classification(
                    book_id=book['id'],
                    udc_number=result.get(number_key, result.get('udc_number')),
                    classification_system=result['classification_system'],
                    confidence=result['confidence'],
                    cutter_number=result.get('cutter_number'),
                    call_number=result.get('call_number')
                )

                # Display result
                class_num = result.get(number_key, result.get('udc_number'))
                class_label = result.get(label_key, result.get('udc_label'))
                console.print(f"  [green]✓[/green] {class_num} - {class_label}")

                if result.get('call_number'):
                    console.print(f"    Call Number: [bold]{result['call_number']}[/bold]")
                elif result.get('cutter_number'):
                    console.print(f"    Cutter: {result['cutter_number']}")

                console.print(f"    Confidence: {result['confidence']}")
                if result.get('reasoning'):
                    console.print(f"    {result['reasoning']}")
                console.print()

        elif book_id:
            # Classify single book
            book = db.get_book(book_id)
            if not book:
                console.print(f"[red]✗[/red] Book {book_id} not found")
                return

            console.print(f"\n[cyan]Classifying: {book['title']}[/cyan]")
            console.print(f"[dim]Using {system_name} classification[/dim]\n")

            result = classifier.classify_book(
                title=book['title'],
                author=book['author'],
                subtitle=book['subtitle'],
                subjects=book['subjects'],
                publisher=book['publisher'],
                publication_year=book['publication_year'],
                enriched_summary=book.get('enriched_summary')
            )

            if "error" in result:
                console.print(f"[red]✗[/red] Classification failed: {result['error']}")
                return

            # Update database
            db.update_book_classification(
                book_id=book['id'],
                udc_number=result.get(number_key, result.get('udc_number')),
                classification_system=result['classification_system'],
                confidence=result['confidence'],
                cutter_number=result.get('cutter_number'),
                call_number=result.get('call_number')
            )

            # Display result
            table = Table(title=f"{system_name} Classification Result")
            table.add_column("Field", style="cyan")
            table.add_column("Value", style="white")

            class_num = result.get(number_key, result.get('udc_number'))
            class_label = result.get(label_key, result.get('udc_label'))

            table.add_row(f"{system_name} Number", class_num)
            table.add_row("Subject", class_label)

            if result.get('call_number'):
                table.add_row("Call Number", f"[bold]{result['call_number']}[/bold]")
            if result.get('cutter_number'):
                table.add_row("Cutter Number", result['cutter_number'])

            table.add_row("Confidence", result['confidence'])
            if result.get('alternative_numbers'):
                table.add_row("Alternatives", ", ".join(result['alternative_numbers']))
            if result.get('reasoning'):
                table.add_row("Reasoning", result['reasoning'])

            console.print(table)
            console.print(f"\n[green]✓[/green] Classification saved!")

        else:
            console.print("[yellow]Usage:[/yellow] holo books classify <book-id> OR --all")

    except Exception as e:
        console.print(f"[red]✗[/red] Classification failed: {e}")
        import traceback
        traceback.print_exc()


@books.command("repair-classification")
@click.option("--dry-run", is_flag=True, help="Show what would be fixed without making changes")
def repair_classification(dry_run: bool):
    """Repair missing Cutter numbers and call numbers for classified books."""
    from holocene.config import load_config
    from holocene.research.dewey_classifier import generate_cutter_number

    config = load_config()
    db = Database(config.db_path)

    try:
        # Find books that have classification but missing Cutter/call numbers
        cursor = db.conn.cursor()
        cursor.execute("""
            SELECT id, title, author, udc_classification, classification_system,
                   cutter_number, call_number
            FROM books
            WHERE (udc_classification IS NOT NULL OR classification_system IS NOT NULL)
              AND (cutter_number IS NULL OR call_number IS NULL)
        """)
        books_to_fix = [dict(row) for row in cursor.fetchall()]

        if not books_to_fix:
            console.print("[green]✓[/green] All classified books have proper call numbers!")
            return

        console.print(f"\n[cyan]Found {len(books_to_fix)} books needing repair:[/cyan]\n")

        fixed = 0
        cannot_fix = []

        for book in books_to_fix:
            book_id = book['id']
            title = book['title']
            author = book['author']
            classification = book['udc_classification']
            system = book['classification_system'] or 'Unknown'

            # Check if we can generate Cutter number
            if not author or not classification:
                cannot_fix.append({
                    'id': book_id,
                    'title': title,
                    'reason': 'Missing author' if not author else 'Missing classification number'
                })
                console.print(f"[yellow]⚠[/yellow] ID {book_id}: {title}")
                console.print(f"  Cannot repair: {'No author info' if not author else 'No classification number'}")
                continue

            # Generate Cutter number
            cutter = generate_cutter_number(author, config.classification.cutter_length)

            # Generate call number
            work_letter = title[0].lower() if title else "a"
            call_number = f"{classification} {cutter}{work_letter}"

            if dry_run:
                console.print(f"[cyan]Would repair[/cyan] ID {book_id}: {title}")
                console.print(f"  Current: {classification}")
                console.print(f"  Would set: {call_number} (Cutter: {cutter})")
            else:
                # Update database
                db.update_book_classification(
                    book_id=book_id,
                    udc_number=classification,
                    classification_system=system,
                    confidence='medium',  # Keep existing or set default
                    cutter_number=cutter,
                    call_number=call_number
                )
                console.print(f"[green]✓[/green] ID {book_id}: {title}")
                console.print(f"  Set call number: [bold]{call_number}[/bold]")
                fixed += 1

            console.print()

        # Summary
        if dry_run:
            console.print(f"\n[cyan]Dry run complete:[/cyan]")
            console.print(f"  Would fix: {len(books_to_fix) - len(cannot_fix)} books")
            console.print(f"  Cannot fix: {len(cannot_fix)} books")
        else:
            console.print(f"\n[green]Repair complete:[/green]")
            console.print(f"  Fixed: {fixed} books")
            if cannot_fix:
                console.print(f"  [yellow]Could not fix {len(cannot_fix)} books (missing author/classification)[/yellow]")

        db.close()

    except Exception as e:
        console.print(f"[red]✗[/red] Repair failed: {e}")
        import traceback
        traceback.print_exc()


@books.command("discover-ia")
@click.argument("query")
@click.option("--limit", "-l", type=int, default=20, help="Number of results")
@click.option("--subject", "-s", help="Filter by subject (e.g., 'mining', 'geology')")
@click.option("--pre-llm", is_flag=True, help="Only show books from 1900-2022")
def books_discover_ia(query: str, limit: int, subject: str, pre_llm: bool):
    """Search Internet Archive for public domain books."""
    from ..research import InternetArchiveClient

    console.print(f"[cyan]Searching Internet Archive for:[/cyan] {query}\n")

    client = InternetArchiveClient()

    with console.status("[bold cyan]Searching Internet Archive...", spinner="dots"):
        if pre_llm:
            results = client.search_pre_llm_books(query, subject=subject, limit=limit)
        else:
            results = client.search_books(query, subject=subject, limit=limit)

    if not results:
        console.print("[yellow]No books found[/yellow]")
        return

    console.print(f"[cyan]Found {len(results)} books:[/cyan]\n")

    for i, book in enumerate(results, 1):
        authors_str = ", ".join(book.get("authors", [])[:2])
        if len(book.get("authors", [])) > 2:
            authors_str += " et al."

        console.print(f"{i}. [bold]{book.get('title', 'Untitled')}[/bold]")
        if authors_str:
            console.print(f"   {authors_str}")
        if book.get("publication_year"):
            console.print(f"   Published: {book['publication_year']}")
        if book.get("downloads"):
            console.print(f"   [dim]Downloads: {book['downloads']:,}[/dim]")
        console.print(f"   [dim]Identifier: {book.get('identifier')}[/dim]")
        console.print(f"   [dim]{book.get('url')}[/dim]")
        console.print()


@books.command("add-ia")
@click.argument("identifier")
@click.option("--download-pdf", is_flag=True, help="Download PDF to local storage")
@click.option("--add-to-calibre", is_flag=True, help="Add to Calibre library (overrides config)")
@click.option("--no-calibre", is_flag=True, help="Skip Calibre even if enabled in config")
def books_add_ia(identifier: str, download_pdf: bool, add_to_calibre: bool, no_calibre: bool):
    """Add a book from Internet Archive to your collection."""
    from ..research import InternetArchiveClient
    from ..integrations import CalibreIntegration

    config = load_config()
    db = Database(config.db_path)
    client = InternetArchiveClient()

    console.print(f"[cyan]Fetching metadata from Internet Archive...[/cyan]")

    metadata = client.get_metadata(identifier)

    if not metadata:
        console.print(f"[red]✗[/red] Book not found with identifier: {identifier}")
        db.close()
        return

    # Extract book info
    title = metadata.get("title", "Unknown")
    creators = metadata.get("creator", [])
    if isinstance(creators, str):
        creators = [creators]
    author = ", ".join(creators) if creators else None

    publication_year = metadata.get("date")
    if isinstance(publication_year, list) and publication_year:
        publication_year = publication_year[0]

    subjects = metadata.get("subject", [])
    if isinstance(subjects, str):
        subjects = [subjects]

    # Determine PDF path
    pdf_dir = config.data_dir / "books" / "internet_archive"
    pdf_path = pdf_dir / f"{identifier}.pdf"

    # Check if PDF already exists (caching!)
    pdf_already_exists = pdf_path.exists()
    if pdf_already_exists:
        console.print(f"[dim]✓ PDF already downloaded (cached): {pdf_path}[/dim]")

    # Add to database
    try:
        cursor = db.conn.cursor()
        now = datetime.now().isoformat()

        cursor.execute("""
            INSERT INTO books (
                title, author, publication_year, subjects,
                source, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            title,
            author,
            publication_year,
            ", ".join(subjects) if subjects else None,
            "internet_archive",
            f"IA Identifier: {identifier}",
            now
        ))

        db.conn.commit()
        book_id = cursor.lastrowid

        console.print(Panel.fit(
            f"[green]✓[/green] Added to Holocene collection!\n\n"
            f"[bold]{title}[/bold]\n"
            f"{author or 'Unknown author'}\n"
            f"{publication_year or 'Unknown year'}",
            title="📚 Book Added from Internet Archive"
        ))

        # Download PDF if requested and not already cached
        pdf_downloaded = False
        if download_pdf and not pdf_already_exists:
            console.print(f"\n[cyan]Downloading PDF...[/cyan]")
            success = client.download_pdf(identifier, pdf_path)

            if success:
                pdf_downloaded = True
                # Update book record with PDF path
                cursor.execute("""
                    UPDATE books
                    SET notes = ?
                    WHERE id = ?
                """, (f"IA Identifier: {identifier}\nPDF: {pdf_path}", book_id))
                db.conn.commit()

                console.print(f"[green]✓[/green] PDF downloaded to: {pdf_path}")
        elif download_pdf and pdf_already_exists:
            pdf_downloaded = True

        # Decide whether to add to Calibre
        should_add_to_calibre = False
        if add_to_calibre:
            should_add_to_calibre = True
        elif not no_calibre and config.integrations.calibre_enabled:
            if config.integrations.calibre_auto_add_ia_books and (download_pdf or pdf_already_exists):
                should_add_to_calibre = True

        # Add to Calibre if appropriate
        if should_add_to_calibre and (pdf_downloaded or pdf_already_exists):
            console.print(f"\n[cyan]Adding to Calibre library...[/cyan]")

            calibre = CalibreIntegration(
                library_path=config.integrations.calibre_library_path,
                content_server_port=config.integrations.calibre_content_server_port,
                username=config.integrations.calibre_username,
                password=config.integrations.calibre_password
            )

            # Check if calibredb is available
            if not calibre.is_available():
                console.print("[yellow]⚠️  Calibre not found. Skipping Calibre integration.[/yellow]")
            else:
                # Build tags: source + holocene marker + era
                tags = ["internet_archive", "holocene"]

                # Add pre-LLM tag if applicable
                if publication_year:
                    try:
                        year_int = int(publication_year[:4])
                        if year_int < 2022:
                            tags.append("pre-llm")
                    except (ValueError, TypeError):
                        pass

                # Add to Calibre
                success = calibre.add_book(
                    pdf_path=pdf_path,
                    title=title,
                    authors=creators if creators else None,
                    tags=tags,
                    pubdate=publication_year,
                    comments=f"Downloaded from Internet Archive: https://archive.org/details/{identifier}"
                )

                if success:
                    console.print(f"[green]✓[/green] Added to Calibre with tags: {', '.join(tags)}")
                    # Update book notes
                    cursor.execute("""
                        UPDATE books
                        SET notes = ?
                        WHERE id = ?
                    """, (f"IA Identifier: {identifier}\nPDF: {pdf_path}\nAdded to Calibre", book_id))
                    db.conn.commit()

    finally:
        db.close()


@cli.group()
def papers():
    """Manage academic papers collection for research."""
    pass


@papers.command("search")
@click.argument("query")
@click.option("--limit", "-l", type=int, default=20, help="Number of results")
@click.option("--pre-llm", is_flag=True, help="Only show pre-LLM papers (before Nov 2022)")
def papers_search(query: str, limit: int, pre_llm: bool):
    """Search Crossref for academic papers."""
    from ..research import CrossrefClient

    console.print(f"[cyan]Searching Crossref for:[/cyan] {query}\n")

    client = CrossrefClient()

    with console.status("[bold cyan]Fetching papers...", spinner="dots"):
        if pre_llm:
            results = client.search_pre_llm(query, limit=limit)
        else:
            response = client.search(query, limit=limit)
            if response.get("status") == "error":
                console.print(f"[red]Error:[/red] {response.get('message')}")
                return

            items = response.get("message", {}).get("items", [])
            results = [client.parse_paper(item) for item in items]

    if not results:
        console.print("[yellow]No papers found[/yellow]")
        return

    console.print(f"[cyan]Found {len(results)} papers:[/cyan]\n")

    for i, paper in enumerate(results, 1):
        authors_str = ", ".join(paper.get("authors", [])[:3])
        if len(paper.get("authors", [])) > 3:
            authors_str += " et al."

        console.print(f"{i}. [bold]{paper.get('title', 'Untitled')}[/bold]")
        if authors_str:
            console.print(f"   {authors_str}")
        if paper.get("journal"):
            console.print(f"   {paper['journal']}", end="")
            if paper.get("publication_date"):
                console.print(f" ({paper['publication_date']})")
            else:
                console.print()
        console.print(f"   [dim]DOI: {paper.get('doi', 'N/A')}[/dim]")
        if paper.get("cited_by_count"):
            console.print(f"   [dim]Cited by: {paper['cited_by_count']} papers[/dim]")
        console.print()


@papers.command("add")
@click.argument("doi")
@click.option("--notes", "-n", help="Add notes about this paper")
def papers_add(doi: str, notes: str):
    """Add a paper to your collection by DOI."""
    from ..research import CrossrefClient, UnpaywallClient

    config = load_config()
    db = Database(config.db_path)
    crossref = CrossrefClient()
    unpaywall = UnpaywallClient()

    # Check if already exists
    existing = db.get_paper_by_doi(doi)
    if existing:
        console.print(f"[yellow]Paper already in your collection:[/yellow]")
        console.print(f"  {existing.get('title')}")
        db.close()
        return

    console.print(f"[cyan]Fetching paper metadata from Crossref...[/cyan]")

    paper_data = crossref.get_by_doi(doi)

    if not paper_data:
        console.print(f"[red]✗[/red] Paper not found with DOI: {doi}")
        db.close()
        return

    paper = crossref.parse_paper(paper_data)

    # Check Open Access status via Unpaywall
    console.print(f"[cyan]Checking Open Access status via Unpaywall...[/cyan]")
    oa_info = {}
    unpaywall_data = unpaywall.get_oa_status(doi)
    if unpaywall_data:
        oa_info = unpaywall.parse_oa_info(unpaywall_data)

    # Add to database
    try:
        paper_id = db.add_paper(
            title=paper.get("title"),
            authors=paper.get("authors"),
            doi=paper["doi"],
            abstract=paper.get("abstract"),
            publication_date=paper.get("publication_date"),
            journal=paper.get("journal"),
            url=paper.get("url"),
            references=paper.get("references"),
            cited_by_count=paper.get("cited_by_count", 0),
            notes=notes,
            is_open_access=oa_info.get("is_open_access", False),
            pdf_url=oa_info.get("pdf_url"),
            oa_status=oa_info.get("oa_status"),
            oa_color=oa_info.get("oa_color")
        )

        # Build output message
        oa_indicator = ""
        if oa_info.get("is_open_access"):
            oa_indicator = f"\n{oa_info.get('oa_color', '🟢')} Open Access ({oa_info.get('oa_status', 'unknown')})"
            if oa_info.get("pdf_url"):
                oa_indicator += f"\nPDF: {oa_info['pdf_url'][:60]}..."

        console.print(Panel.fit(
            f"[green]✓[/green] Added to collection!\n\n"
            f"[bold]{paper.get('title')}[/bold]\n"
            f"{', '.join(paper.get('authors', [])[:3])}\n"
            f"{paper.get('journal', 'Unknown journal')} ({paper.get('publication_date', 'Unknown date')})"
            f"{oa_indicator}",
            title="📄 Paper Added"
        ))

    finally:
        db.close()


@papers.command("list")
@click.option("--limit", "-l", type=int, default=20, help="Number of papers to show")
@click.option("--search", "-s", help="Search in title or abstract")
@click.option("--oa-only", is_flag=True, help="Only show Open Access papers")
def papers_list(limit: int, search: str, oa_only: bool):
    """List papers in your collection."""
    config = load_config()
    db = Database(config.db_path)

    papers_list = db.get_papers(search=search, limit=limit, oa_only=oa_only)

    if not papers_list:
        console.print("[yellow]No papers found.[/yellow]")
        console.print("Add papers with: [cyan]holo papers add <DOI>[/cyan]")
        db.close()
        return

    console.print(f"[cyan]Papers in your collection ({len(papers_list)} shown):[/cyan]\n")

    for i, paper in enumerate(papers_list, 1):
        authors_str = ", ".join(paper.get("authors", [])[:2])
        if len(paper.get("authors", [])) > 2:
            authors_str += " et al."

        console.print(f"{i}. [bold]{paper.get('title', 'Untitled')}[/bold]")
        if authors_str:
            console.print(f"   {authors_str}")
        if paper.get("journal"):
            console.print(f"   {paper['journal']}", end="")
            if paper.get("publication_date"):
                console.print(f" ({paper['publication_date']})")
            else:
                console.print()
        console.print(f"   [dim]DOI: {paper.get('doi')}[/dim]")

        # Show OA status if available
        if paper.get("is_open_access"):
            oa_color = paper.get("oa_color", "🟢")
            oa_status = paper.get("oa_status", "open access")
            console.print(f"   {oa_color} Open Access ({oa_status})")

        if paper.get("notes"):
            console.print(f"   [dim]Note: {paper['notes']}[/dim]")
        console.print()

    db.close()


@papers.command("download")
@click.argument("doi")
@click.option("--output", "-o", type=click.Path(), help="Output directory (default: ~/.holocene/papers/)")
def papers_download(doi: str, output: str):
    """Download PDF for an Open Access paper."""
    import requests
    from pathlib import Path

    config = load_config()
    db = Database(config.db_path)

    # Check if paper exists in database
    paper = db.get_paper_by_doi(doi)

    if not paper:
        console.print(f"[yellow]Paper not in your collection. Add it first:[/yellow]")
        console.print(f"  [cyan]holo papers add {doi}[/cyan]")
        db.close()
        return

    if not paper.get("is_open_access"):
        console.print(f"[red]✗[/red] This paper is not Open Access")
        console.print(f"   DOI: {doi}")
        if paper.get("url"):
            console.print(f"   Publisher URL: {paper['url']}")
        db.close()
        return

    pdf_url = paper.get("pdf_url")
    if not pdf_url:
        console.print(f"[yellow]⚠️[/yellow] Paper is Open Access but no PDF URL found")
        if paper.get("url"):
            console.print(f"   Try accessing manually: {paper['url']}")
        db.close()
        return

    # Determine output path
    if output:
        output_dir = Path(output)
    else:
        output_dir = config.data_dir / "papers"

    output_dir.mkdir(parents=True, exist_ok=True)

    # Create safe filename from DOI
    safe_doi = doi.replace("/", "_").replace(":", "_")
    output_file = output_dir / f"{safe_doi}.pdf"

    console.print(f"[cyan]Downloading PDF...[/cyan]")
    console.print(f"  From: {pdf_url}")
    console.print(f"  To: {output_file}")

    try:
        response = requests.get(pdf_url, timeout=60, stream=True)
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))
        downloaded = 0

        with open(output_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    pct = (downloaded / total_size) * 100
                    console.print(f"  Progress: {pct:.1f}%", end="\r")

        console.print()  # New line after progress
        console.print(f"[green]✓[/green] Downloaded successfully!")
        console.print(f"  {output_file}")

    except Exception as e:
        console.print(f"[red]✗[/red] Download failed: {e}")
        if output_file.exists():
            output_file.unlink()  # Remove partial file

    finally:
        db.close()


@papers.command("analyze")
@click.argument("paper_id", type=int, required=False)
@click.option("--all-incomplete", is_flag=True, help="Analyze all papers not fully analyzed")
@click.option("--filter-status", type=click.Choice(["to_read", "reading", "completed", "reference"]),
              help="Only analyze papers with this reading status")
@click.option("--full-text", is_flag=True, help="Analyze entire PDF (slow)")
@click.option("--pages", type=int, default=15, help="Number of pages to analyze (default: 15)")
def papers_analyze(paper_id: int, all_incomplete: bool, filter_status: str, full_text: bool, pages: int):
    """
    Re-analyze papers with DeepSeek V3 to generate summaries.

    Examples:
        holo papers analyze 15                    # Analyze paper ID 15
        holo papers analyze --all-incomplete      # All papers without summaries
        holo papers analyze --filter-status=reading  # Only papers you're reading
    """
    from pathlib import Path
    from ..research import PDFMetadataExtractor
    from datetime import datetime

    config = load_config()
    db = Database(config.db_path)

    # Determine which papers to analyze
    papers_to_analyze = []

    if paper_id:
        # Single paper
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
        row = cursor.fetchone()
        if row:
            papers_to_analyze.append(dict(row))
        else:
            console.print(f"[red]✗[/red] Paper ID {paper_id} not found")
            db.close()
            return
    elif all_incomplete:
        # All papers without summaries or not fully analyzed
        cursor = db.conn.cursor()
        query = "SELECT * FROM papers WHERE (summary IS NULL OR summary = '') OR full_text_analyzed = 0"
        if filter_status:
            query += f" AND reading_status = '{filter_status}'"
        cursor.execute(query)
        papers_to_analyze = [dict(row) for row in cursor.fetchall()]
    else:
        console.print("[yellow]⚠[/yellow]  Specify either a paper ID or --all-incomplete")
        console.print("Examples:")
        console.print("  holo papers analyze 15")
        console.print("  holo papers analyze --all-incomplete")
        db.close()
        return

    if not papers_to_analyze:
        console.print("[yellow]No papers to analyze[/yellow]")
        db.close()
        return

    total = len(papers_to_analyze)
    console.print(f"[cyan]Analyzing {total} paper(s) with DeepSeek V3...[/cyan]\n")

    extractor = PDFMetadataExtractor(config)
    success_count = 0
    fail_count = 0

    for idx, paper in enumerate(papers_to_analyze, 1):
        if total > 1:
            console.print(f"\n[cyan]═══ Analyzing {idx}/{total}: {paper.get('title', 'Untitled')[:60]}... ═══[/cyan]")

        # Get PDF path
        pdf_path = None
        if paper.get('local_pdf_path'):
            pdf_path = Path(paper['local_pdf_path'])

        if not pdf_path or not pdf_path.exists():
            console.print(f"[yellow]⚠[/yellow] No local PDF found, skipping...")
            fail_count += 1
            continue

        try:
            # Extract with summary
            console.print(f"[cyan]Generating summary from {'entire PDF' if full_text else f'first {pages} pages'}...[/cyan]")

            metadata = extractor.extract_metadata(
                pdf_path,
                max_pages=pages,
                full_text=full_text,
                extract_summary=True  # Always extract summary when analyzing
            )

            if "error" in metadata:
                console.print(f"[red]✗[/red] Analysis failed: {metadata.get('error')}")
                fail_count += 1
                continue

            # Update database with summary and analysis info
            cursor = db.conn.cursor()
            cursor.execute("""
                UPDATE papers
                SET summary = ?,
                    analysis_pages = ?,
                    total_pages = ?,
                    full_text_analyzed = ?,
                    last_analyzed_at = ?
                WHERE id = ?
            """, (
                metadata.get("summary"),
                metadata.get("analysis_pages"),
                metadata.get("total_pages"),
                1 if metadata.get("full_text_analyzed") else 0,
                datetime.now().isoformat(),
                paper['id']
            ))
            db.conn.commit()

            console.print(f"[green]✓[/green] Summary generated and saved")
            if metadata.get("summary"):
                # Show first line of summary
                first_line = metadata["summary"].split('\n')[0][:80]
                console.print(f"   [dim]{first_line}...[/dim]")

            success_count += 1

        except Exception as e:
            console.print(f"[red]✗[/red] Failed: {e}")
            fail_count += 1
            continue

    # Show summary
    console.print(f"\n[cyan]Analysis complete![/cyan]")
    console.print(f"[green]✓ Success:[/green] {success_count}")
    console.print(f"[red]✗ Failed:[/red] {fail_count}")

    db.close()


@papers.command("import-bib")
@click.argument("bib_file", type=click.Path(exists=True))
@click.option("--oa-only", is_flag=True, help="Only import Open Access papers")
@click.option("--download", is_flag=True, help="Auto-download OA papers after importing")
@click.option("--dry-run", is_flag=True, help="Show what would be imported without actually importing")
def papers_import_bib(bib_file: str, oa_only: bool, download: bool, dry_run: bool):
    """Import papers from a BibTeX file (e.g., thesis bibliography)."""
    from pathlib import Path
    from ..research import BibTeXImporter, CrossrefClient, UnpaywallClient
    import time

    config = load_config()
    db = Database(config.db_path)
    bibtex = BibTeXImporter()
    crossref = CrossrefClient()
    unpaywall = UnpaywallClient()

    console.print(f"[cyan]Parsing BibTeX file:[/cyan] {bib_file}\n")

    # Parse BibTeX
    try:
        entries = bibtex.parse_file(Path(bib_file))
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to parse BibTeX file: {e}")
        db.close()
        return

    categorized = bibtex.categorize_entries(entries)

    console.print(f"[cyan]Found {categorized['total']} entries:[/cyan]")
    console.print(f"  • With DOI: {len(categorized['with_doi'])}")
    console.print(f"  • Without DOI: {len(categorized['without_doi'])}\n")

    if dry_run:
        console.print("[yellow]DRY RUN - No papers will be imported[/yellow]\n")

    # Process entries
    imported = 0
    skipped = 0
    oa_count = 0
    failed = 0

    for i, entry in enumerate(entries, 1):
        console.print(f"[{i}/{len(entries)}] {entry['title'][:60]}...")

        # Check if already exists
        if entry.get('doi'):
            existing = db.get_paper_by_doi(entry['doi'])
            if existing:
                console.print(f"  [dim]↷ Already in collection[/dim]")
                skipped += 1
                continue

        # Get DOI if we don't have one
        doi = entry.get('doi')
        if not doi and entry.get('search_query'):
            console.print(f"  [dim]Searching Crossref for DOI...[/dim]")
            search_result = crossref.search(entry['search_query'], limit=1)
            if search_result.get('message', {}).get('items'):
                first_result = search_result['message']['items'][0]
                doi = first_result.get('DOI')
                if doi:
                    console.print(f"  [dim]✓ Found DOI: {doi}[/dim]")
            time.sleep(0.1)  # Be polite to Crossref

        if not doi:
            console.print(f"  [yellow]⚠ No DOI found, skipping[/yellow]")
            failed += 1
            continue

        # Get full metadata from Crossref
        paper_data = crossref.get_by_doi(doi)
        if not paper_data:
            console.print(f"  [yellow]⚠ Could not fetch from Crossref[/yellow]")
            failed += 1
            continue

        paper = crossref.parse_paper(paper_data)

        # Check OA status
        oa_info = {}
        unpaywall_data = unpaywall.get_oa_status(doi)
        if unpaywall_data:
            oa_info = unpaywall.parse_oa_info(unpaywall_data)

        # Filter by OA if requested
        if oa_only and not oa_info.get('is_open_access'):
            console.print(f"  [dim]↷ Not Open Access, skipping[/dim]")
            skipped += 1
            continue

        # Import paper
        if not dry_run:
            try:
                db.add_paper(
                    title=paper.get("title"),
                    authors=paper.get("authors"),
                    doi=paper["doi"],
                    abstract=paper.get("abstract"),
                    publication_date=paper.get("publication_date"),
                    journal=paper.get("journal"),
                    url=paper.get("url"),
                    references=paper.get("references"),
                    cited_by_count=paper.get("cited_by_count", 0),
                    notes=f"Imported from BibTeX: {entry['bibtex_key']}",
                    is_open_access=oa_info.get("is_open_access", False),
                    pdf_url=oa_info.get("pdf_url"),
                    oa_status=oa_info.get("oa_status"),
                    oa_color=oa_info.get("oa_color")
                )
                imported += 1

                if oa_info.get('is_open_access'):
                    oa_count += 1
                    oa_indicator = f"{oa_info.get('oa_color', '🟢')} {oa_info.get('oa_status', 'OA')}"
                    console.print(f"  [green]✓[/green] Imported ({oa_indicator})")
                else:
                    console.print(f"  [green]✓[/green] Imported")

            except Exception as e:
                console.print(f"  [red]✗[/red] Import failed: {e}")
                failed += 1
        else:
            imported += 1
            if oa_info.get('is_open_access'):
                oa_count += 1
                console.print(f"  [dim]Would import ({oa_info.get('oa_color', '🟢')} {oa_info.get('oa_status', 'OA')})[/dim]")
            else:
                console.print(f"  [dim]Would import[/dim]")

        time.sleep(0.15)  # Be polite to APIs

    # Summary
    console.print()
    if dry_run:
        console.print(Panel.fit(
            f"[cyan]Dry Run Complete[/cyan]\n\n"
            f"Would import: {imported} papers\n"
            f"Open Access: {oa_count} papers\n"
            f"Skipped: {skipped}\n"
            f"Failed: {failed}",
            title="📊 Import Summary"
        ))
    else:
        console.print(Panel.fit(
            f"[green]✓[/green] Import Complete!\n\n"
            f"Imported: {imported} papers\n"
            f"Open Access: {oa_count} papers\n"
            f"Skipped: {skipped}\n"
            f"Failed: {failed}",
            title="📊 Import Summary"
        ))

        # Batch download if requested
        if download and oa_count > 0:
            console.print(f"\n[cyan]Downloading {oa_count} Open Access PDFs...[/cyan]\n")
            # Get all OA papers we just imported
            oa_papers = db.get_papers(oa_only=True, limit=1000)
            output_dir = config.data_dir / "papers"
            output_dir.mkdir(parents=True, exist_ok=True)

            downloaded = 0
            for paper in oa_papers:
                if not paper.get('pdf_url'):
                    continue

                safe_doi = paper['doi'].replace("/", "_").replace(":", "_")
                output_file = output_dir / f"{safe_doi}.pdf"

                if output_file.exists():
                    continue  # Already downloaded

                try:
                    import requests
                    console.print(f"  Downloading: {paper['title'][:50]}...")
                    response = requests.get(paper['pdf_url'], timeout=60, stream=True)
                    response.raise_for_status()

                    with open(output_file, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)

                    downloaded += 1
                    console.print(f"  [green]✓[/green] Downloaded")
                    time.sleep(0.5)  # Be polite

                except Exception as e:
                    console.print(f"  [yellow]⚠[/yellow] Download failed: {e}")

            console.print(f"\n[green]✓[/green] Downloaded {downloaded} PDFs to {output_dir}")

    db.close()


@cli.command()
@click.option("--raw", is_flag=True, help="Show raw API response")
def usage(raw: bool):
    """Show LLM API usage statistics from NanoGPT."""
    from ..llm import BudgetTracker
    from datetime import datetime

    config = load_config()
    tracker = BudgetTracker(
        data_dir=config.data_dir,
        daily_limit=config.llm.daily_budget,
        api_key=config.llm.api_key,
        base_url=config.llm.base_url
    )

    # Fetch from API
    api_data = tracker.get_usage_details()

    if api_data:
        if raw:
            # Show raw JSON
            console.print(Panel.fit(
                f"[cyan]NanoGPT API Response[/cyan]\n\n"
                f"{json.dumps(api_data, indent=2)}",
                title="📊 Raw API Data"
            ))
        else:
            # Show formatted output
            daily = api_data.get("daily", {})
            monthly = api_data.get("monthly", {})
            limits = api_data.get("limits", {})

            # Parse reset time
            reset_timestamp = daily.get("resetAt", 0) / 1000  # Convert ms to seconds
            reset_time = datetime.fromtimestamp(reset_timestamp).strftime("%Y-%m-%d %H:%M:%S")

            # Format percentages
            daily_pct = daily.get("percentUsed", 0) * 100
            monthly_pct = monthly.get("percentUsed", 0) * 100

            console.print(Panel.fit(
                f"[cyan]📊 Daily Usage[/cyan]\n"
                f"Used: {daily.get('used', 0)} / {limits.get('daily', 0)} calls ({daily_pct:.1f}%)\n"
                f"Remaining: {daily.get('remaining', 0)} calls\n"
                f"Resets at: {reset_time}\n\n"
                f"[cyan]📈 Monthly Usage[/cyan]\n"
                f"Used: {monthly.get('used', 0)} / {limits.get('monthly', 0)} calls ({monthly_pct:.2f}%)\n"
                f"Remaining: {monthly.get('remaining', 0)} calls",
                title="🤖 NanoGPT Subscription"
            ))
    else:
        console.print("[yellow]Could not fetch usage from NanoGPT API[/yellow]")
        console.print("[dim]Falling back to local tracking[/dim]\n")

        today_usage = tracker.get_today_usage()
        remaining = tracker.remaining_budget()

        console.print(Panel.fit(
            f"[cyan]Local Usage Tracking[/cyan]\n\n"
            f"Today's usage: {today_usage} calls\n"
            f"Daily budget: {config.llm.daily_budget} calls\n"
            f"Remaining: {remaining} calls",
            title="📊 Local Usage"
        ))


@cli.group()
def open():
    """Open PDFs from your collection."""
    pass


@open.command("book")
@click.argument("identifier")
def open_book(identifier: str):
    """
    Open a book PDF.

    IDENTIFIER can be:
    - Book ID number
    - Part of the book title (will search and open first match)
    """
    import subprocess
    import platform

    config = load_config()
    db = Database(config.db_path)

    # Try as ID first
    book = None
    try:
        book_id = int(identifier)
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM books WHERE id = ?", (book_id,))
        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            book = dict(zip(columns, row))
    except ValueError:
        # Not an ID, search by title
        books = db.get_books(search=identifier, limit=1)
        if books:
            book = books[0]

    if not book:
        console.print(f"[red]✗[/red] No book found matching '{identifier}'")
        console.print(f"  Try: [cyan]holo books list --search=\"{identifier}\"[/cyan]")
        db.close()
        return

    # Check for local PDF
    pdf_path = None

    # Check local_pdf_path field first
    if book.get("local_pdf_path"):
        pdf_path = Path(book["local_pdf_path"])

    # Fallback: Check old IA location
    if not pdf_path or not pdf_path.exists():
        # Try internet_archive directory
        ia_dir = config.data_dir / "books" / "internet_archive"
        # Try to find PDF by book source if it's from IA
        if book.get("source") == "internet_archive":
            # Search for PDF files in IA directory
            # Extract keywords from book title
            title_words = book["title"].lower().split()
            # Remove common words
            skip_words = {"the", "a", "an", "of", "in", "on", "at", "to", "for", "and", "or"}
            keywords = [w for w in title_words if len(w) > 3 and w not in skip_words]

            best_match = None
            best_score = 0

            for pdf_file in ia_dir.glob("*.pdf"):
                filename = pdf_file.stem.lower()
                # Count matching keywords
                score = sum(1 for kw in keywords if kw in filename)
                if score > best_score:
                    best_score = score
                    best_match = pdf_file

            # Use best match if we found at least one keyword match
            if best_match and best_score > 0:
                pdf_path = best_match

    if not pdf_path or not pdf_path.exists():
        console.print(f"[yellow]⚠[/yellow]  No PDF found for: {book['title']}")
        console.print(f"   Book ID: {book['id']}")
        if book.get("source") == "internet_archive":
            console.print(f"   Try downloading: [cyan]holo books add-ia <identifier> --download-pdf[/cyan]")
        db.close()
        return

    # Open PDF with default viewer
    console.print(f"[cyan]Opening:[/cyan] {book['title']}")
    console.print(f"[dim]  {pdf_path}[/dim]")

    try:
        if platform.system() == 'Darwin':  # macOS
            subprocess.run(['open', str(pdf_path)])
        elif platform.system() == 'Windows':
            subprocess.run(['cmd', '/c', 'start', '', str(pdf_path)], shell=True)
        else:  # Linux
            subprocess.run(['xdg-open', str(pdf_path)])

        console.print(f"[green]✓[/green] Opened in default PDF viewer")
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to open PDF: {e}")

    db.close()


@open.command("paper")
@click.argument("identifier")
def open_paper(identifier: str):
    """
    Open a paper PDF.

    IDENTIFIER can be:
    - Paper ID number
    - DOI
    - Part of the paper title (will search and open first match)
    """
    import subprocess
    import platform

    config = load_config()
    db = Database(config.db_path)

    # Try as ID first
    paper = None
    try:
        paper_id = int(identifier)
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM papers WHERE id = ?", (paper_id,))
        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            paper = dict(zip(columns, row))
    except ValueError:
        # Try as DOI
        paper = db.get_paper_by_doi(identifier)

        # If not DOI, search by title
        if not paper:
            papers = db.get_papers(search=identifier, limit=1)
            if papers:
                paper = papers[0]

    if not paper:
        console.print(f"[red]✗[/red] No paper found matching '{identifier}'")
        console.print(f"  Try: [cyan]holo papers list --search=\"{identifier}\"[/cyan]")
        db.close()
        return

    # Check for local PDF
    pdf_path = None

    # Check local_pdf_path field first
    if paper.get("local_pdf_path"):
        pdf_path = Path(paper["local_pdf_path"])

    # Fallback: Check old papers location
    if not pdf_path or not pdf_path.exists():
        papers_dir = config.data_dir / "papers"
        # Create safe filename from DOI
        doi = paper["doi"]
        safe_doi = doi.replace("/", "_").replace(":", "_")
        potential_path = papers_dir / f"{safe_doi}.pdf"
        if potential_path.exists():
            pdf_path = potential_path

    if not pdf_path or not pdf_path.exists():
        console.print(f"[yellow]⚠[/yellow]  No PDF found for: {paper['title']}")
        console.print(f"   DOI: {paper['doi']}")
        if paper.get("is_open_access"):
            console.print(f"   Try downloading: [cyan]holo papers download {paper['doi']}[/cyan]")
        else:
            console.print(f"   This paper is not Open Access")
            if paper.get("url"):
                console.print(f"   Publisher URL: {paper['url']}")
        db.close()
        return

    # Open PDF with default viewer
    console.print(f"[cyan]Opening:[/cyan] {paper['title']}")
    console.print(f"[dim]  {pdf_path}[/dim]")

    try:
        if platform.system() == 'Darwin':  # macOS
            subprocess.run(['open', str(pdf_path)])
        elif platform.system() == 'Windows':
            subprocess.run(['cmd', '/c', 'start', '', str(pdf_path)], shell=True)
        else:  # Linux
            subprocess.run(['xdg-open', str(pdf_path)])

        console.print(f"[green]✓[/green] Opened in default PDF viewer")
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to open PDF: {e}")

    db.close()


@cli.command("add-pdf")
@click.argument("pdf_files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--type", "item_type", type=click.Choice(["book", "paper", "auto"]), default="auto",
              help="Force type (auto-detect if not specified)")
@click.option("--doi", help="Manually specify DOI (for papers, only works with single file)")
@click.option("--isbn", help="Manually specify ISBN (for books, only works with single file)")
@click.option("--status", "reading_status", type=click.Choice(["to_read", "reading", "completed", "reference"]),
              help="Set reading status on import")
@click.option("--full-text", is_flag=True, help="Extract and analyze entire PDF (slow)")
@click.option("--pages", type=int, help="Number of pages to extract (default: 5, or 15 with --summary)")
@click.option("--summary", "extract_summary", is_flag=True, help="Generate detailed summary with DeepSeek V3")
def add_pdf(pdf_files: tuple, item_type: str, doi: str, isbn: str, reading_status: str,
            full_text: bool, pages: int, extract_summary: bool):
    """
    Add PDF(s) to your collection with automatic metadata extraction.

    Supports multiple files and wildcards. Uses DeepSeek V3 to extract
    metadata from PDFs, then adds them to your papers or books collection.

    Examples:
        holo add-pdf paper.pdf
        holo add-pdf *.pdf
        holo add-pdf paper1.pdf paper2.pdf paper3.pdf
        holo add-pdf papers/*.pdf --status=to_read
        holo add-pdf paper.pdf --summary --full-text  # Deep analysis with summary
        holo add-pdf paper.pdf --summary --pages=20   # Summary from first 20 pages
    """
    from ..research import PDFMetadataExtractor, CrossrefClient, UnpaywallClient
    import shutil
    from glob import glob

    # Validate single-file options
    if len(pdf_files) > 1 and (doi or isbn):
        console.print("[yellow]⚠[/yellow]  --doi and --isbn only work with single files")
        console.print("  Processing without manual identifiers...")
        doi = None
        isbn = None

    # Expand glob patterns (in case shell didn't expand them)
    all_files = []
    for pattern in pdf_files:
        if '*' in pattern or '?' in pattern:
            expanded = glob(pattern)
            all_files.extend(expanded)
        else:
            all_files.append(pattern)

    if not all_files:
        console.print("[red]✗[/red] No PDF files found")
        return

    # Convert to Path objects
    pdf_paths = [Path(f) for f in all_files]
    total = len(pdf_paths)

    if total > 1:
        console.print(Panel.fit(
            f"[cyan]Bulk PDF Import[/cyan]\n\n"
            f"Files to process: {total}",
            title="📄 Batch Import"
        ))

    config = load_config()
    db = Database(config.db_path)

    success_count = 0
    fail_count = 0
    skip_count = 0

    for idx, pdf_path in enumerate(pdf_paths, 1):
        if total > 1:
            console.print(f"\n[cyan]═══ Processing {idx}/{total}: {pdf_path.name} ═══[/cyan]")

        try:
            # Extract metadata using DeepSeek V3
            if extract_summary:
                console.print("[cyan]Extracting metadata and generating summary with DeepSeek V3...[/cyan]")
            else:
                console.print("[cyan]Extracting metadata with DeepSeek V3...[/cyan]")

            extractor = PDFMetadataExtractor(config)

            try:
                metadata = extractor.extract_metadata(
                    pdf_path,
                    max_pages=pages,
                    full_text=full_text,
                    extract_summary=extract_summary
                )
            except Exception as e:
                console.print(f"[red]✗[/red] Failed to extract metadata: {e}")
                fail_count += 1
                continue

            # Check for errors
            if "error" in metadata:
                console.print(f"[yellow]⚠[/yellow] Extraction had issues:")
                console.print(f"  {metadata.get('error')}")
                if metadata.get("confidence", "").lower() == "low":
                    console.print("[yellow]Skipping due to low confidence...[/yellow]")
                    skip_count += 1
                    continue

            # Display extracted metadata
            console.print("[green]✓[/green] Metadata extracted:")
            console.print(f"  Type: {metadata.get('type', 'unknown')}")
            console.print(f"  Title: {metadata.get('title', 'Unknown')}")
            console.print(f"  Authors: {', '.join(metadata.get('authors', []))}")
            if metadata.get('doi'):
                console.print(f"  DOI: {metadata['doi']}")

            # Override with manual values (only for single file)
            if len(pdf_paths) == 1:
                if doi:
                    metadata['doi'] = doi
                    metadata['type'] = 'paper'
                if isbn:
                    metadata['isbn'] = isbn
                    metadata['type'] = 'book'
            if item_type != "auto":
                metadata['type'] = item_type

            # Determine final type
            final_type = metadata.get('type', 'unknown')
            if final_type == 'unknown':
                # Guess based on what identifiers we have
                if metadata.get('doi'):
                    final_type = 'paper'
                elif metadata.get('isbn'):
                    final_type = 'book'
                else:
                    console.print("[yellow]Cannot determine type, skipping...[/yellow]")
                    skip_count += 1
                    continue

            console.print(f"[cyan]Importing as: {final_type}[/cyan]")

            # Create library directory
            library_dir = config.data_dir / "library" / f"{final_type}s"
            library_dir.mkdir(parents=True, exist_ok=True)

            if final_type == "paper":
                # Add to papers collection
                from ..research import OpenAlexClient

                paper_doi = metadata.get('doi') or None  # Convert empty string to None
                title = metadata.get('title', '')
                authors = metadata.get('authors', [])
                first_author = authors[0] if authors else ''
                year = metadata.get('year')

                # Check for duplicates using fallback hierarchy
                existing = db.find_duplicate_paper(
                    doi=paper_doi,
                    title=title,
                    first_author=first_author,
                    year=year
                )
                if existing:
                    console.print(f"[yellow]⚠[/yellow] Paper already in collection (ID: {existing['id']}), skipping...")
                    skip_count += 1
                    continue

                # Try to enrich metadata from external sources
                paper = None
                oa_info = {}

                if paper_doi:
                    # Try Crossref first
                    console.print(f"[cyan]Fetching from Crossref...[/cyan]")
                    crossref = CrossrefClient()
                    paper_data = crossref.get_by_doi(paper_doi)
                    if paper_data:
                        paper = crossref.parse_paper(paper_data)

                        # Check OA status
                        console.print(f"[cyan]Checking OA status...[/cyan]")
                        unpaywall = UnpaywallClient()
                        unpaywall_data = unpaywall.get_oa_status(paper_doi)
                        if unpaywall_data:
                            oa_info = unpaywall.parse_oa_info(unpaywall_data)

                # If no DOI or Crossref failed, try OpenAlex
                if not paper:
                    console.print("[yellow]Searching OpenAlex...[/yellow]")
                    openalex = OpenAlexClient()

                    if paper_doi:
                        # Search by DOI
                        work = openalex.get_by_doi(paper_doi)
                    else:
                        # Search by title + author
                        results = openalex.search_by_title_author(title, first_author, year)
                        work = results[0] if results else None

                    if work:
                        paper = openalex.parse_paper(work)
                        paper_doi = paper.get('doi') or paper_doi  # Use OpenAlex DOI if found
                        oa_info = {
                            'is_open_access': paper.get('is_open_access', False),
                            'oa_status': paper.get('oa_status'),
                            'pdf_url': paper.get('pdf_url')
                        }
                        console.print(f"[green]✓[/green] Found in OpenAlex!")
                        if paper_doi:
                            console.print(f"  DOI: {paper_doi}")

                # If still no metadata, use what DeepSeek V3 extracted
                if not paper:
                    console.print("[yellow]Using metadata from PDF extraction only[/yellow]")
                    paper = {
                        'title': title,
                        'authors': authors,
                        'abstract': metadata.get('abstract'),
                        'journal': metadata.get('journal'),
                        'publisher': metadata.get('publisher'),
                        'year': year,
                        'publication_date': str(year) if year else None,
                        'url': None,
                        'references': [],
                        'cited_by_count': 0
                    }

                # Copy PDF to library
                if paper_doi:
                    safe_doi = paper_doi.replace("/", "_").replace(":", "_")
                    dest_path = library_dir / f"{safe_doi}.pdf"
                else:
                    # Use sanitized title if no DOI
                    safe_title = "".join(c for c in title[:50] if c.isalnum() or c in (' ', '-', '_')).replace(' ', '_')
                    dest_path = library_dir / f"{safe_title}.pdf"

                shutil.copy2(pdf_path, dest_path)

                # Add to database
                paper_id = db.add_paper(
                    title=paper.get("title"),
                    authors=paper.get("authors", []),
                    doi=paper_doi,
                    openalex_id=paper.get("openalex_id"),
                    pmid=paper.get("pmid"),
                    abstract=paper.get("abstract"),
                    publication_date=paper.get("publication_date"),
                    journal=paper.get("journal"),
                    url=paper.get("url"),
                    references=paper.get("references", []),
                    cited_by_count=paper.get("cited_by_count", 0),
                    is_open_access=oa_info.get("is_open_access", False),
                    pdf_url=oa_info.get("pdf_url"),
                    oa_status=oa_info.get("oa_status"),
                    oa_color=oa_info.get("oa_color"),
                    notes=f"Imported from PDF: {pdf_path.name}",
                    summary=metadata.get("summary"),
                    analysis_pages=metadata.get("analysis_pages"),
                    total_pages=metadata.get("total_pages"),
                    full_text_analyzed=metadata.get("full_text_analyzed", False)
                )

                # Update with local PDF info and reading status
                cursor = db.conn.cursor()
                cursor.execute("""
                    UPDATE papers
                    SET local_pdf_path = ?, has_local_pdf = 1, downloaded_at = ?,
                        access_status = 'owned_digital', reading_status = ?
                    WHERE id = ?
                """, (str(dest_path), datetime.now().isoformat(), reading_status, paper_id))
                db.conn.commit()

                console.print(f"[green]✓[/green] Added: {paper['title'][:60]}...")
                success_count += 1

            else:  # book
                # Check if already exists (by title)
                existing_books = db.get_books(search=metadata.get('title', ''), limit=1)
                if existing_books and existing_books[0]['title'] == metadata.get('title'):
                    console.print(f"[yellow]⚠[/yellow] Book already in collection, skipping...")
                    skip_count += 1
                    continue

                book_isbn = metadata.get('isbn')

                # Copy PDF to library
                if book_isbn:
                    safe_isbn = book_isbn.replace("-", "")
                    dest_path = library_dir / f"{safe_isbn}.pdf"
                else:
                    # Use sanitized title
                    safe_title = "".join(c for c in metadata.get('title', 'unknown')[:50] if c.isalnum() or c in (' ', '-', '_')).replace(' ', '_')
                    dest_path = library_dir / f"{safe_title}.pdf"

                shutil.copy2(pdf_path, dest_path)

                # Add to database
                book_id = db.add_book(
                    title=metadata.get('title', 'Unknown'),
                    author=', '.join(metadata.get('authors', [])),
                    isbn=book_isbn,
                    publication_year=metadata.get('year'),
                    publisher=metadata.get('publisher'),
                    source='pdf_import',
                    notes=f"Imported from PDF: {pdf_path.name}"
                )

                # Update with local PDF info and reading status
                cursor = db.conn.cursor()
                cursor.execute("""
                    UPDATE books
                    SET local_pdf_path = ?, has_local_pdf = 1, downloaded_at = ?,
                        access_status = 'owned_digital', reading_status = ?
                    WHERE id = ?
                """, (str(dest_path), datetime.now().isoformat(), reading_status, book_id))
                db.conn.commit()

                console.print(f"[green]✓[/green] Added: {metadata.get('title', 'Unknown')[:60]}...")
                success_count += 1

        except Exception as e:
            console.print(f"[red]✗[/red] Failed: {e}")
            fail_count += 1
            continue

    db.close()

    # Show summary for bulk imports
    if total > 1:
        console.print(Panel.fit(
            f"[cyan]Import Complete![/cyan]\n\n"
            f"[green]✓ Success:[/green] {success_count}\n"
            f"[yellow]⚠ Skipped:[/yellow] {skip_count}\n"
            f"[red]✗ Failed:[/red] {fail_count}\n"
            f"[dim]Total:[/dim] {total}",
            title="📊 Import Summary"
        ))


@cli.group()
def research():
    """Deep research mode for overnight context compilation."""
    pass


@research.command("start")
@click.argument("topic")
@click.option("--depth", type=click.Choice(["quick", "deep", "thorough"]), default="quick",
              help="Research depth (quick=10 calls, deep=50, thorough=100)")
@click.option("--no-books", is_flag=True, help="Don't search book collection")
@click.option("--no-papers", is_flag=True, help="Don't search papers collection")
@click.option("--no-vision", is_flag=True, help="Don't analyze figures")
@click.option("--wikipedia", is_flag=True, help="Include Wikipedia background")
def research_start(topic: str, depth: str, no_books: bool, no_papers: bool, no_vision: bool, wikipedia: bool):
    """Start a research session on a topic."""
    from ..research import ResearchOrchestrator

    console.print(Panel.fit(
        f"[cyan]Deep Research Mode[/cyan]\n\n"
        f"Topic: {topic}\n"
        f"Depth: {depth}",
        title="🔬 Research Starting"
    ))

    orchestrator = ResearchOrchestrator()

    try:
        report_path = orchestrator.research(
            topic=topic,
            depth=depth,
            include_books=not no_books,
            include_papers=not no_papers,
            include_vision=not no_vision,
            include_wikipedia=wikipedia
        )

        console.print(f"\n[green]✓[/green] Research report ready!")
        console.print(f"   {report_path}")
        console.print(f"\n[dim]Open with your editor to review findings[/dim]")

    finally:
        orchestrator.close()


@research.command("show")
@click.option("--latest", is_flag=True, help="Show most recent research")
def research_show(latest: bool):
    """Show a research report."""
    config = load_config()
    research_dir = config.data_dir / "research"

    if not research_dir.exists():
        console.print("[yellow]No research reports found[/yellow]")
        console.print("Run: [cyan]holo research start \"your topic\"[/cyan]")
        return

    # Get all research reports
    reports = sorted(research_dir.glob("research-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not reports:
        console.print("[yellow]No research reports found[/yellow]")
        return

    # Show latest
    if latest or len(reports) == 1:
        report_path = reports[0]
        console.print(f"[cyan]Latest research:[/cyan] {report_path.name}\n")

        content = report_path.read_text(encoding="utf-8")
        console.print(content)
    else:
        # Show list to choose from
        console.print("[cyan]Available research reports:[/cyan]\n")
        for i, report in enumerate(reports, 1):
            mtime = datetime.fromtimestamp(report.stat().st_mtime)
            console.print(f"{i}. {report.stem} ({mtime.strftime('%Y-%m-%d %H:%M')})")


@research.command("list")
@click.option("--limit", "-n", type=int, default=10, help="Number of reports to show")
def research_list(limit: int):
    """List past research reports."""
    config = load_config()
    research_dir = config.data_dir / "research"

    if not research_dir.exists():
        console.print("[yellow]No research reports found[/yellow]")
        return

    reports = sorted(research_dir.glob("research-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)

    if not reports:
        console.print("[yellow]No research reports found[/yellow]")
        return

    console.print(f"[cyan]Research Reports ({len(reports)} total)[/cyan]\n")

    for i, report in enumerate(reports[:limit], 1):
        mtime = datetime.fromtimestamp(report.stat().st_mtime)

        # Extract topic from filename
        # Format: research-topic-name-20251117-123456.md
        parts = report.stem.split('-')
        if len(parts) >= 3:
            topic = '-'.join(parts[1:-2])  # Everything between 'research' and timestamp
        else:
            topic = report.stem

        console.print(f"{i}. [bold]{topic}[/bold]")
        console.print(f"   {mtime.strftime('%Y-%m-%d %H:%M')} - {report.name}")
        console.print()


@cli.command()
@click.argument("query")
@click.option("--limit", "-l", type=int, default=5, help="Number of results")
def wikipedia(query: str, limit: int):
    """Search Wikipedia and display article summaries."""
    from ..research import WikipediaClient
    from ..config import load_config

    config = load_config()
    wiki = WikipediaClient(cache_dir=config.data_dir / "wikipedia_cache")

    console.print(f"[cyan]Searching Wikipedia for:[/cyan] {query}\n")

    # Try exact match first
    article = wiki.get_summary(query)

    if article:
        console.print(Panel.fit(
            f"[bold]{article['title']}[/bold]\n\n"
            f"{article['extract']}\n\n"
            f"[dim]{article['url']}[/dim]",
            title="📚 Wikipedia Article"
        ))
    else:
        # Search for articles
        results = wiki.search(query, limit=limit)

        if not results:
            console.print("[yellow]No Wikipedia articles found[/yellow]")
            return

        console.print(f"[cyan]Found {len(results)} articles:[/cyan]\n")

        for i, result in enumerate(results, 1):
            console.print(f"{i}. [bold]{result['title']}[/bold]")
            if result.get('description'):
                console.print(f"   {result['description']}")
            console.print(f"   [dim]{result['url']}[/dim]")
            console.print()



@cli.command("db-status")
def db_status():
    """Show database schema version and migration history."""
    from ..storage.database import Database
    from ..storage import migrations
    from ..config import load_config
    from rich.table import Table

    config = load_config()
    db = Database(config.data_dir / "holocene.db")

    # Get current version
    current_version = migrations.get_current_version(db.conn)
    max_version = max(m['version'] for m in migrations.MIGRATIONS)

    console.print(f"\n[cyan]Database:[/cyan] {config.data_dir / 'holocene.db'}")
    console.print(f"[cyan]Schema Version:[/cyan] {current_version} / {max_version}")

    # Check if up to date
    if current_version == max_version:
        console.print("[green]✓ Database is up to date[/green]\n")
    else:
        console.print(f"[yellow]⚠ {max_version - current_version} pending migration(s)[/yellow]\n")

    # Get migration history
    history = migrations.get_migration_history(db.conn)

    if history:
        # Create table
        table = Table(title="Migration History")
        table.add_column("Version", style="cyan")
        table.add_column("Name", style="white")
        table.add_column("Applied", style="dim")

        for record in history:
            table.add_row(
                f"v{record['version']}",
                record['name'],
                record['applied_at'][:19]  # Trim microseconds
            )

        console.print(table)
        console.print()
    else:
        console.print("[yellow]No migrations applied yet[/yellow]\n")

    db.close()


@cli.group()
def plugins():
    """Manage Holocene plugins."""
    pass


@plugins.command("list")
def plugins_list():
    """List all available plugins and their status."""
    from ..core import HoloceneCore, PluginRegistry
    from rich.table import Table

    core = HoloceneCore()
    registry = PluginRegistry(core, device="wmut")

    console.print("\n[cyan]Discovering plugins...[/cyan]")
    registry.discover_plugins()
    registry.load_all()

    plugins_list = registry.list_plugins()

    if not plugins_list:
        console.print("[yellow]No plugins found[/yellow]\n")
        core.shutdown()
        return

    # Create table
    table = Table(title="Holocene Plugins")
    table.add_column("Name", style="cyan")
    table.add_column("Version", style="dim")
    table.add_column("Status", style="white")
    table.add_column("Description")

    for plugin in plugins_list:
        status = "[green]Loaded[/green]" if plugin['name'] in registry._plugins else "[dim]Not Loaded[/dim]"
        table.add_row(
            plugin['name'],
            plugin.get('version', 'unknown'),
            status,
            plugin.get('description', '')
        )

    console.print()
    console.print(table)
    console.print()

    core.shutdown()


@plugins.command("info")
@click.argument("plugin_name")
def plugins_info(plugin_name: str):
    """Show detailed information about a plugin."""
    from ..core import HoloceneCore, PluginRegistry
    from rich.panel import Panel

    core = HoloceneCore()
    registry = PluginRegistry(core, device="wmut")

    registry.discover_plugins()
    registry.load_all()

    plugin = registry.get_plugin(plugin_name)

    if not plugin:
        console.print(f"[red]Plugin '{plugin_name}' not found[/red]")
        core.shutdown()
        return

    metadata = plugin.get_metadata()

    info_text = f"""[bold]{metadata.get('name', 'Unknown')}[/bold]
Version: {metadata.get('version', 'unknown')}
Description: {metadata.get('description', 'No description')}

Runs On: {', '.join(metadata.get('runs_on', []))}
Requires: {', '.join(metadata.get('requires', [])) or 'None'}

Status: {'[green]Enabled[/green]' if plugin.enabled else '[dim]Disabled[/dim]'}
"""

    console.print()
    console.print(Panel(info_text, title=f"Plugin: {plugin_name}"))
    console.print()

    core.shutdown()


@cli.group()
def stats():
    """View collection statistics and analytics."""
    pass


@stats.command("archives")
def stats_archives():
    """Show archive statistics and link health metrics.

    Displays comprehensive statistics about link archiving:
    - Internet Archive coverage
    - Link health status
    - Trust tier distribution
    - Storage usage
    - Recent archiving activity
    """
    from rich.table import Table
    from rich.panel import Panel

    config = load_config()
    db = Database(config.db_path)

    # Get archive statistics
    cursor = db.conn.cursor()

    # Total links
    cursor.execute("SELECT COUNT(*) FROM links")
    total_links = cursor.fetchone()[0]

    if total_links == 0:
        console.print("[yellow]No links tracked yet.[/yellow]")
        console.print("Start tracking links with: [cyan]holo links scan[/cyan]")
        db.close()
        return

    # Archived links
    cursor.execute("SELECT COUNT(*) FROM links WHERE archived = 1")
    archived_count = cursor.fetchone()[0]

    # Failed links (with retry attempts)
    cursor.execute("SELECT COUNT(*) FROM links WHERE archive_attempts > 0 AND archived = 0")
    failed_count = cursor.fetchone()[0]

    # Pending links (never attempted)
    cursor.execute("SELECT COUNT(*) FROM links WHERE archived = 0 AND archive_attempts = 0")
    pending_count = cursor.fetchone()[0]

    # Link health status
    cursor.execute("SELECT status, COUNT(*) FROM links WHERE status IS NOT NULL GROUP BY status")
    status_counts = dict(cursor.fetchall())

    # Trust tier distribution (archived links only)
    cursor.execute("SELECT trust_tier, COUNT(*) FROM links WHERE archived = 1 AND trust_tier IS NOT NULL GROUP BY trust_tier")
    trust_tier_counts = dict(cursor.fetchall())

    # Recent archiving activity
    cursor.execute("""
        SELECT DATE(archive_date) as date, COUNT(*) as count
        FROM links
        WHERE archive_date IS NOT NULL
        AND DATE(archive_date) >= DATE('now', '-7 days')
        GROUP BY DATE(archive_date)
        ORDER BY date DESC
        LIMIT 7
    """)
    recent_archives = cursor.fetchall()

    # Calculate percentages
    archived_pct = (archived_count / total_links * 100) if total_links > 0 else 0
    failed_pct = (failed_count / total_links * 100) if total_links > 0 else 0
    pending_pct = (pending_count / total_links * 100) if total_links > 0 else 0

    # Build statistics display
    console.print()
    console.print("╭──────────────── Archive Statistics ────────────────╮")
    console.print("│                                                     │")
    console.print(f"│ Total Links: [bold cyan]{total_links:,}[/bold cyan]                                  │")
    console.print("│                                                     │")
    console.print("│ Coverage:                                           │")

    # Internet Archive coverage bar
    bar_width = 30
    archived_bar = int((archived_count / total_links) * bar_width) if total_links > 0 else 0
    archived_bar_str = "█" * archived_bar + "░" * (bar_width - archived_bar)
    console.print(f"│   Internet Archive:    [green]{archived_count:4}[/green] ([green]{archived_pct:5.1f}%[/green])  {archived_bar_str}   │")

    # Failed links
    failed_bar = int((failed_count / total_links) * bar_width) if total_links > 0 else 0
    failed_bar_str = "█" * failed_bar + "░" * (bar_width - failed_bar)
    console.print(f"│   Failed:              [red]{failed_count:4}[/red] ([red]{failed_pct:5.1f}%[/red])  {failed_bar_str}   │")

    # Pending links
    pending_bar = int((pending_count / total_links) * bar_width) if total_links > 0 else 0
    pending_bar_str = "█" * pending_bar + "░" * (bar_width - pending_bar)
    console.print(f"│   Pending:             [yellow]{pending_count:4}[/yellow] ([yellow]{pending_pct:5.1f}%[/yellow])  {pending_bar_str}   │")

    console.print("│                                                     │")

    # Link health section
    if status_counts:
        console.print("│ Link Health:                                        │")
        alive = status_counts.get('alive', 0)
        dead = status_counts.get('dead', 0)
        timeout = status_counts.get('timeout', 0)
        error = status_counts.get('connection_error', 0)
        total_checked = alive + dead + timeout + error
        unchecked = total_links - total_checked

        if alive > 0:
            alive_pct = (alive / total_links * 100) if total_links > 0 else 0
            console.print(f"│   Alive:               [green]{alive:4}[/green] ([green]{alive_pct:5.1f}%[/green])                   │")
        if dead > 0:
            dead_pct = (dead / total_links * 100) if total_links > 0 else 0
            console.print(f"│   Dead:                [red]{dead:4}[/red] ([red]{dead_pct:5.1f}%[/red])                   │")
        if unchecked > 0:
            unchecked_pct = (unchecked / total_links * 100) if total_links > 0 else 0
            console.print(f"│   Unchecked:           [dim]{unchecked:4}[/dim] ([dim]{unchecked_pct:5.1f}%[/dim])                   │")

        console.print("│                                                     │")

    # Trust tier distribution
    if trust_tier_counts:
        console.print("│ Trust Tier Distribution (Archived):                │")
        pre_llm = trust_tier_counts.get('pre-llm', 0)
        early_llm = trust_tier_counts.get('early-llm', 0)
        recent = trust_tier_counts.get('recent', 0)

        if pre_llm > 0:
            console.print(f"│   Pre-LLM:             [green]{pre_llm:4}[/green] (high value)                │")
        if early_llm > 0:
            console.print(f"│   Early-LLM:           [yellow]{early_llm:4}[/yellow] (medium value)             │")
        if recent > 0:
            console.print(f"│   Recent:              [red]{recent:4}[/red] (low value)                │")

        console.print("│                                                     │")

    # Recent activity
    if recent_archives:
        console.print("│ Recent Archiving Activity (last 7 days):           │")
        for date, count in recent_archives[:5]:  # Show up to 5 days
            console.print(f"│   {date}:  [cyan]{count:3}[/cyan] archived                         │")
        console.print("│                                                     │")

    # Last run info (approximate - check most recent archive date)
    cursor.execute("SELECT MAX(archive_date) FROM links WHERE archive_date IS NOT NULL")
    last_archive = cursor.fetchone()[0]
    if last_archive:
        from datetime import datetime
        try:
            last_dt = datetime.fromisoformat(last_archive)
            time_ago = datetime.now() - last_dt
            if time_ago.days > 0:
                time_ago_str = f"{time_ago.days} days ago"
            elif time_ago.seconds > 3600:
                time_ago_str = f"{time_ago.seconds // 3600} hours ago"
            else:
                time_ago_str = f"{time_ago.seconds // 60} minutes ago"
            console.print(f"│ Last Archive: [dim]{time_ago_str}[/dim]                         │")
        except:
            pass

    console.print("╰─────────────────────────────────────────────────────╯")
    console.print()

    # Suggestions
    if pending_count > 0:
        console.print(f"[yellow]Tip:[/yellow] Run [cyan]holo links auto-archive[/cyan] to archive {pending_count} pending link(s)")
    if failed_count > 0:
        console.print(f"[yellow]Tip:[/yellow] {failed_count} failed link(s) will retry according to exponential backoff")

    db.close()


# Register print commands (optional: requires paperang dependencies)
try:
    from .print_commands import print_group
    cli.add_command(print_group, name="print")
except ImportError:
    # Paperang dependencies not installed
    pass

if __name__ == "__main__":
    cli()
