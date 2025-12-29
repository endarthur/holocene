"""Laney's tool definitions for agentic queries.

Provides tools for searching and querying the Holocene knowledge base.
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional, Union


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
]


class LaneyToolHandler:
    """Handler for Laney's tools - executes queries against the database."""

    def __init__(self, db_path: Union[str, Path]):
        """
        Initialize tool handler.

        Args:
            db_path: Path to SQLite database
        """
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row

        # Map tool names to handler methods
        self.handlers = {
            "get_collection_stats": self.get_collection_stats,
            "search_books": self.search_books,
            "search_papers": self.search_papers,
            "search_links": self.search_links,
            "search_mercadolivre": self.search_mercadolivre,
            "search_all": self.search_all,
            "get_recent_items": self.get_recent_items,
        }

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

    def _parse_json(self, field: str) -> Any:
        """Parse JSON field, return empty list if invalid."""
        if not field:
            return []
        try:
            return json.loads(field)
        except (json.JSONDecodeError, TypeError):
            return field  # Return as-is if not JSON
