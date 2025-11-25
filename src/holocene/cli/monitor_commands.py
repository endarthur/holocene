"""Monitor commands for Uptime Kuma integration."""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ..config import load_config

console = Console()


@click.group()
def monitor():
    """Manage Uptime Kuma monitoring for holocene services."""
    pass


@monitor.command()
def setup():
    """Show recommended monitors and setup instructions."""
    config = load_config()

    if not config.integrations.uptime_kuma_enabled:
        console.print("[red]Error:[/red] Uptime Kuma integration not enabled")
        console.print("Add to your config.yml:")
        console.print("  [cyan]uptime_kuma_enabled: true[/cyan]")
        console.print("  [cyan]uptime_kuma_url: \"http://192.168.1.103:3001\"[/cyan]")
        console.print("  [cyan]uptime_kuma_api_key: \"uk_xxxxx\"[/cyan]")
        return

    from ..integrations.uptime_kuma import setup_holocene_monitoring, HoloceneMonitorConfig

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

    # Add push monitor recommendation
    table.add_row(
        "[bold]holod Push[/bold]",
        "[bold]push[/bold]",
        "[dim](daemon pings Uptime Kuma)[/dim]",
        "60s"
    )

    console.print(table)
    console.print()

    # Show instructions
    console.print("[bold]Setup Instructions:[/bold]")
    console.print()
    console.print(f"1. Open [link={result['uptime_kuma_url']}]{result['uptime_kuma_url']}[/link]")
    console.print()
    console.print("2. For each service above, click [cyan]Add New Monitor[/cyan]:")
    console.print("   • HTTP monitors: Enter the URL directly")
    console.print("   • TCP monitors: Enter hostname and port")
    console.print()
    console.print("3. [bold]For holod Push monitor:[/bold]")
    console.print("   • Select type: [yellow]Push[/yellow]")
    console.print("   • Name: [cyan]holod Daemon[/cyan]")
    console.print("   • Copy the Push URL (looks like: [dim]http://.../api/push/abc123[/dim])")
    console.print("   • Extract the token (the [cyan]abc123[/cyan] part)")
    console.print("   • Add to your config.yml:")
    console.print("     [cyan]uptime_kuma_push_token: \"abc123\"[/cyan]")
    console.print()
    console.print("4. Restart holod: [cyan]holo daemon restart[/cyan]")
    console.print()
    console.print("[dim]The daemon will ping Uptime Kuma every 60 seconds alongside healthchecks.io[/dim]")


@monitor.command()
def status():
    """Check current monitoring status."""
    config = load_config()

    if not config.integrations.uptime_kuma_enabled:
        console.print("[red]Uptime Kuma integration not enabled[/red]")
        return

    from ..integrations.uptime_kuma import UptimeKumaClient

    console.print()
    console.print("[bold]Uptime Kuma Status[/bold]")
    console.print()

    # Show config
    console.print(f"URL: [cyan]{config.integrations.uptime_kuma_url}[/cyan]")
    console.print(f"API Key: [dim]{config.integrations.uptime_kuma_api_key[:15]}...[/dim]")

    push_token = getattr(config.integrations, 'uptime_kuma_push_token', None)
    if push_token:
        console.print(f"Push Token: [green]✓ Configured[/green] ({push_token[:10]}...)")
    else:
        console.print(f"Push Token: [yellow]Not configured[/yellow]")
        console.print("  [dim]Run 'holo monitor setup' for instructions[/dim]")

    console.print()

    # Test connectivity
    try:
        client = UptimeKumaClient(
            config.integrations.uptime_kuma_url,
            config.integrations.uptime_kuma_api_key
        )

        # Try a simple API call
        import requests
        response = requests.get(
            f"{config.integrations.uptime_kuma_url}/api/status-page/holocene",
            headers={"X-API-KEY": config.integrations.uptime_kuma_api_key},
            timeout=5
        )

        if response.status_code == 200:
            console.print("[green]✓ Connected to Uptime Kuma[/green]")
        elif response.status_code == 404:
            console.print("[green]✓ API responding[/green] (no 'holocene' status page yet)")
        else:
            console.print(f"[yellow]API returned status {response.status_code}[/yellow]")

    except requests.exceptions.ConnectionError:
        console.print("[red]✗ Cannot connect to Uptime Kuma[/red]")
        console.print(f"  [dim]Check if Uptime Kuma is running at {config.integrations.uptime_kuma_url}[/dim]")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")


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
        console.print("Run [cyan]holo monitor setup[/cyan] for instructions")
        return

    from ..integrations.uptime_kuma import UptimeKumaClient

    client = UptimeKumaClient(
        config.integrations.uptime_kuma_url,
        config.integrations.uptime_kuma_api_key
    )

    console.print(f"Pinging push monitor with status=[cyan]{ping_status}[/cyan]...")

    if client.ping_push_monitor(push_token, status=ping_status, msg=msg):
        console.print("[green]✓ Ping successful[/green]")
    else:
        console.print("[red]✗ Ping failed[/red]")


@monitor.command()
def list():
    """List configured monitors (requires status page)."""
    config = load_config()

    if not config.integrations.uptime_kuma_enabled:
        console.print("[red]Uptime Kuma integration not enabled[/red]")
        return

    console.print()
    console.print("[yellow]Note:[/yellow] Monitor listing requires a status page named 'holocene'")
    console.print("Create one in Uptime Kuma and add your monitors to it.")
    console.print()
    console.print(f"Open: [link={config.integrations.uptime_kuma_url}]{config.integrations.uptime_kuma_url}[/link]")
