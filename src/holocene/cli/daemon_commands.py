"""Daemon control commands for holod."""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from ..daemon import HoloceneDaemon
from ..config import load_config

console = Console()


@click.group()
def daemon():
    """Manage holod daemon (background service)."""
    pass


@daemon.command()
@click.option("--foreground", "-f", is_flag=True, help="Run in foreground (don't daemonize)")
@click.option("--device", "-d", default="rei", help="Device identifier (default: rei)")
def start(foreground: bool, device: str):
    """Start the holod daemon.

    The daemon runs plugins 24/7 and provides REST API on port 5555.

    Examples:
        holo daemon start                    # Start in background
        holo daemon start --foreground       # Run in foreground (Ctrl+C to stop)
        holo daemon start --device wmut      # Run on wmut device
    """
    try:
        config = load_config()
        daemon = HoloceneDaemon(device=device)

        success = daemon.start(foreground=foreground)

        if not success:
            console.print("[red]✗[/red] Failed to start daemon")
            return

    except Exception as e:
        console.print(f"[red]✗[/red] Error starting daemon: {e}")
        raise


@daemon.command()
def stop():
    """Stop the holod daemon.

    Gracefully shuts down the daemon and all running plugins.

    Examples:
        holo daemon stop
    """
    try:
        daemon = HoloceneDaemon()

        if not daemon.is_running():
            console.print("[yellow]holod is not running[/yellow]")
            return

        # Read PID and stop
        pid = int(daemon.pid_file.read_text().strip())

        console.print(f"Stopping holod (PID: {pid})...")

        # Send SIGTERM to daemon
        import signal
        import sys

        if sys.platform == 'win32':
            # Windows: Use taskkill
            import subprocess
            subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], check=False)
        else:
            # Unix: Send SIGTERM
            import os
            os.kill(pid, signal.SIGTERM)

        console.print("[green]✓[/green] holod stopped")

    except Exception as e:
        console.print(f"[red]✗[/red] Error stopping daemon: {e}")
        raise


@daemon.command()
def status():
    """Show holod daemon status.

    Displays daemon status, uptime, and plugin information.

    Examples:
        holo daemon status
    """
    try:
        daemon = HoloceneDaemon()
        status_info = daemon.status()

        if not status_info['running']:
            console.print(Panel.fit(
                "[yellow]holod is not running[/yellow]\n\n"
                "Start with: [cyan]holo daemon start[/cyan]",
                title="Holod Status"
            ))
            return

        # Create status panel
        status_text = f"""[green]✓ Running[/green]

[bold]Process:[/bold]
  PID: {status_info['pid']}
  Device: {status_info['device']}

[bold]Plugins:[/bold]
  Loaded: {status_info['plugins']}

[bold]API:[/bold]
  {status_info['api'] or 'Not available'}
"""

        console.print(Panel.fit(status_text, title="Holod Status"))

    except Exception as e:
        console.print(f"[red]✗[/red] Error getting status: {e}")
        raise


@daemon.command()
def restart():
    """Restart the holod daemon.

    Stops and starts the daemon.

    Examples:
        holo daemon restart
    """
    try:
        daemon = HoloceneDaemon()

        # Check if running
        if daemon.is_running():
            console.print("Stopping holod...")

            # Read PID and stop
            pid = int(daemon.pid_file.read_text().strip())

            import signal
            import sys

            if sys.platform == 'win32':
                import subprocess
                subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], check=False)
            else:
                import os
                os.kill(pid, signal.SIGTERM)

            # Wait for shutdown
            import time
            time.sleep(2)

        console.print("Starting holod...")
        success = daemon.start(foreground=False)

        if success:
            console.print("[green]✓[/green] holod restarted")
        else:
            console.print("[red]✗[/red] Failed to restart daemon")

    except Exception as e:
        console.print(f"[red]✗[/red] Error restarting daemon: {e}")
        raise


