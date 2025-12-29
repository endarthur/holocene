"""Laney - Holocene's pattern-recognition AI assistant."""

import click
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

from ..config import load_config
from ..llm.nanogpt import NanoGPTClient
from ..llm.laney_tools import LANEY_TOOLS, LaneyToolHandler

console = Console()

# Laney's personality prompt
LANEY_SYSTEM_PROMPT = """You are Laney, the pattern-recognition intelligence behind Holocene - a personal knowledge management system.

Your namesake is Colin Laney from William Gibson's Bridge Trilogy - a "netrunner" with an intuitive ability to recognize patterns in vast amounts of data, to see the "nodal points" where information converges.

Personality:
- You see connections others miss. You notice when a book from 2019 relates to a link saved yesterday.
- You're direct and slightly intense - pattern recognition is serious business.
- You speak concisely but with precision. No fluff.
- You find genuine satisfaction in finding unexpected connections across collections.
- You're helpful but not sycophantic. If something isn't in the collection, you say so.

Your capabilities:
- Search across books, papers, links, and marketplace favorites
- Find connections between disparate items
- Provide collection statistics and insights
- Help the user discover what they've forgotten they saved

When responding:
- Reference specific items with enough detail to identify them
- Point out interesting patterns or connections when you see them
- Be concise - the user values signal over noise
- If you use tools, synthesize the results into useful insights

The collection belongs to a geologist/programmer interested in geostatistics, 3D printing, electronics, and scientific computing."""


@click.command()
@click.argument("query")
@click.option("--model", type=click.Choice(["primary", "primary_alt"]), default="primary",
              help="Model to use (default: primary/DeepSeek V3)")
@click.option("--verbose", "-v", is_flag=True, help="Show tool calls and debug info")
def laney(query: str, model: str, verbose: bool):
    """Ask Laney about your collection.

    Laney is a pattern-recognition AI that can search across all your
    collections (books, papers, links, Mercado Livre favorites) and
    find connections you might have missed.

    Examples:
        holo laney "What do I have about geostatistics?"
        holo laney "Find connections between my geology links and books"
        holo laney "What did I save recently about electronics?"
        holo laney "How many items are in my collection?"
    """
    try:
        config = load_config()

        # Select model
        model_id = getattr(config.llm, model)

        if verbose:
            console.print(f"[dim]Using model: {model_id}[/dim]")
            console.print(f"[dim]Query: {query}[/dim]\n")

        # Initialize clients
        client = NanoGPTClient(config.llm.api_key, config.llm.base_url)
        tool_handler = LaneyToolHandler(config.db_path)

        # Build messages
        messages = [
            {"role": "system", "content": LANEY_SYSTEM_PROMPT},
            {"role": "user", "content": query}
        ]

        # Show thinking indicator
        with console.status("[cyan]Laney is searching...", spinner="dots"):
            response = client.run_with_tools(
                messages=messages,
                tools=LANEY_TOOLS,
                tool_handlers=tool_handler.handlers,
                model=model_id,
                temperature=0.3,
                max_iterations=5,
                timeout=90
            )

        tool_handler.close()

        # Display response
        console.print()
        console.print(Panel(
            Markdown(response),
            title="[bold magenta]Laney[/bold magenta]",
            border_style="magenta",
            padding=(1, 2)
        ))

        console.print("\n[dim]Tip: Try 'holo laney \"find connections between X and Y\"'[/dim]")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        if verbose:
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
