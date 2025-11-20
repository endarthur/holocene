"""Configuration management CLI commands."""

import os
import subprocess
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from pathlib import Path

from holocene.config import load_config, save_config, get_config_path, DEFAULT_CONFIG

console = Console()


@click.group()
def config():
    """Manage Holocene configuration."""
    pass


@config.command()
def show():
    """Show current configuration."""
    config_path = get_config_path()

    if not config_path.exists():
        console.print("[yellow]No config file found. Run 'holo init' to create one.[/yellow]")
        return

    # Load and display config
    cfg = load_config()

    # Create tables for each section
    console.print(Panel.fit(
        f"[bold cyan]Configuration[/bold cyan]\n"
        f"Location: {config_path}",
        border_style="cyan"
    ))

    # Privacy section
    privacy_table = Table(title="Privacy Settings", show_header=True)
    privacy_table.add_column("Setting", style="cyan")
    privacy_table.add_column("Value", style="green")

    privacy_table.add_row("Tier", cfg.privacy.tier)
    privacy_table.add_row("Blacklist Domains", str(len(cfg.privacy.blacklist_domains)))
    privacy_table.add_row("Blacklist Keywords", str(len(cfg.privacy.blacklist_keywords)))
    privacy_table.add_row("Whitelist Domains", str(len(cfg.privacy.whitelist_domains)))

    console.print(privacy_table)
    console.print()

    # LLM section
    llm_table = Table(title="LLM Configuration", show_header=True)
    llm_table.add_column("Setting", style="cyan")
    llm_table.add_column("Value", style="green")

    llm_table.add_row("Provider", cfg.llm.provider)
    llm_table.add_row("API Key", "✓ Set" if cfg.llm.api_key else "✗ Not Set")
    llm_table.add_row("Base URL", cfg.llm.base_url)
    llm_table.add_row("Daily Budget", str(cfg.llm.daily_budget))
    llm_table.add_row("Primary Model", cfg.llm.primary)
    llm_table.add_row("Coding Model", cfg.llm.coding)

    console.print(llm_table)
    console.print()

    # Classification section
    class_table = Table(title="Classification System", show_header=True)
    class_table.add_column("Setting", style="cyan")
    class_table.add_column("Value", style="green")

    class_table.add_row("System", cfg.classification.system)
    class_table.add_row("Generate Cutter Numbers", "✓" if cfg.classification.generate_cutter_numbers else "✗")
    class_table.add_row("Generate Full Call Numbers", "✓" if cfg.classification.generate_full_call_numbers else "✗")
    class_table.add_row("Cutter Length", str(cfg.classification.cutter_length))

    console.print(class_table)
    console.print()

    # Integrations section
    int_table = Table(title="Integrations", show_header=True)
    int_table.add_column("Integration", style="cyan")
    int_table.add_column("Status", style="green")

    int_table.add_row("Journel", "✓ Enabled" if cfg.integrations.journel_enabled else "✗ Disabled")
    int_table.add_row("Calibre", "✓ Enabled" if cfg.integrations.calibre_enabled else "✗ Disabled")
    int_table.add_row("Internet Archive", "✓ Enabled" if cfg.integrations.internet_archive_enabled else "✗ Disabled")
    int_table.add_row("Browser Tracking", "✓ Enabled" if cfg.integrations.browser_enabled else "✗ Disabled")
    int_table.add_row("Window Focus", "✓ Enabled" if cfg.integrations.window_focus_enabled else "✗ Disabled")

    console.print(int_table)


