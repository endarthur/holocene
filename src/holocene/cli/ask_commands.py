"""Natural language queries for your personal knowledge collection."""

import json
import click
from rich.console import Console
from rich.panel import Panel
from pathlib import Path
from typing import Dict, List

from ..storage.database import Database
from ..llm import NanoGPTClient
from ..config import load_config

console = Console()


@click.group()
def ask():
    """Ask questions about your collection using natural language."""
    pass


@ask.command("query")
@click.argument("question")
@click.option(
    "--include-links",
    is_flag=True,
    help="Include links in context (experimental - may be slow with 1000+ links)",
)
def ask_query(question: str, include_links: bool):
    """
    Query your personal library using natural language.

    Examples:
        holo ask query "What books do I have about geostatistics?"
        holo ask query "Which papers discuss pattern recognition?"
        holo ask query "Recommend a reading path for structural geology"

    The AI will search through your books and papers to answer your question.
    """
    try:
        config = load_config()
        db = Database(config.db_path)

        # Build collection context
        console.print("[dim]Loading your collection...[/dim]")
        context = _build_collection_context(db, include_links=include_links)

        if context["stats"]["total_items"] == 0:
            console.print("[yellow]Your collection is empty. Add some books or papers first![/yellow]")
            console.print("\nTry:")
            console.print("  holo books add-ia <identifier>  # Add from Internet Archive")
            console.print("  holo papers add <DOI>            # Add a paper")
            return

        # Show what we're querying
        stats = context["stats"]
        console.print(f"[dim]Querying {stats['books']} books, {stats['papers']} papers...[/dim]\n")

        # Call LLM
        response = _query_llm(config, context, question)

        if not response:
            console.print("[red]Failed to get response from LLM.[/red]")
            console.print("Check your NANOGPT_API_KEY configuration.")
            return

        # Display response
        _display_response(response, stats)

        db.close()

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")


def _build_collection_context(db: Database, include_links: bool = False) -> Dict:
    """
    Build JSON context of the user's collection.

    Args:
        db: Database instance
        include_links: Whether to include links (can be large)

    Returns:
        Dict with books, papers, and statistics
    """
    context = {
        "books": [],
        "papers": [],
        "stats": {
            "books": 0,
            "papers": 0,
            "links": 0,
            "total_items": 0,
        }
    }

    # Get all books
    cursor = db.conn.cursor()
    cursor.execute("""
        SELECT id, title, author, publication_year, dewey_decimal, call_number,
               subjects, enriched_summary, enriched_tags, metadata
        FROM books
        ORDER BY title
    """)

    for row in cursor.fetchall():
        book = {
            "id": row[0],
            "title": row[1],
            "author": row[2] or "Unknown",
            "year": row[3],
            "dewey": row[4],
            "call_number": row[5],
            "subjects": _parse_json_field(row[6]),
            "summary": row[7],
            "tags": _parse_json_field(row[8]),
        }
        context["books"].append(book)

    context["stats"]["books"] = len(context["books"])

    # Get all papers
    cursor.execute("""
        SELECT id, title, authors, abstract, publication_date, journal, doi,
               arxiv_id, url, summary
        FROM papers
        ORDER BY publication_date DESC
    """)

    for row in cursor.fetchall():
        paper = {
            "id": row[0],
            "title": row[1],
            "authors": _parse_json_field(row[2]),
            "abstract": row[3],
            "year": row[4][:4] if row[4] else None,  # Extract year from date
            "journal": row[5],
            "doi": row[6],
            "arxiv_id": row[7],
            "url": row[8],
            "summary": row[9],
        }
        context["papers"].append(paper)

    context["stats"]["papers"] = len(context["papers"])

    # TODO: Add links if requested (needs filtering strategy for 1000+ items)
    if include_links:
        cursor.execute("SELECT COUNT(*) FROM links")
        context["stats"]["links"] = cursor.fetchone()[0]

    context["stats"]["total_items"] = (
        context["stats"]["books"] + context["stats"]["papers"]
    )

    return context


def _parse_json_field(field: str) -> List:
    """Parse JSON field, return empty list if invalid."""
    if not field:
        return []
    try:
        return json.loads(field)
    except (json.JSONDecodeError, TypeError):
        return []


def _query_llm(config, context: Dict, question: str) -> str:
    """
    Query the LLM with collection context and user's question.

    Args:
        config: Holocene configuration
        context: Collection context dictionary
        question: User's natural language question

    Returns:
        LLM response string
    """
    # Build prompt
    system_prompt = """You are a helpful librarian assistant for a personal knowledge collection.

Your role is to help the user find relevant books and papers in their collection based on natural language queries.

When answering:
- Be specific and reference actual items from the collection
- Include call numbers for books when available
- Provide brief summaries or explanations
- If no exact matches exist, suggest related items or acknowledge the gap
- Be concise but informative

The collection is relatively small, so you can see everything at once."""

    user_prompt = f"""Here is the user's complete collection:

{json.dumps(context, indent=2)}

User's question: {question}

Please answer their question using information from their collection. Be helpful and specific."""

    try:
        client = NanoGPTClient(
            api_key=config.llm.api_key,
            base_url=config.llm.base_url
        )

        response = client.simple_prompt(
            prompt=user_prompt,
            system=system_prompt,
            model=config.llm.primary,  # DeepSeek V3.1
            temperature=0.3,  # Lower for factual responses
        )

        return response

    except Exception as e:
        console.print(f"[red]LLM API error:[/red] {e}")
        return None


def _display_response(response: str, stats: Dict, show_budget: bool = True):
    """
    Display the LLM response with nice formatting.

    Args:
        response: LLM response text
        stats: Collection statistics
        show_budget: Whether to show budget information
    """
    # Display main response
    console.print(Panel(
        response,
        title="[cyan]AI Librarian Response[/cyan]",
        border_style="cyan"
    ))

    # Show helpful tips
    console.print("\n[dim]─" * 40 + "[/dim]")
    console.print("[dim]Tip: View full details with:[/dim]")
    console.print("  [cyan]holo books list[/cyan]  # List all books")
    console.print("  [cyan]holo papers list[/cyan] # List all papers")
    console.print("  [cyan]holo books search <term>[/cyan]  # Search books")

    # Show collection stats
    console.print(f"\n[dim]Collection: {stats['books']} books, {stats['papers']} papers[/dim]")

    # Show budget info
    if show_budget:
        try:
            config = load_config()
            # Try to load budget info if tracking is available
            # For now, just show a note about budget
            console.print(f"[dim]💡 Used 1 LLM prompt (NanoGPT budget: 2,000/day)[/dim]")
        except Exception:
            pass  # Silently fail if config unavailable


# Make the command directly invokable as `holo ask`
@click.command()
@click.argument("question")
@click.option(
    "--include-links",
    is_flag=True,
    help="Include links in context (experimental)",
)
def ask_shortcut(question: str, include_links: bool):
    """
    Ask questions about your collection using natural language.

    Examples:
        holo ask "What books do I have about geostatistics?"
        holo ask "Which papers discuss pattern recognition?"
        holo ask "Recommend a reading path for structural geology"
    """
    # Call the actual implementation
    from click.testing import CliRunner
    runner = CliRunner()
    ctx = click.get_current_context()
    ctx.invoke(ask_query, question=question, include_links=include_links)
