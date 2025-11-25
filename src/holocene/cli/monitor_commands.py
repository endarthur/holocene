"""Monitor commands for Uptime Kuma integration."""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ..config import load_config, save_config, get_config_path

console = Console()


@click.group()
def monitor():
    """Manage Uptime Kuma monitoring for holocene services."""
    pass


@monitor.command()
@click.option("--create", is_flag=True, help="Auto-create all monitors in Uptime Kuma")
def setup(create: bool):
    """Show recommended monitors and optionally create them."""
    config = load_config()

    if not config.integrations.uptime_kuma_enabled:
        console.print("[red]Error:[/red] Uptime Kuma integration not enabled")
        console.print("Add to your config.yml:")
        console.print("  [cyan]uptime_kuma_enabled: true[/cyan]")
        console.print("  [cyan]uptime_kuma_url: \"http://192.168.1.103:3001\"[/cyan]")
        return

    from ..integrations.uptime_kuma import (
        setup_holocene_monitoring,
        create_holocene_monitors,
        UPTIME_KUMA_API_AVAILABLE
    )

    if create:
        # Auto-create monitors
        console.print()
        console.print("[bold cyan]Creating Uptime Kuma monitors...[/bold cyan]")
        console.print()

        def update_push_token(token):
            """Callback to save push token to config."""
            # Load fresh config, update, and save
            import yaml
            config_path = get_config_path()
            with open(config_path, 'r') as f:
                config_data = yaml.safe_load(f)

            if 'integrations' not in config_data:
                config_data['integrations'] = {}
            config_data['integrations']['uptime_kuma_push_token'] = token

            with open(config_path, 'w') as f:
                yaml.dump(config_data, f, default_flow_style=False, sort_keys=False)

            console.print(f"[green]✓[/green] Push token saved to config: [dim]{token[:20]}...[/dim]")

        result = create_holocene_monitors(config, update_config_callback=update_push_token)

        if not result["success"]:
            console.print(f"[red]Error:[/red] {result['error']}")
            return

        # Show results
        if result["created"]:
            console.print("[green]Created monitors:[/green]")
            for name in result["created"]:
                console.print(f"  [green]✓[/green] {name}")

        if result["skipped"]:
            console.print("[yellow]Already exist (skipped):[/yellow]")
            for name in result["skipped"]:
                console.print(f"  [dim]○[/dim] {name}")

        if result["errors"]:
            console.print("[red]Errors:[/red]")
            for err in result["errors"]:
                console.print(f"  [red]✗[/red] {err}")

        if result["push_token"]:
            console.print()
            console.print("[green]✓ Push monitor configured![/green]")
            console.print()
            console.print("[bold]Next steps:[/bold]")
            console.print("1. Restart holod: [cyan]sudo systemctl restart holod[/cyan]")
            console.print("2. The daemon will ping Uptime Kuma every 60 seconds")
        else:
            console.print()
            console.print("[yellow]Warning:[/yellow] Could not retrieve push token")
            console.print("You may need to manually copy it from Uptime Kuma")

        return

    # Show setup info without creating
    result = setup_holocene_monitoring(config)

    if not result["success"]:
        console.print(f"[red]Error:[/red] {result['error']}")
        return

    # Show header
    console.print()
    console.print(Panel.fit(
        "[bold cyan]Holocene Monitoring Setup[/bold cyan]",
        border_style="cyan"
    ))
    console.print()

    # Show recommended monitors
    table = Table(title="Recommended Monitors", show_header=True)
    table.add_column("Service", style="cyan")
    table.add_column("Type", style="yellow")
    table.add_column("Target", style="green")
    table.add_column("Interval", style="dim")

    for m in result["recommended_monitors"]:
        table.add_row(
            m["name"],
            m["type"],
            m["target"],
            f"{m['interval']}s"
        )

    console.print(table)
    console.print()

    # Show auto-create status
    if result["can_auto_create"]:
        console.print("[green]✓ Auto-creation available[/green]")
        console.print()
        console.print("Run [cyan]holo monitor setup --create[/cyan] to create all monitors automatically")
    else:
        console.print("[yellow]Manual setup required[/yellow]")
        console.print()
        for instruction in result.get("instructions", []):
            console.print(f"  {instruction}")

    console.print()
    console.print(f"Uptime Kuma URL: [link={result['uptime_kuma_url']}]{result['uptime_kuma_url']}[/link]")