@config.command()
@click.argument("key")
def get(key: str):
    """Get a specific configuration value.

    Examples:
        holo config get llm.primary
        holo config get privacy.tier
        holo config get integrations.calibre_enabled
    """
    cfg = load_config()

    # Parse nested key (e.g., "llm.primary")
    parts = key.split(".")

    try:
        value = cfg
        for part in parts:
            if hasattr(value, part):
                value = getattr(value, part)
            else:
                console.print(f"[red]Error: Key '{key}' not found[/red]")
                return

        # Format output
        if isinstance(value, (list, dict)):
            console.print(f"[cyan]{key}:[/cyan]")
            for item in value if isinstance(value, list) else value.items():
                console.print(f"  - {item}")
        else:
            console.print(f"[cyan]{key}:[/cyan] [green]{value}[/green]")

    except Exception as e:
        console.print(f"[red]Error getting config value: {e}[/red]")


@config.command()
@click.argument("key")
@click.argument("value")
def set(key: str, value: str):
    """Set a configuration value.

    Examples:
        holo config set llm.primary deepseek-ai/DeepSeek-V3.1
        holo config set privacy.tier local_only
        holo config set integrations.calibre_enabled true
    """
    cfg = load_config()

    # Parse nested key
    parts = key.split(".")

    try:
        # Navigate to the parent object
        obj = cfg
        for part in parts[:-1]:
            if hasattr(obj, part):
                obj = getattr(obj, part)
            else:
                console.print(f"[red]Error: Key path '{key}' not found[/red]")
                return

        # Set the value
        last_key = parts[-1]
        if not hasattr(obj, last_key):
            console.print(f"[red]Error: Key '{key}' not found[/red]")
            return

        # Convert value to appropriate type
        current = getattr(obj, last_key)

        if isinstance(current, bool):
            # Convert string to boolean
            new_value = value.lower() in ("true", "yes", "1", "on")
        elif isinstance(current, int):
            new_value = int(value)
        elif isinstance(current, float):
            new_value = float(value)
        elif isinstance(current, Path):
            new_value = Path(value).expanduser()
        else:
            new_value = value

        setattr(obj, last_key, new_value)

        # Save config
        save_config(cfg)

        console.print(f"[green]✓[/green] Set [cyan]{key}[/cyan] = [green]{new_value}[/green]")

    except ValueError as e:
        console.print(f"[red]Error: Invalid value type: {e}[/red]")
    except Exception as e:
        console.print(f"[red]Error setting config value: {e}[/red]")


@config.command()
def path():
    """Show path to configuration file."""
    config_path = get_config_path()
    console.print(f"[cyan]Config file:[/cyan] {config_path}")

    if config_path.exists():
        console.print(f"[green]✓ File exists[/green]")
    else:
        console.print(f"[yellow]✗ File not found - run 'holo init' to create[/yellow]")


@config.command()
def edit():
    """Open configuration file in default editor."""
    config_path = get_config_path()

    if not config_path.exists():
        console.print("[yellow]No config file found. Creating default...[/yellow]")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            f.write(DEFAULT_CONFIG)
        console.print(f"[green]✓ Created {config_path}[/green]")

    # Try to open in editor
    editor = os.getenv("EDITOR", os.getenv("VISUAL", "nano"))

    try:
        # On Windows, try common editors
        if os.name == "nt":
            # Try notepad, then VSCode, then notepad++
            editors_to_try = ["notepad", "code", "notepad++", "vim", "nano"]
            for ed in editors_to_try:
                try:
                    subprocess.run([ed, str(config_path)])
                    return
                except FileNotFoundError:
                    continue

            # If none work, just show the path
            console.print(f"[yellow]Could not open editor automatically.[/yellow]")
            console.print(f"[cyan]Please edit manually:[/cyan] {config_path}")
        else:
            subprocess.run([editor, str(config_path)])

    except Exception as e:
        console.print(f"[red]Error opening editor: {e}[/red]")
        console.print(f"[cyan]Config location:[/cyan] {config_path}")


@config.command()
@click.confirmation_option(prompt="Are you sure you want to reset to default configuration?")
def reset():
    """Reset configuration to defaults."""
    config_path = get_config_path()

    # Write default config
    with open(config_path, "w") as f:
        f.write(DEFAULT_CONFIG)

    console.print(f"[green]✓ Reset configuration to defaults[/green]")
    console.print(f"[yellow]Note:[/yellow] You'll need to set your NANOGPT_API_KEY again")