@daemon.command()
@click.option("--limit", "-l", default=10, help="Number of logs to show (default: 10)")
def logs(limit: int):
    """Show holod daemon logs.

    Displays recent log entries from the daemon.

    Examples:
        holo daemon logs              # Show last 10 logs
        holo daemon logs --limit 50   # Show last 50 logs
    """
    try:
        config = load_config()
        log_file = config.data_dir / "holod.log"

        if not log_file.exists():
            console.print("[yellow]No log file found[/yellow]")
            return

        # Read last N lines
        with open(log_file, 'r') as f:
            lines = f.readlines()

        recent_lines = lines[-limit:] if len(lines) > limit else lines

        console.print(f"[bold]Last {len(recent_lines)} log entries:[/bold]\n")

        for line in recent_lines:
            console.print(line.rstrip())

    except Exception as e:
        console.print(f"[red]✗[/red] Error reading logs: {e}")
        raise


@daemon.command()
def plugins():
    """List plugins running in holod daemon.

    Shows all discovered plugins and their status.

    Examples:
        holo daemon plugins
    """
    try:
        daemon = HoloceneDaemon()

        if not daemon.is_running():
            console.print("[yellow]holod is not running[/yellow]")
            console.print("Start with: [cyan]holo daemon start[/cyan]")
            return

        # Query API for plugin list
        import requests

        response = requests.get("http://localhost:5555/plugins")
        data = response.json()

        plugins_list = data.get('plugins', [])

        if not plugins_list:
            console.print("[yellow]No plugins loaded[/yellow]")
            return

        # Create table
        table = Table(title="Holod Plugins")
        table.add_column("Name", style="cyan")
        table.add_column("Version", style="magenta")
        table.add_column("Status", style="green")
        table.add_column("Runs On", style="yellow")
        table.add_column("Description")

        for plugin in plugins_list:
            status = "✓ Enabled" if plugin.get('enabled', False) else "○ Disabled"
            runs_on = ", ".join(plugin.get('runs_on', []))

            table.add_row(
                plugin['name'],
                plugin.get('version', '?'),
                status,
                runs_on,
                plugin.get('description', '')
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]✗[/red] Error listing plugins: {e}")
        raise


@daemon.command()
@click.argument("plugin_name")
def enable(plugin_name: str):
    """Enable a plugin in holod daemon.

    Args:
        plugin_name: Name of plugin to enable

    Examples:
        holo daemon enable book_enricher
        holo daemon enable link_status_checker
    """
    try:
        daemon = HoloceneDaemon()

        if not daemon.is_running():
            console.print("[yellow]holod is not running[/yellow]")
            return

        # Query API to enable plugin
        import requests

        response = requests.post(f"http://localhost:5555/plugins/{plugin_name}/enable")
        data = response.json()

        if response.status_code == 200:
            console.print(f"[green]✓[/green] Enabled plugin: {plugin_name}")
        else:
            console.print(f"[red]✗[/red] Failed to enable plugin: {data.get('error', 'Unknown error')}")

    except Exception as e:
        console.print(f"[red]✗[/red] Error enabling plugin: {e}")
        raise


@daemon.command()
@click.argument("plugin_name")
def disable(plugin_name: str):
    """Disable a plugin in holod daemon.

    Args:
        plugin_name: Name of plugin to disable

    Examples:
        holo daemon disable book_enricher
        holo daemon disable link_status_checker
    """
    try:
        daemon = HoloceneDaemon()

        if not daemon.is_running():
            console.print("[yellow]holod is not running[/yellow]")
            return

        # Query API to disable plugin
        import requests

        response = requests.post(f"http://localhost:5555/plugins/{plugin_name}/disable")
        data = response.json()

        if response.status_code == 200:
            console.print(f"[green]✓[/green] Disabled plugin: {plugin_name}")
        else:
            console.print(f"[red]✗[/red] Failed to disable plugin: {data.get('error', 'Unknown error')}")

    except Exception as e:
        console.print(f"[red]✗[/red] Error disabling plugin: {e}")
        raise
