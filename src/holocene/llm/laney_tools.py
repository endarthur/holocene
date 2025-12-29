"""Laney's tool definitions for agentic queries.

Provides tools for searching and querying the Holocene knowledge base.
"""

import json
import math
import re
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from zoneinfo import ZoneInfo


# Tool definitions in OpenAI format
LANEY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_collection_stats",
            "description": "Get overview statistics of the user's entire collection (books, papers, links, mercadolivre favorites)",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_books",
            "description": "Search the user's book collection by title, author, or subject",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (matches title, author, or subjects)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 10)",
                        "default": 10
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_papers",
            "description": "Search the user's academic paper collection by title, author, or abstract",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (matches title, authors, or abstract)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 10)",
                        "default": 10
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_links",
            "description": "Search the user's saved links and bookmarks by URL or title",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (matches URL or title)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 15)",
                        "default": 15
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_mercadolivre",
            "description": "Search the user's Mercado Livre favorites (marketplace items they saved)",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (matches title or category)"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results (default: 15)",
                        "default": 15
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_all",
            "description": "Search across ALL collections (books, papers, links, mercadolivre) at once. Use this for broad queries.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query to match across all collections"
                    },
                    "limit_per_collection": {
                        "type": "integer",
                        "description": "Maximum results per collection (default: 5)",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_items",
            "description": "Get the most recently added items from a specific collection",
            "parameters": {
                "type": "object",
                "properties": {
                    "collection": {
                        "type": "string",
                        "enum": ["books", "papers", "links", "mercadolivre"],
                        "description": "Which collection to get recent items from"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of recent items (default: 10)",
                        "default": 10
                    }
                },
                "required": ["collection"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web using Brave Search. Use this when the user's collection doesn't have the answer, or to find current/recent information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of results (default: 5, max: 10)",
                        "default": 5
                    },
                    "freshness": {
                        "type": "string",
                        "enum": ["pd", "pw", "pm", "py"],
                        "description": "Filter by freshness: pd=past day, pw=past week, pm=past month, py=past year"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "Evaluate a mathematical expression. Supports basic arithmetic, trigonometry, logarithms, and common math functions. Use this for any calculations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Math expression to evaluate (e.g., '2 + 2', 'sqrt(16)', 'sin(pi/4)', 'log(100, 10)')"
                    }
                },
                "required": ["expression"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_datetime",
            "description": "Get the current date, time, and related information. Use this when the user asks about today's date, current time, day of week, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "Timezone name (e.g., 'America/Sao_Paulo', 'UTC', 'US/Eastern'). Default: America/Sao_Paulo",
                        "default": "America/Sao_Paulo"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "date_calculate",
            "description": "Perform date calculations: add/subtract days, find difference between dates, get day of week for a date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["add", "subtract", "difference", "day_of_week"],
                        "description": "Operation to perform"
                    },
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format (or 'today' for current date)"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days to add/subtract (for add/subtract operations)"
                    },
                    "date2": {
                        "type": "string",
                        "description": "Second date in YYYY-MM-DD format (for difference operation)"
                    }
                },
                "required": ["operation", "date"]
            }
        }
    },
    # === Notebook/Memory Tools ===
    {
        "type": "function",
        "function": {
            "name": "note_create",
            "description": "Create a new note in your personal notebook. Use this to remember important information, patterns you've noticed, or insights about the user's collection.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Title for the note"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content of the note (markdown supported)"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for categorization (e.g., ['pattern', 'geology', 'user-preference'])"
                    },
                    "note_type": {
                        "type": "string",
                        "enum": ["note", "observation", "connection", "reminder", "reference"],
                        "description": "Type of note (default: note)"
                    }
                },
                "required": ["title", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "note_read",
            "description": "Read a specific note by its slug/identifier",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "The note's slug identifier"
                    }
                },
                "required": ["slug"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "note_update",
            "description": "Update an existing note's content. Can replace or append.",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "The note's slug identifier"
                    },
                    "content": {
                        "type": "string",
                        "description": "New content (or content to append)"
                    },
                    "append": {
                        "type": "boolean",
                        "description": "If true, append to existing content instead of replacing",
                        "default": False
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "New tags (replaces existing tags if provided)"
                    }
                },
                "required": ["slug", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "note_search",
            "description": "Search your notes by content, title, or tags",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (matches title and content)"
                    },
                    "tag": {
                        "type": "string",
                        "description": "Filter by specific tag"
                    },
                    "note_type": {
                        "type": "string",
                        "enum": ["note", "observation", "connection", "reminder", "reference"],
                        "description": "Filter by note type"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default: 10)",
                        "default": 10
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "note_list",
            "description": "List recent notes from your notebook",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of notes to return (default: 10)",
                        "default": 10
                    },
                    "note_type": {
                        "type": "string",
                        "enum": ["note", "observation", "connection", "reminder", "reference"],
                        "description": "Filter by note type"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "note_delete",
            "description": "Delete a note from your notebook",
            "parameters": {
                "type": "object",
                "properties": {
                    "slug": {
                        "type": "string",
                        "description": "The note's slug identifier"
                    }
                },
                "required": ["slug"]
            }
        }
    },
    # === Sandboxed Code Execution ===
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Execute Python code in a sandboxed environment. Use for data processing, analysis, or complex calculations. Has access to: math, datetime, json, re, collections, itertools, statistics. NO file I/O or network access.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to execute. Use print() to output results."
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Timeout in seconds (default: 5, max: 30)",
                        "default": 5
                    }
                },
                "required": ["code"]
            }
        }
    },
    # === Document Export ===
    {
        "type": "function",
        "function": {
            "name": "write_document",
            "description": "Write a markdown document to disk. Use this to create reports, summaries, research compilations, reading lists, or any structured document the user requests. The file will be saved and can be sent to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Document title (appears in header and is used for filename)"
                    },
                    "content": {
                        "type": "string",
                        "description": "Document body in markdown format. Do NOT include the title - it will be added automatically."
                    },
                    "filename": {
                        "type": "string",
                        "description": "Optional filename (without extension). If omitted, derived from title."
                    },
                    "include_metadata": {
                        "type": "boolean",
                        "description": "If true, includes generation date and 'Generated by Laney' footer. Default: true",
                        "default": True
                    }
                },
                "required": ["title", "content"]
            }
        }
    },
]