@config.command()
def validate():
    """Validate configuration file."""
    config_path = get_config_path()

    if not config_path.exists():
        console.print("[red]✗ No config file found[/red]")
        return

    try:
        cfg = load_config()
        console.print("[green]✓ Configuration is valid[/green]")

        # Check for common issues
        issues = []

        if not cfg.llm.api_key:
            issues.append("LLM API key not set (set NANOGPT_API_KEY environment variable)")

        if not cfg.data_dir.exists():
            issues.append(f"Data directory does not exist: {cfg.data_dir}")

        if cfg.integrations.calibre_enabled and not cfg.integrations.calibre_library_path:
            issues.append("Calibre enabled but library path not set")

        if cfg.integrations.journel_enabled and not cfg.integrations.journel_path:
            issues.append("Journel enabled but path not set")

        if issues:
            console.print("\n[yellow]Warnings:[/yellow]")
            for issue in issues:
                console.print(f"  ⚠ {issue}")

    except Exception as e:
        console.print(f"[red]✗ Configuration is invalid:[/red]")
        console.print(f"  {e}")


@config.command()
def locations():
    """Show all Holocene data locations."""
    cfg = load_config()

    table = Table(title="Holocene Data Locations", show_header=True)
    table.add_column("Location", style="cyan")
    table.add_column("Path", style="green")
    table.add_column("Status", style="yellow")

    # Config file
    config_path = get_config_path()
    table.add_row(
        "Config File",
        str(config_path),
        "✓" if config_path.exists() else "✗"
    )

    # Data directory
    table.add_row(
        "Data Directory",
        str(cfg.data_dir),
        "✓" if cfg.data_dir.exists() else "✗"
    )

    # Database
    table.add_row(
        "Database",
        str(cfg.db_path),
        "✓" if cfg.db_path and cfg.db_path.exists() else "✗"
    )

    # Cache directory
    cache_dir = cfg.data_dir / "cache"
    table.add_row(
        "Cache",
        str(cache_dir),
        "✓" if cache_dir.exists() else "✗"
    )

    # Embeddings directory
    embeddings_dir = cfg.data_dir / "embeddings"
    table.add_row(
        "Embeddings",
        str(embeddings_dir),
        "✓" if embeddings_dir.exists() else "✗"
    )

    # Books directory
    books_dir = cfg.data_dir / "books"
    table.add_row(
        "Books",
        str(books_dir),
        "✓" if books_dir.exists() else "✗"
    )

    # Research directory
    research_dir = cfg.data_dir / "research"
    table.add_row(
        "Research",
        str(research_dir),
        "✓" if research_dir.exists() else "✗"
    )

    # Calibre library (if configured)
    if cfg.integrations.calibre_library_path:
        table.add_row(
            "Calibre Library",
            str(cfg.integrations.calibre_library_path),
            "✓" if cfg.integrations.calibre_library_path.exists() else "✗"
        )

    console.print(table)


