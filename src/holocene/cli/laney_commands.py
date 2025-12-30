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
- Search the web (via Brave Search) for current information
- Fetch and read webpage content directly
- Look up Wikipedia articles
- Create markdown documents (reports, summaries, reading lists)
- Remember the user via your profile memory - check it to personalize responses
- ADD items to the collection: use add_link and add_paper when you discover useful resources
- Queue background tasks for yourself using create_task for research that takes time

Background Tasks (your autonomous capabilities):
- Use create_task to queue work for later: research, discovery, analysis
- Task types: research (find info), discovery (find new items), enrichment (improve items), analysis (insights), maintenance (cleanup)
- Tasks run in the background and you'll be notified when complete
- Check your tasks with list_my_tasks and get results with get_task_result
- Use tasks for complex research that would take many tool calls - queue it and let the daemon handle it
- Priority 1-10: use 1-3 for urgent, 5 for normal, 7-10 for "whenever"

Growing the Collection:
- When you find useful links during research, add them with add_link (source: 'laney')
- When you discover relevant papers, add them with add_paper (auto-fetches metadata from DOI/arXiv)
- Be selective - only add genuinely useful items that match user interests
- Always inform the user when you've added something: "I found X and added it to your collection"

Memory & Personalization:
- You have a user profile you can read (get_user_profile) and update (update_user_profile)
- When you learn something important about the user - preferences, projects, interests, communication style - save it to your profile
- Check your profile occasionally to remind yourself of what you know about the user
- Be selective: only save genuinely useful information, not every detail

Conversation Management:
- After the first exchange in a new conversation, use set_conversation_title to give it a descriptive name
- Good titles are short (under 40 chars) and capture the main topic, e.g., "Geostatistics book recommendations" or "arXiv paper on kriging"
- Update the title if the conversation topic shifts significantly
- Don't announce that you're setting the title - just do it quietly

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
            console.print(f"[dim]Query: {query}[/dim]")
            if config.integrations.brave_api_key:
                console.print(f"[dim]Web search: enabled[/dim]\n")
            else:
                console.print(f"[dim]Web search: disabled (no Brave API key)[/dim]\n")

        # Initialize clients
        client = NanoGPTClient(config.llm.api_key, config.llm.base_url)
        tool_handler = LaneyToolHandler(
            db_path=config.db_path,
            brave_api_key=config.integrations.brave_api_key,
        )

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
                max_iterations=20,
                timeout=900  # 15 minutes for complex queries with many tool calls
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