# Safe math namespace for calculator
CALC_NAMESPACE = {
    # Basic operations
    'abs': abs, 'round': round, 'min': min, 'max': max,
    'sum': sum, 'pow': pow, 'int': int, 'float': float,
    # Trigonometry
    'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
    'asin': math.asin, 'acos': math.acos, 'atan': math.atan,
    'atan2': math.atan2, 'degrees': math.degrees, 'radians': math.radians,
    # Exponentials and logarithms
    'sqrt': math.sqrt, 'log': math.log, 'log10': math.log10, 'log2': math.log2,
    'exp': math.exp,
    # Rounding
    'floor': math.floor, 'ceil': math.ceil, 'trunc': math.trunc,
    # Constants
    'pi': math.pi, 'e': math.e, 'tau': math.tau, 'inf': math.inf,
    # Hyperbolic
    'sinh': math.sinh, 'cosh': math.cosh, 'tanh': math.tanh,
    # Other useful
    'factorial': math.factorial, 'gcd': math.gcd,
    'hypot': math.hypot, 'copysign': math.copysign,
}


class LaneyToolHandler:
    """Handler for Laney's tools - executes queries against the database."""

    def __init__(
        self,
        db_path: Union[str, Path],
        brave_api_key: Optional[str] = None,
        documents_dir: Optional[Union[str, Path]] = None,
    ):
        """
        Initialize tool handler.

        Args:
            db_path: Path to SQLite database
            brave_api_key: Optional Brave Search API key for web search
            documents_dir: Directory for document exports (default: ~/.holocene/documents)
        """
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.brave_api_key = brave_api_key
        self._brave_client = None

        # Documents directory
        if documents_dir:
            self.documents_dir = Path(documents_dir)
        else:
            self.documents_dir = Path.home() / ".holocene" / "documents"
        self.documents_dir.mkdir(parents=True, exist_ok=True)

        # Track documents created during this session (for Telegram file sending)
        self.created_documents: List[Path] = []

        # Map tool names to handler methods
        self.handlers = {
            # Collection search
            "get_collection_stats": self.get_collection_stats,
            "search_books": self.search_books,
            "search_papers": self.search_papers,
            "search_links": self.search_links,
            "search_mercadolivre": self.search_mercadolivre,
            "search_all": self.search_all,
            "get_recent_items": self.get_recent_items,
            # Web search
            "web_search": self.web_search,
            # Calculator & datetime
            "calculate": self.calculate,
            "get_current_datetime": self.get_current_datetime,
            "date_calculate": self.date_calculate,
            # Notebook/memory
            "note_create": self.note_create,
            "note_read": self.note_read,
            "note_update": self.note_update,
            "note_search": self.note_search,
            "note_list": self.note_list,
            "note_delete": self.note_delete,
            # Code execution
            "run_python": self.run_python,
            # Document export
            "write_document": self.write_document,
        }

    @property
    def brave_client(self):
        """Lazy-load Brave Search client."""
        if self._brave_client is None and self.brave_api_key:
            from ..integrations.brave_search import BraveSearchClient
            self._brave_client = BraveSearchClient(self.brave_api_key)
        return self._brave_client

    def close(self):
        """Close the database connection."""
        self.conn.close()

    def get_collection_stats(self) -> Dict[str, Any]:
        """Get overview statistics of all collections."""
        cursor = self.conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM books")
        books = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM papers")
        papers = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM links")
        links = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM links WHERE archived = 1")
        links_archived = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM mercadolivre_favorites")
        ml_favorites = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM mercadolivre_favorites WHERE dewey_class IS NOT NULL")
        ml_classified = cursor.fetchone()[0]

        return {
            "books": books,
            "papers": papers,
            "links": {
                "total": links,
                "archived": links_archived,
                "unarchived": links - links_archived
            },
            "mercadolivre": {
                "total": ml_favorites,
                "classified": ml_classified
            },
            "total_items": books + papers + links + ml_favorites
        }

    def search_books(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search books by title, author, or subjects."""
        cursor = self.conn.cursor()

        search_pattern = f"%{query}%"
        cursor.execute("""
            SELECT id, title, author, publication_year, dewey_decimal,
                   call_number, subjects, enriched_summary
            FROM books
            WHERE title LIKE ? OR author LIKE ? OR subjects LIKE ?
            ORDER BY title
            LIMIT ?
        """, (search_pattern, search_pattern, search_pattern, limit))

        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "title": row[1],
                "author": row[2] or "Unknown",
                "year": row[3],
                "dewey": row[4],
                "call_number": row[5],
                "subjects": self._parse_json(row[6]),
                "summary": row[7][:200] + "..." if row[7] and len(row[7]) > 200 else row[7]
            })

        return results

    def search_papers(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search papers by title, authors, or abstract."""
        cursor = self.conn.cursor()

        search_pattern = f"%{query}%"
        cursor.execute("""
            SELECT id, title, authors, abstract, publication_date, journal, doi, arxiv_id
            FROM papers
            WHERE title LIKE ? OR authors LIKE ? OR abstract LIKE ?
            ORDER BY publication_date DESC
            LIMIT ?
        """, (search_pattern, search_pattern, search_pattern, limit))

        results = []
        for row in cursor.fetchall():
            abstract = row[3]
            results.append({
                "id": row[0],
                "title": row[1],
                "authors": self._parse_json(row[2]),
                "abstract": abstract[:300] + "..." if abstract and len(abstract) > 300 else abstract,
                "year": row[4][:4] if row[4] else None,
                "journal": row[5],
                "doi": row[6],
                "arxiv_id": row[7]
            })

        return results

    def search_links(self, query: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Search links by URL or title."""
        cursor = self.conn.cursor()

        search_pattern = f"%{query}%"
        cursor.execute("""
            SELECT id, url, title, clean_title, source, archived, trust_tier, first_seen
            FROM links
            WHERE url LIKE ? OR title LIKE ? OR clean_title LIKE ?
            ORDER BY first_seen DESC
            LIMIT ?
        """, (search_pattern, search_pattern, search_pattern, limit))

        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "url": row[1],
                "title": row[3] or row[2],  # Prefer clean_title
                "source": row[4],
                "archived": bool(row[5]),
                "trust_tier": row[6],
                "first_seen": row[7][:10] if row[7] else None  # Just date
            })

        return results

    def search_mercadolivre(self, query: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Search Mercado Livre favorites by title or category."""
        cursor = self.conn.cursor()

        search_pattern = f"%{query}%"
        cursor.execute("""
            SELECT item_id, title, clean_title, price, currency, category_name,
                   dewey_class, is_available
            FROM mercadolivre_favorites
            WHERE title LIKE ? OR clean_title LIKE ? OR category_name LIKE ?
            ORDER BY bookmarked_date DESC
            LIMIT ?
        """, (search_pattern, search_pattern, search_pattern, limit))

        results = []
        for row in cursor.fetchall():
            results.append({
                "item_id": row[0],
                "title": row[2] or row[1],  # Prefer clean_title
                "price": f"{row[4]} {row[3]:.2f}" if row[3] else None,
                "category": row[5],
                "dewey_class": row[6],
                "available": bool(row[7])
            })

        return results

    def search_all(self, query: str, limit_per_collection: int = 5) -> Dict[str, List[Dict]]:
        """Search across all collections at once."""
        return {
            "books": self.search_books(query, limit_per_collection),
            "papers": self.search_papers(query, limit_per_collection),
            "links": self.search_links(query, limit_per_collection),
            "mercadolivre": self.search_mercadolivre(query, limit_per_collection)
        }

    def get_recent_items(self, collection: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get most recently added items from a collection."""
        cursor = self.conn.cursor()

        if collection == "books":
            cursor.execute("""
                SELECT id, title, author, publication_year, dewey_decimal
                FROM books ORDER BY id DESC LIMIT ?
            """, (limit,))
            return [{"id": r[0], "title": r[1], "author": r[2], "year": r[3], "dewey": r[4]}
                    for r in cursor.fetchall()]

        elif collection == "papers":
            cursor.execute("""
                SELECT id, title, authors, publication_date, doi
                FROM papers ORDER BY id DESC LIMIT ?
            """, (limit,))
            return [{"id": r[0], "title": r[1], "authors": self._parse_json(r[2]),
                     "date": r[3], "doi": r[4]} for r in cursor.fetchall()]

        elif collection == "links":
            cursor.execute("""
                SELECT id, url, title, clean_title, source, archived
                FROM links ORDER BY id DESC LIMIT ?
            """, (limit,))
            return [{"id": r[0], "url": r[1], "title": r[3] or r[2],
                     "source": r[4], "archived": bool(r[5])} for r in cursor.fetchall()]

        elif collection == "mercadolivre":
            cursor.execute("""
                SELECT item_id, title, clean_title, price, currency, dewey_class
                FROM mercadolivre_favorites ORDER BY first_synced DESC LIMIT ?
            """, (limit,))
            return [{"item_id": r[0], "title": r[2] or r[1],
                     "price": f"{r[4]} {r[3]:.2f}" if r[3] else None,
                     "dewey": r[5]} for r in cursor.fetchall()]

        return []

    def web_search(
        self,
        query: str,
        count: int = 5,
        freshness: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Search the web using Brave Search.

        Args:
            query: Search query
            count: Number of results (max 10)
            freshness: Filter by freshness (pd, pw, pm, py)

        Returns:
            Dict with 'results' list and 'query' info
        """
        if not self.brave_client:
            return {
                "error": "Web search not available - Brave API key not configured",
                "hint": "Add brave_api_key to config or set BRAVE_API_KEY env var"
            }

        try:
            results = self.brave_client.search_simple(
                query=query,
                count=min(count, 10),
                freshness=freshness,
            )
            return {
                "query": query,
                "results": results,
                "count": len(results),
            }
        except Exception as e:
            return {"error": f"Web search failed: {str(e)}"}

    def calculate(self, expression: str) -> Dict[str, Any]:
        """Evaluate a mathematical expression safely.

        Args:
            expression: Math expression to evaluate

        Returns:
            Dict with 'result' or 'error'
        """
        try:
            # Use restricted eval with only math functions
            result = eval(expression, {"__builtins__": {}}, CALC_NAMESPACE)
            return {
                "expression": expression,
                "result": result,
                "type": type(result).__name__
            }
        except ZeroDivisionError:
            return {"error": "Division by zero"}
        except (SyntaxError, NameError) as e:
            return {"error": f"Invalid expression: {str(e)}"}
        except Exception as e:
            return {"error": f"Calculation failed: {str(e)}"}

    def get_current_datetime(self, timezone: str = "America/Sao_Paulo") -> Dict[str, Any]:
        """Get current date and time information.

        Args:
            timezone: Timezone name (default: America/Sao_Paulo)

        Returns:
            Dict with current datetime info
        """
        try:
            tz = ZoneInfo(timezone)
            now = datetime.now(tz)

            return {
                "timezone": timezone,
                "datetime": now.isoformat(),
                "date": now.strftime("%Y-%m-%d"),
                "time": now.strftime("%H:%M:%S"),
                "day_of_week": now.strftime("%A"),
                "day_of_year": now.timetuple().tm_yday,
                "week_number": now.isocalendar()[1],
                "is_weekend": now.weekday() >= 5,
                "unix_timestamp": int(now.timestamp()),
            }
        except Exception as e:
            return {"error": f"Failed to get datetime: {str(e)}"}

    def date_calculate(
        self,
        operation: str,
        date: str,
        days: Optional[int] = None,
        date2: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Perform date calculations.

        Args:
            operation: add, subtract, difference, or day_of_week
            date: Date in YYYY-MM-DD format or 'today'
            days: Days to add/subtract
            date2: Second date for difference calculation

        Returns:
            Dict with calculation result
        """
        try:
            # Parse first date
            if date.lower() == "today":
                d1 = datetime.now().date()
            else:
                d1 = datetime.strptime(date, "%Y-%m-%d").date()

            if operation == "add":
                if days is None:
                    return {"error": "days parameter required for add operation"}
                result = d1 + timedelta(days=days)
                return {
                    "original_date": str(d1),
                    "days_added": days,
                    "result_date": str(result),
                    "result_day_of_week": result.strftime("%A"),
                }

            elif operation == "subtract":
                if days is None:
                    return {"error": "days parameter required for subtract operation"}
                result = d1 - timedelta(days=days)
                return {
                    "original_date": str(d1),
                    "days_subtracted": days,
                    "result_date": str(result),
                    "result_day_of_week": result.strftime("%A"),
                }

            elif operation == "difference":
                if date2 is None:
                    return {"error": "date2 parameter required for difference operation"}
                if date2.lower() == "today":
                    d2 = datetime.now().date()
                else:
                    d2 = datetime.strptime(date2, "%Y-%m-%d").date()
                diff = (d2 - d1).days
                return {
                    "date1": str(d1),
                    "date2": str(d2),
                    "difference_days": diff,
                    "difference_weeks": round(diff / 7, 2),
                    "difference_months": round(diff / 30.44, 2),  # Average month
                    "difference_years": round(diff / 365.25, 2),
                }

            elif operation == "day_of_week":
                return {
                    "date": str(d1),
                    "day_of_week": d1.strftime("%A"),
                    "day_number": d1.weekday(),  # 0=Monday
                    "is_weekend": d1.weekday() >= 5,
                }

            else:
                return {"error": f"Unknown operation: {operation}"}

        except ValueError as e:
            return {"error": f"Invalid date format: {str(e)}"}
        except Exception as e:
            return {"error": f"Date calculation failed: {str(e)}"}

    # === Notebook/Memory Methods ===

    def _slugify(self, title: str) -> str:
        """Convert title to URL-safe slug."""
        slug = title.lower()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[\s_]+', '-', slug)
        slug = re.sub(r'-+', '-', slug).strip('-')
        # Add timestamp suffix for uniqueness
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        return f"{slug[:50]}-{timestamp}"

    def note_create(
        self,
        title: str,
        content: str,
        tags: Optional[List[str]] = None,
        note_type: str = "note",
    ) -> Dict[str, Any]:
        """Create a new note in the notebook.

        Args:
            title: Note title
            content: Note content (markdown)
            tags: Optional list of tags
            note_type: Type of note

        Returns:
            Dict with created note info
        """
        try:
            cursor = self.conn.cursor()
            slug = self._slugify(title)
            now = datetime.now().isoformat()
            tags_json = json.dumps(tags or [])

            cursor.execute("""
                INSERT INTO laney_notes (slug, title, content, tags, note_type, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (slug, title, content, tags_json, note_type, now, now))

            self.conn.commit()

            return {
                "success": True,
                "slug": slug,
                "title": title,
                "note_type": note_type,
                "tags": tags or [],
                "created_at": now,
            }
        except Exception as e:
            return {"error": f"Failed to create note: {str(e)}"}

    def note_read(self, slug: str) -> Dict[str, Any]:
        """Read a note by slug.

        Args:
            slug: Note identifier

        Returns:
            Dict with note content
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT slug, title, content, tags, note_type, created_at, updated_at
                FROM laney_notes WHERE slug = ?
            """, (slug,))

            row = cursor.fetchone()
            if not row:
                return {"error": f"Note not found: {slug}"}

            return {
                "slug": row[0],
                "title": row[1],
                "content": row[2],
                "tags": json.loads(row[3]) if row[3] else [],
                "note_type": row[4],
                "created_at": row[5],
                "updated_at": row[6],
            }
        except Exception as e:
            return {"error": f"Failed to read note: {str(e)}"}

    def note_update(
        self,
        slug: str,
        content: str,
        append: bool = False,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Update a note.

        Args:
            slug: Note identifier
            content: New content
            append: If True, append instead of replace
            tags: New tags (optional)

        Returns:
            Dict with update status
        """
        try:
            cursor = self.conn.cursor()

            # Get existing note
            cursor.execute("SELECT content, tags FROM laney_notes WHERE slug = ?", (slug,))
            row = cursor.fetchone()
            if not row:
                return {"error": f"Note not found: {slug}"}

            # Prepare new content
            if append:
                new_content = row[0] + "\n\n" + content
            else:
                new_content = content

            # Prepare tags
            if tags is not None:
                tags_json = json.dumps(tags)
            else:
                tags_json = row[1]

            now = datetime.now().isoformat()

            cursor.execute("""
                UPDATE laney_notes
                SET content = ?, tags = ?, updated_at = ?
                WHERE slug = ?
            """, (new_content, tags_json, now, slug))

            self.conn.commit()

            return {
                "success": True,
                "slug": slug,
                "updated_at": now,
                "appended": append,
            }
        except Exception as e:
            return {"error": f"Failed to update note: {str(e)}"}

    def note_search(
        self,
        query: Optional[str] = None,
        tag: Optional[str] = None,
        note_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Search notes.

        Args:
            query: Search query (title/content)
            tag: Filter by tag
            note_type: Filter by type
            limit: Max results

        Returns:
            List of matching notes
        """
        try:
            cursor = self.conn.cursor()

            conditions = []
            params = []

            if query:
                conditions.append("(title LIKE ? OR content LIKE ?)")
                pattern = f"%{query}%"
                params.extend([pattern, pattern])

            if tag:
                conditions.append("tags LIKE ?")
                params.append(f'%"{tag}"%')

            if note_type:
                conditions.append("note_type = ?")
                params.append(note_type)

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            params.append(limit)

            cursor.execute(f"""
                SELECT slug, title, content, tags, note_type, created_at, updated_at
                FROM laney_notes
                WHERE {where_clause}
                ORDER BY updated_at DESC
                LIMIT ?
            """, params)

            results = []
            for row in cursor.fetchall():
                content_preview = row[2][:200] + "..." if len(row[2]) > 200 else row[2]
                results.append({
                    "slug": row[0],
                    "title": row[1],
                    "content_preview": content_preview,
                    "tags": json.loads(row[3]) if row[3] else [],
                    "note_type": row[4],
                    "updated_at": row[6],
                })

            return results
        except Exception as e:
            return [{"error": f"Search failed: {str(e)}"}]

    def note_list(
        self,
        limit: int = 10,
        note_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List recent notes.

        Args:
            limit: Number of notes
            note_type: Filter by type

        Returns:
            List of notes
        """
        return self.note_search(note_type=note_type, limit=limit)

    def note_delete(self, slug: str) -> Dict[str, Any]:
        """Delete a note.

        Args:
            slug: Note identifier

        Returns:
            Dict with deletion status
        """
        try:
            cursor = self.conn.cursor()

            # Check if exists
            cursor.execute("SELECT title FROM laney_notes WHERE slug = ?", (slug,))
            row = cursor.fetchone()
            if not row:
                return {"error": f"Note not found: {slug}"}

            cursor.execute("DELETE FROM laney_notes WHERE slug = ?", (slug,))
            self.conn.commit()

            return {
                "success": True,
                "deleted": slug,
                "title": row[0],
            }
        except Exception as e:
            return {"error": f"Failed to delete note: {str(e)}"}

    # === Sandboxed Code Execution ===

    def run_python(self, code: str, timeout: int = 5) -> Dict[str, Any]:
        """Execute Python code in a sandboxed subprocess.

        Args:
            code: Python code to execute
            timeout: Timeout in seconds (max 30)

        Returns:
            Dict with stdout, stderr, and exit code
        """
        timeout = min(timeout, 30)  # Cap at 30 seconds

        # Simple sandbox - rely on subprocess isolation + timeout
        # Pre-import useful modules for convenience
        sandbox_wrapper = '''
# Pre-import useful modules
import math
import datetime
import json
import re
import collections
import itertools
import functools
import statistics
import random
import string
import decimal
import fractions
from datetime import date, time, timedelta
from collections import Counter, defaultdict, namedtuple, deque
from itertools import combinations, permutations, product

# User code below
'''
        full_code = sandbox_wrapper + "\n" + code

        try:
            # Write to temp file
            with tempfile.NamedTemporaryFile(
                mode='w',
                suffix='.py',
                delete=False,
                encoding='utf-8'
            ) as f:
                f.write(full_code)
                temp_path = f.name

            # Run in subprocess
            result = subprocess.run(
                [sys.executable, temp_path],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tempfile.gettempdir(),  # Run in temp dir
            )

            # Clean up
            Path(temp_path).unlink(missing_ok=True)

            # Truncate long output
            stdout = result.stdout[:5000] if result.stdout else ""
            stderr = result.stderr[:2000] if result.stderr else ""

            return {
                "success": result.returncode == 0,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": result.returncode,
            }

        except subprocess.TimeoutExpired:
            Path(temp_path).unlink(missing_ok=True)
            return {
                "success": False,
                "error": f"Code execution timed out after {timeout} seconds",
                "stdout": "",
                "stderr": "",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Execution failed: {str(e)}",
                "stdout": "",
                "stderr": "",
            }

    # === Document Export ===

    def _slugify_filename(self, title: str) -> str:
        """Convert title to filesystem-safe filename."""
        # Remove/replace problematic characters
        filename = title.lower()
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        filename = re.sub(r'[^\w\s-]', '', filename)
        filename = re.sub(r'[\s_]+', '-', filename)
        filename = re.sub(r'-+', '-', filename).strip('-')
        return filename[:100]  # Limit length

    def write_document(
        self,
        title: str,
        content: str,
        filename: Optional[str] = None,
        include_metadata: bool = True,
    ) -> Dict[str, Any]:
        """Write a markdown document to disk.

        Args:
            title: Document title
            content: Markdown content (body only, title added automatically)
            filename: Optional filename (without extension)
            include_metadata: Include generation date and footer

        Returns:
            Dict with file path and status
        """
        try:
            # Generate filename
            if filename:
                safe_filename = self._slugify_filename(filename)
            else:
                safe_filename = self._slugify_filename(title)

            # Add timestamp to ensure uniqueness
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
            full_filename = f"{safe_filename}-{timestamp}.md"
            file_path = self.documents_dir / full_filename

            # Build document
            doc_parts = []

            # Title
            doc_parts.append(f"# {title}\n")

            # Metadata header
            if include_metadata:
                gen_date = datetime.now().strftime('%Y-%m-%d %H:%M')
                doc_parts.append(f"*Generated by Laney on {gen_date}*\n")

            doc_parts.append("---\n")

            # Content
            doc_parts.append(content)

            # Footer
            if include_metadata:
                doc_parts.append("\n\n---\n")
                doc_parts.append("*Document generated by Laney, Holocene's pattern-recognition AI*")

            # Write file
            full_content = "\n".join(doc_parts)
            file_path.write_text(full_content, encoding='utf-8')

            # Track for Telegram file sending
            self.created_documents.append(file_path)

            return {
                "success": True,
                "file_path": str(file_path),
                "filename": full_filename,
                "title": title,
                "size_bytes": len(full_content.encode('utf-8')),
                "message": f"Document saved: {full_filename}",
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to write document: {str(e)}",
            }

    def _parse_json(self, field: str) -> Any:
        """Parse JSON field, return empty list if invalid."""
        if not field:
            return []
        try:
            return json.loads(field)
        except (json.JSONDecodeError, TypeError):
            return field  # Return as-is if not JSON