@config.command()
@click.option('--test', is_flag=True, help='Test existing keys without prompting')
def setup(test: bool):
    """Interactive setup wizard for API keys and credentials.

    Checks which API keys are missing or not working, and prompts
    for configuration. Use --test to just test existing keys.
    """
    cfg = load_config()
    console.print(Panel.fit(
        "[bold cyan]Holocene Configuration Setup[/bold cyan]\n"
        "Let's configure your API keys and credentials",
        border_style="cyan"
    ))
    console.print()

    changes_made = False

    # Check NanoGPT API Key
    console.print("[bold]1. NanoGPT API Key[/bold]")
    console.print("   Used for: LLM model routing (DeepSeek, Qwen, etc.)")

    if cfg.llm.api_key:
        console.print(f"   [green]✓ Currently set[/green]")
        if not test:
            if click.confirm("   Update NanoGPT API key?", default=False):
                new_key = click.prompt("   Enter NanoGPT API key", hide_input=True)
                cfg.llm.api_key = new_key
                changes_made = True
                console.print("   [green]✓ Updated[/green]")
    else:
        console.print(f"   [yellow]✗ Not set[/yellow]")
        if not test:
            if click.confirm("   Configure NanoGPT API key now?", default=True):
                new_key = click.prompt("   Enter NanoGPT API key", hide_input=True)
                cfg.llm.api_key = new_key
                changes_made = True
                console.print("   [green]✓ Set[/green]")
            else:
                console.print("   [yellow]Skipped - set NANOGPT_API_KEY environment variable[/yellow]")
    console.print()

    # GitHub Token
    console.print("[bold]2. GitHub Token (optional)[/bold]")
    console.print("   Used for: Git repository scanning and activity tracking")

    if cfg.integrations.github_token:
        console.print(f"   [green]✓ Currently set[/green]")
        if not test:
            if click.confirm("   Update GitHub token?", default=False):
                new_token = click.prompt("   Enter GitHub token", hide_input=True)
                cfg.integrations.github_token = new_token
                cfg.integrations.github_enabled = True
                changes_made = True
                console.print("   [green]✓ Updated[/green]")
    else:
        console.print(f"   [dim]✗ Not set[/dim]")
        if not test and click.confirm("   Configure GitHub token?", default=False):
            new_token = click.prompt("   Enter GitHub token", hide_input=True)
            cfg.integrations.github_token = new_token
            cfg.integrations.github_enabled = True
            changes_made = True
            console.print("   [green]✓ Set[/green]")
    console.print()

    # Internet Archive
    console.print("[bold]3. Internet Archive Keys (optional)[/bold]")
    console.print("   Used for: Uploading to Internet Archive, accessing restricted items")

    if cfg.integrations.ia_access_key and cfg.integrations.ia_secret_key:
        console.print(f"   [green]✓ Currently set[/green]")
        if not test and click.confirm("   Update IA keys?", default=False):
            access_key = click.prompt("   Enter IA access key", hide_input=True)
            secret_key = click.prompt("   Enter IA secret key", hide_input=True)
            cfg.integrations.ia_access_key = access_key
            cfg.integrations.ia_secret_key = secret_key
            cfg.integrations.internet_archive_enabled = True
            changes_made = True
            console.print("   [green]✓ Updated[/green]")
    else:
        console.print(f"   [dim]✗ Not set[/dim]")
        if not test and click.confirm("   Configure Internet Archive keys?", default=False):
            console.print("   [dim]Get keys from: https://archive.org/account/s3.php[/dim]")
            access_key = click.prompt("   Enter IA access key", hide_input=True)
            secret_key = click.prompt("   Enter IA secret key", hide_input=True)
            cfg.integrations.ia_access_key = access_key
            cfg.integrations.ia_secret_key = secret_key
            cfg.integrations.internet_archive_enabled = True
            changes_made = True
            console.print("   [green]✓ Set[/green]")
    console.print()

    # Apify
    console.print("[bold]4. Apify API Key (optional)[/bold]")
    console.print("   Used for: Web scraping (MercadoLivre, etc.)")

    if cfg.integrations.apify_api_key:
        console.print(f"   [green]✓ Currently set[/green]")
        if not test and click.confirm("   Update Apify API key?", default=False):
            new_key = click.prompt("   Enter Apify API key", hide_input=True)
            cfg.integrations.apify_api_key = new_key
            cfg.integrations.apify_enabled = True
            changes_made = True
            console.print("   [green]✓ Updated[/green]")
    else:
        console.print(f"   [dim]✗ Not set[/dim]")
        if not test and click.confirm("   Configure Apify API key?", default=False):
            console.print("   [dim]Get key from: https://console.apify.com/account/integrations[/dim]")
            new_key = click.prompt("   Enter Apify API key", hide_input=True)
            cfg.integrations.apify_api_key = new_key
            cfg.integrations.apify_enabled = True
            changes_made = True
            console.print("   [green]✓ Set[/green]")
    console.print()

    # Telegram Bot
    console.print("[bold]5. Telegram Bot (optional)[/bold]")
    console.print("   Used for: Mobile notifications and commands")

    if cfg.telegram.bot_token:
        console.print(f"   [green]✓ Currently set[/green]")
        if not test and click.confirm("   Update Telegram bot token?", default=False):
            bot_token = click.prompt("   Enter bot token", hide_input=True)
            cfg.telegram.bot_token = bot_token
            cfg.telegram.enabled = True
            changes_made = True
            console.print("   [green]✓ Updated[/green]")

            # Optionally set chat ID
            if click.confirm("   Set chat ID now? (or skip - bot will auto-detect on /start)", default=False):
                chat_id = click.prompt("   Enter chat ID", type=int)
                cfg.telegram.chat_id = chat_id
    else:
        console.print(f"   [dim]✗ Not set[/dim]")
        if not test and click.confirm("   Configure Telegram bot?", default=False):
            console.print("   [dim]Get token from @BotFather on Telegram[/dim]")
            bot_token = click.prompt("   Enter bot token", hide_input=True)
            cfg.telegram.bot_token = bot_token
            cfg.telegram.enabled = True
            changes_made = True
            console.print("   [green]✓ Set[/green]")

            # Optionally set chat ID
            if click.confirm("   Set chat ID now? (or skip - bot will auto-detect on /start)", default=False):
                console.print("   [dim]Get your chat ID from @userinfobot on Telegram[/dim]")
                chat_id = click.prompt("   Enter chat ID", type=int)
                cfg.telegram.chat_id = chat_id
    console.print()

    # MercadoLivre
    console.print("[bold]6. MercadoLivre OAuth (optional)[/bold]")
    console.print("   Used for: Syncing MercadoLivre favorites")

    if cfg.mercadolivre.client_id and cfg.mercadolivre.client_secret:
        console.print(f"   [green]✓ Currently set[/green]")
        if not test and click.confirm("   Update MercadoLivre credentials?", default=False):
            client_id = click.prompt("   Enter client ID")
            client_secret = click.prompt("   Enter client secret", hide_input=True)
            cfg.mercadolivre.client_id = client_id
            cfg.mercadolivre.client_secret = client_secret
            cfg.mercadolivre.enabled = True
            changes_made = True
            console.print("   [green]✓ Updated[/green]")
    else:
        console.print(f"   [dim]✗ Not set[/dim]")
        if not test and click.confirm("   Configure MercadoLivre OAuth?", default=False):
            console.print("   [dim]Create app at: https://developers.mercadolivre.com.br/[/dim]")
            client_id = click.prompt("   Enter client ID")
            client_secret = click.prompt("   Enter client secret", hide_input=True)
            cfg.mercadolivre.client_id = client_id
            cfg.mercadolivre.client_secret = client_secret
            cfg.mercadolivre.enabled = True
            changes_made = True
            console.print("   [green]✓ Set[/green]")
    console.print()

    # Save if changes were made
    if changes_made:
        save_config(cfg)
        console.print(Panel.fit(
            "[bold green]✓ Configuration saved[/bold green]\n"
            f"Location: {get_config_path()}",
            border_style="green"
        ))
    elif test:
        console.print(Panel.fit(
            "[bold cyan]Configuration Check Complete[/bold cyan]\n"
            "Run without --test to update keys",
            border_style="cyan"
        ))
    else:
        console.print(Panel.fit(
            "[bold yellow]No changes made[/bold yellow]",
            border_style="yellow"
        ))
