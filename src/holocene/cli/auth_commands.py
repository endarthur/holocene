"""Authentication commands for holod web interface."""

import secrets
import click
from rich.console import Console
from rich.panel import Panel
from datetime import datetime, timedelta

from ..config import load_config
from ..storage.database import Database

console = Console()


@click.group()
def auth():
    """Manage authentication for holod web interface."""
    pass


@auth.command("link")
@click.option(
    "--telegram-user-id",
    type=int,
    help="Telegram user ID (defaults to config if only one user)",
)
def generate_link(telegram_user_id: int = None):
    """
    Generate a magic link for web login.

    Examples:
        holo auth link                    # For default user
        holo auth link --telegram-user-id 123456
    """
    try:
        config = load_config()
        db = Database(config.db_path)
        cursor = db.conn.cursor()

        # If no telegram_user_id provided, try to get from first/only user
        if not telegram_user_id:
            cursor.execute("SELECT telegram_user_id FROM users LIMIT 1")
            row = cursor.fetchone()
            if row:
                telegram_user_id = row[0]
            else:
                console.print(
                    "[red]Error:[/red] No users found in database.\n"
                    "Either:\n"
                    "1. Use /login command in Telegram bot first (recommended)\n"
                    "2. Or specify --telegram-user-id explicitly"
                )
                db.close()
                return

        # Get or create user
        cursor.execute(
            "SELECT id, telegram_username FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,)
        )
        user_row = cursor.fetchone()

        if user_row:
            user_id = user_row[0]
            username = user_row[1] or "(no username)"
        else:
            # Create new user (admin by default for CLI-created users)
            cursor.execute("""
                INSERT INTO users (telegram_user_id, telegram_username, created_at, is_admin)
                VALUES (?, ?, ?, 1)
            """, (telegram_user_id, None, datetime.now().isoformat()))
            user_id = cursor.lastrowid
            username = "(new user)"
            db.conn.commit()
            console.print(f"[green]✓[/green] Created new user: {user_id}")

        # Generate secure random token
        token = secrets.token_urlsafe(32)  # ~43 chars, URL-safe base64

        # Calculate expiry (5 minutes)
        expires_at = datetime.now() + timedelta(minutes=5)

        # Store token
        cursor.execute("""
            INSERT INTO auth_tokens (user_id, token, created_at, expires_at)
            VALUES (?, ?, ?, ?)
        """, (user_id, token, datetime.now().isoformat(), expires_at.isoformat()))
        db.conn.commit()

        # Build magic link (TODO: get base URL from config)
        base_url = getattr(config, 'holod_url', 'https://holo.stdgeo.com')
        magic_link = f"{base_url}/auth/login?token={token}"

        # Display success message
        console.print(Panel.fit(
            f"[green]🔐 Magic Link Generated[/green]\n\n"
            f"[cyan]User:[/cyan] {username} (ID: {user_id})\n"
            f"[cyan]Telegram ID:[/cyan] {telegram_user_id}\n\n"
            f"[bold]{magic_link}[/bold]\n\n"
            f"⏱️  Expires: {expires_at.strftime('%H:%M:%S')} ({expires_at.strftime('%Y-%m-%d')})\n"
            f"🔒 Single-use only\n\n"
            f"[dim]This link grants full access to the holod web interface.[/dim]",
            title="Web Login Link",
            border_style="cyan"
        ))

        db.close()

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")


@auth.command("list-tokens")
def list_tokens():
    """List active magic link tokens."""
    try:
        config = load_config()
        db = Database(config.db_path)
        cursor = db.conn.cursor()

        # Get all active tokens (not used, not expired)
        cursor.execute("""
            SELECT
                auth_tokens.id,
                auth_tokens.token,
                auth_tokens.created_at,
                auth_tokens.expires_at,
                auth_tokens.used_at,
                users.telegram_username,
                users.telegram_user_id
            FROM auth_tokens
            JOIN users ON auth_tokens.user_id = users.id
            WHERE auth_tokens.used_at IS NULL
              AND auth_tokens.expires_at > ?
            ORDER BY auth_tokens.created_at DESC
        """, (datetime.now().isoformat(),))

        tokens = cursor.fetchall()

        if not tokens:
            console.print("[yellow]No active magic link tokens found.[/yellow]")
            db.close()
            return

        console.print(f"\n[cyan]Active Magic Link Tokens:[/cyan] {len(tokens)}\n")

        for token_row in tokens:
            token_id, token, created_at, expires_at, used_at, username, tg_id = token_row

            # Calculate time until expiry
            expires_dt = datetime.fromisoformat(expires_at)
            time_left = expires_dt - datetime.now()
            minutes_left = int(time_left.total_seconds() / 60)

            console.print(
                f"[bold]Token #{token_id}[/bold]\n"
                f"  User: {username or '(no username)'} (tg:{tg_id})\n"
                f"  Token: {token[:20]}...\n"
                f"  Created: {created_at}\n"
                f"  Expires: {expires_at} ([yellow]{minutes_left} min left[/yellow])\n"
            )

        db.close()

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")


@auth.command("revoke-token")
@click.argument("token_id", type=int)
def revoke_token(token_id: int):
    """Revoke a magic link token by ID."""
    try:
        config = load_config()
        db = Database(config.db_path)
        cursor = db.conn.cursor()

        # Mark as used (effectively revoking it)
        cursor.execute("""
            UPDATE auth_tokens
            SET used_at = ?
            WHERE id = ? AND used_at IS NULL
        """, (datetime.now().isoformat(), token_id))

        if cursor.rowcount > 0:
            db.conn.commit()
            console.print(f"[green]✓[/green] Revoked token #{token_id}")
        else:
            console.print(f"[yellow]Token #{token_id} not found or already used.[/yellow]")

        db.close()

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