@monitor.command()
def status():
    """Check current monitoring status."""
    config = load_config()

    if not config.integrations.uptime_kuma_enabled:
        console.print("[red]Uptime Kuma integration not enabled[/red]")
        return

    from ..integrations.uptime_kuma import UPTIME_KUMA_API_AVAILABLE

    console.print()
    console.print("[bold]Uptime Kuma Status[/bold]")
    console.print()

    # Show config
    console.print(f"URL: [cyan]{config.integrations.uptime_kuma_url}[/cyan]")

    api_key = getattr(config.integrations, 'uptime_kuma_api_key', None)
    if api_key:
        console.print(f"API Key: [dim]{api_key[:15]}...[/dim]")
    else:
        console.print(f"API Key: [dim]Not configured[/dim]")

    username = getattr(config.integrations, 'uptime_kuma_username', None)
    if username:
        console.print(f"Username: [green]✓ Configured[/green] ({username})")
    else:
        console.print(f"Username: [yellow]Not configured[/yellow] (needed for --create)")

    push_token = getattr(config.integrations, 'uptime_kuma_push_token', None)
    if push_token:
        console.print(f"Push Token: [green]✓ Configured[/green] ({push_token[:15]}...)")
    else:
        console.print(f"Push Token: [yellow]Not configured[/yellow]")
        console.print("  [dim]Run 'holo monitor setup --create' to auto-configure[/dim]")

    console.print()
    console.print(f"uptime-kuma-api: {'[green]✓ Installed[/green]' if UPTIME_KUMA_API_AVAILABLE else '[yellow]Not installed[/yellow]'}")

    console.print()

    # Test connectivity
    try:
        import requests
        response = requests.get(
            f"{config.integrations.uptime_kuma_url}/api/status-page/holocene",
            headers={"X-API-KEY": api_key} if api_key else {},
            timeout=5
        )

        if response.status_code == 200:
            console.print("[green]✓ Connected to Uptime Kuma[/green]")
        elif response.status_code == 404:
            console.print("[green]✓ API responding[/green] (no 'holocene' status page)")
        else:
            console.print(f"[yellow]API returned status {response.status_code}[/yellow]")

    except Exception as e:
        console.print(f"[red]✗ Cannot connect to Uptime Kuma[/red]")
        console.print(f"  [dim]{e}[/dim]")


@monitor.command()
@click.option("--status", "ping_status", default="up", help="Status to report (up/down)")
@click.option("--msg", default="", help="Optional message")
def ping(ping_status: str, msg: str):
    """Manually ping the push monitor (for testing)."""
    config = load_config()

    if not config.integrations.uptime_kuma_enabled:
        console.print("[red]Uptime Kuma integration not enabled[/red]")
        return

    push_token = getattr(config.integrations, 'uptime_kuma_push_token', None)
    if not push_token:
        console.print("[red]Push token not configured[/red]")
        console.print("Run [cyan]holo monitor setup --create[/cyan] to auto-configure")
        return

    from ..integrations.uptime_kuma import UptimeKumaClient

    client = UptimeKumaClient(
        config.integrations.uptime_kuma_url,
        api_key=config.integrations.uptime_kuma_api_key
    )

    console.print(f"Pinging push monitor with status=[cyan]{ping_status}[/cyan]...")

    if client.ping_push_monitor(push_token, status=ping_status, msg=msg):
        console.print("[green]✓ Ping successful[/green]")
    else:
        console.print("[red]✗ Ping failed[/red]")


@monitor.command("list")
def list_monitors():
    """List all monitors from Uptime Kuma."""
    config = load_config()

    if not config.integrations.uptime_kuma_enabled:
        console.print("[red]Uptime Kuma integration not enabled[/red]")
        return

    from ..integrations.uptime_kuma import UptimeKumaClient, UPTIME_KUMA_API_AVAILABLE

    if not UPTIME_KUMA_API_AVAILABLE:
        console.print("[red]uptime-kuma-api not installed[/red]")
        console.print("Install with: [cyan]pip install holocene[monitoring][/cyan]")
        return

    username = getattr(config.integrations, 'uptime_kuma_username', None)
    password = getattr(config.integrations, 'uptime_kuma_password', None)

    if not username or not password:
        console.print("[red]Username and password required[/red]")
        console.print("Add to config.yml:")
        console.print("  [cyan]uptime_kuma_username: your_username[/cyan]")
        console.print("  [cyan]uptime_kuma_password: your_password[/cyan]")
        return

    client = UptimeKumaClient(
        config.integrations.uptime_kuma_url,
        api_key=config.integrations.uptime_kuma_api_key,
        username=username,
        password=password
    )

    try:
        console.print()
        console.print("[bold]Uptime Kuma Monitors[/bold]")
        console.print()

        monitors = client.get_monitors()

        if not monitors:
            console.print("[dim]No monitors configured[/dim]")
            console.print("Run [cyan]holo monitor setup --create[/cyan] to create monitors")
            return

        table = Table(show_header=True)
        table.add_column("ID", style="dim")
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="yellow")
        table.add_column("Status", style="green")
        table.add_column("Target")

        for m in monitors:
            status_str = "[green]Up[/green]" if m.get("active") else "[red]Down[/red]"
            target = m.get("url") or f"{m.get('hostname', '')}:{m.get('port', '')}" or "-"
            table.add_row(
                str(m.get("id", "")),
                m.get("name", ""),
                m.get("type", ""),
                status_str,
                target[:40]
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
    finally:
        client.disconnect()
