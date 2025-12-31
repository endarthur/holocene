"""Laney's tool definitions for agentic queries.

Provides tools for searching and querying the Holocene knowledge base.
"""

import csv
import io
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
            "description": "Write a document to disk. Creates markdown by default, but can export to PDF, DOCX, HTML, etc. using pandoc. Use this to create reports, summaries, research compilations, reading lists, or any structured document the user requests.",
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
                    "format": {
                        "type": "string",
                        "enum": ["md", "pdf", "docx", "html", "txt", "rst", "epub"],
                        "description": "Output format. Default 'md' (markdown). Other formats use pandoc conversion.",
                        "default": "md"
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
    # === Progress Updates ===
    {
        "type": "function",
        "function": {
            "name": "send_update",
            "description": "Send an interim progress update to the user. Use this during complex, multi-step tasks to share findings as you discover them - don't wait until the end. Good for: sharing interesting discoveries, reporting search results before continuing, giving status on long operations, or sending partial documents section by section.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "The update message to send. Can include markdown formatting. Keep it focused and useful - share what you found, not just 'still working'."
                    },
                    "update_type": {
                        "type": "string",
                        "enum": ["discovery", "progress", "result", "question"],
                        "description": "Type of update: 'discovery' for interesting findings, 'progress' for status updates, 'result' for partial results, 'question' for clarifying questions",
                        "default": "progress"
                    }
                },
                "required": ["message"]
            }
        }
    },
    # === URL Fetching ===
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch and extract text content from a URL. Use this to read webpage content, articles, documentation, etc. Returns plain text extracted from the page.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch"
                    },
                    "max_length": {
                        "type": "integer",
                        "description": "Maximum characters to return (default: 8000)",
                        "default": 8000
                    }
                },
                "required": ["url"]
            }
        }
    },
    # === Item Details ===
    {
        "type": "function",
        "function": {
            "name": "get_book_details",
            "description": "Get full details of a specific book by its ID. Use after searching to get complete information about a book.",
            "parameters": {
                "type": "object",
                "properties": {
                    "book_id": {
                        "type": "integer",
                        "description": "The book's database ID"
                    }
                },
                "required": ["book_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_paper_details",
            "description": "Get full details of a specific paper by its ID. Use after searching to get complete information including abstract.",
            "parameters": {
                "type": "object",
                "properties": {
                    "paper_id": {
                        "type": "integer",
                        "description": "The paper's database ID"
                    }
                },
                "required": ["paper_id"]
            }
        }
    },
    # === Wikipedia ===
    {
        "type": "function",
        "function": {
            "name": "wikipedia_search",
            "description": "Search Wikipedia for articles. Returns titles and short descriptions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results (default: 5)",
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
            "name": "wikipedia_summary",
            "description": "Get the summary/introduction of a Wikipedia article. Use after searching to get detailed info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Wikipedia article title (e.g., 'Python (programming language)')"
                    }
                },
                "required": ["title"]
            }
        }
    },
    # === User Profile (Personality Memory) ===
    {
        "type": "function",
        "function": {
            "name": "get_user_profile",
            "description": "Read your memory of the user's preferences, interests, and personality. This helps you personalize responses. Check this when you want to tailor your response to the user.",
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
            "name": "update_user_profile",
            "description": "Update your memory of the user. Use this when you learn something important about their preferences, interests, communication style, or ongoing projects. Be selective - only record genuinely useful information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "addition": {
                        "type": "string",
                        "description": "New information to add to the profile (will be appended)"
                    },
                    "replace_all": {
                        "type": "boolean",
                        "description": "If true, replaces entire profile instead of appending. Use sparingly.",
                        "default": False
                    }
                },
                "required": ["addition"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_conversation_title",
            "description": "Set or update the title of the current conversation. Use this proactively after the first exchange to give the conversation a descriptive title based on its topic. Update if the conversation topic shifts significantly.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short, descriptive title for the conversation (max 60 chars). Should capture the main topic or question."
                    }
                },
                "required": ["title"]
            }
        }
    },
    # === Task Management Tools ===
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Create a background task for yourself to work on later. Use this for research, analysis, or discovery tasks that don't need immediate results. The task will be processed by the daemon and you'll be notified when complete.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short title for the task (max 80 chars)"
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed description of what to do, including any specific instructions or constraints"
                    },
                    "task_type": {
                        "type": "string",
                        "enum": ["research", "discovery", "enrichment", "analysis", "maintenance"],
                        "description": "Type of task: research (find information), discovery (find new items), enrichment (improve existing items), analysis (generate insights), maintenance (cleanup/checks)"
                    },
                    "priority": {
                        "type": "integer",
                        "description": "Priority 1-10 (1=urgent, 5=normal, 10=whenever). Default: 5",
                        "default": 5
                    },
                    "model": {
                        "type": "string",
                        "enum": ["primary", "reasoning", "fast"],
                        "description": "Model to use: primary (default), reasoning (complex analysis), fast (simple tasks)",
                        "default": "primary"
                    },
                    "deadline": {
                        "type": "string",
                        "description": "Optional deadline as ISO datetime (e.g., '2025-01-15T12:00:00')"
                    }
                },
                "required": ["title", "description", "task_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_my_tasks",
            "description": "List your pending, running, and recently completed tasks. Use to check on background work status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["all", "pending", "running", "completed", "failed"],
                        "description": "Filter by status. Default: all",
                        "default": "all"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of tasks to return. Default: 10",
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
            "name": "get_task_result",
            "description": "Get the detailed result of a completed task, including any items added to the collection.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "integer",
                        "description": "ID of the task to retrieve"
                    }
                },
                "required": ["task_id"]
            }
        }
    },
    # === Collection Addition Tools ===
    {
        "type": "function",
        "function": {
            "name": "add_link",
            "description": "Add a link/URL to the user's collection. Use when you discover useful resources during research. The link will be archived automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to add"
                    },
                    "title": {
                        "type": "string",
                        "description": "Title/description of the link"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional notes about why this link is relevant"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags for categorization"
                    }
                },
                "required": ["url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_paper",
            "description": "Add an academic paper to the collection. Provide DOI or arXiv ID and metadata will be fetched automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "doi": {
                        "type": "string",
                        "description": "DOI of the paper (e.g., '10.1000/xyz123')"
                    },
                    "arxiv_id": {
                        "type": "string",
                        "description": "arXiv ID (e.g., '2103.12345')"
                    },
                    "title": {
                        "type": "string",
                        "description": "Paper title (used if DOI/arXiv lookup fails)"
                    },
                    "authors": {
                        "type": "string",
                        "description": "Authors (used if DOI/arXiv lookup fails)"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional notes about relevance"
                    }
                },
                "required": []
            }
        }
    },
    # === Email Tools ===
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": "Send an email to someone. Can only send to whitelisted addresses. Use this when the user asks you to email someone.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email address (must be whitelisted)"
                    },
                    "subject": {
                        "type": "string",
                        "description": "Email subject line"
                    },
                    "body": {
                        "type": "string",
                        "description": "Email body (markdown-style formatting supported)"
                    }
                },
                "required": ["to", "subject", "body"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "email_whitelist_add",
            "description": "Add an email address or domain to Laney's whitelist. Only the owner can do this. Domain format: @domain.com",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "Email address (user@example.com) or domain (@example.com)"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional note about who this is (e.g., 'Arthur's friend')"
                    }
                },
                "required": ["address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "email_whitelist_remove",
            "description": "Remove an email address or domain from Laney's whitelist. Only the owner can do this.",
            "parameters": {
                "type": "object",
                "properties": {
                    "address": {
                        "type": "string",
                        "description": "Email address or domain to remove"
                    }
                },
                "required": ["address"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "email_whitelist_list",
            "description": "List all whitelisted email addresses and domains",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    # === Export Tools ===
    {
        "type": "function",
        "function": {
            "name": "export_books_csv",
            "description": "Export the book collection to a CSV file. Returns the file path for attachment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Optional search query to filter books"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum books to export (default: all)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "export_links_csv",
            "description": "Export saved links to a CSV file. Returns the file path for attachment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Optional search query to filter links"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum links to export (default: 500)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "export_papers_csv",
            "description": "Export academic papers to a CSV file. Returns the file path for attachment.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Optional search query to filter papers"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum papers to export (default: all)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_collection_report",
            "description": "Generate a markdown report summarizing the collection (stats, recent additions, patterns). Returns file path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "include_books": {
                        "type": "boolean",
                        "description": "Include books section (default: true)"
                    },
                    "include_papers": {
                        "type": "boolean",
                        "description": "Include papers section (default: true)"
                    },
                    "include_links": {
                        "type": "boolean",
                        "description": "Include links section (default: true)"
                    },
                    "days": {
                        "type": "integer",
                        "description": "Include items from last N days (default: 30)"
                    }
                },
                "required": []
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
        conversation_id: Optional[int] = None,
        pending_updates: Optional[List[Dict[str, Any]]] = None,
        email_config: Optional[Any] = None,
        config_whitelist: Optional[List[str]] = None,
    ):
        """
        Initialize tool handler.

        Args:
            db_path: Path to SQLite database
            brave_api_key: Optional Brave Search API key for web search
            documents_dir: Directory for document exports (default: ~/.holocene/documents)
            conversation_id: Current conversation ID (for title setting)
            pending_updates: Optional external list for interim updates (for async sending)
            email_config: Email configuration (for send_email tool)
            config_whitelist: Base whitelist from config (supplements DB whitelist)
        """
        self.db_path = str(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.brave_api_key = brave_api_key
        self._brave_client = None
        self.conversation_id = conversation_id
        self.email_config = email_config
        self.config_whitelist = config_whitelist or []

        # Documents directory
        if documents_dir:
            self.documents_dir = Path(documents_dir)
        else:
            self.documents_dir = Path.home() / ".holocene" / "documents"
        self.documents_dir.mkdir(parents=True, exist_ok=True)

        # Track documents created during this session (for Telegram file sending)
        self.created_documents: List[Path] = []

        # Track pending updates to send to the user (for interim progress)
        # Use external list if provided (for async sending from Telegram bot)
        self.pending_updates: List[Dict[str, Any]] = pending_updates if pending_updates is not None else []

        # Session-level cache for web searches and URL fetches (avoid redundant API calls)
        self._search_cache: Dict[str, Any] = {}
        self._fetch_cache: Dict[str, Any] = {}

        # Load persistent cache hits into session cache on init
        self._load_persistent_cache()

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
            # Progress updates
            "send_update": self.send_update,
            # URL fetching
            "fetch_url": self.fetch_url,
            # Item details
            "get_book_details": self.get_book_details,
            "get_paper_details": self.get_paper_details,
            # Wikipedia
            "wikipedia_search": self.wikipedia_search,
            "wikipedia_summary": self.wikipedia_summary,
            # User profile
            "get_user_profile": self.get_user_profile,
            "update_user_profile": self.update_user_profile,
            # Conversation management
            "set_conversation_title": self.set_conversation_title,
            # Task management
            "create_task": self.create_task,
            "list_my_tasks": self.list_my_tasks,
            "get_task_result": self.get_task_result,
            # Collection addition
            "add_link": self.add_link,
            "add_paper": self.add_paper,
            # Email
            "send_email": self.send_email,
            "email_whitelist_add": self.email_whitelist_add,
            "email_whitelist_remove": self.email_whitelist_remove,
            "email_whitelist_list": self.email_whitelist_list,
            # Exports
            "export_books_csv": self.export_books_csv,
            "export_links_csv": self.export_links_csv,
            "export_papers_csv": self.export_papers_csv,
            "generate_collection_report": self.generate_collection_report,
        }

    @property
    def brave_client(self):
        """Lazy-load Brave Search client."""
        if self._brave_client is None and self.brave_api_key:
            from ..integrations.brave_search import BraveSearchClient
            self._brave_client = BraveSearchClient(self.brave_api_key)
        return self._brave_client

    # === Persistent Cache ===

    def _load_persistent_cache(self):
        """Load frequently used cache entries into session cache on startup."""
        # We don't preload everything - just check DB on cache miss
        pass

    def _get_cached(self, cache_type: str, cache_key: str) -> Optional[Dict[str, Any]]:
        """Get from persistent cache, update hit count."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT response FROM api_cache
                WHERE cache_type = ? AND cache_key = ?
            """, (cache_type, cache_key))
            row = cursor.fetchone()
            if row:
                # Update hit count
                cursor.execute("""
                    UPDATE api_cache
                    SET hit_count = hit_count + 1, last_hit_at = ?
                    WHERE cache_type = ? AND cache_key = ?
                """, (datetime.now().isoformat(), cache_type, cache_key))
                self.conn.commit()
                return json.loads(row[0])
        except Exception:
            pass  # Cache miss or error - just return None
        return None

    def _set_cached(self, cache_type: str, cache_key: str, response: Dict[str, Any]):
        """Store in persistent cache."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO api_cache (cache_type, cache_key, response, created_at, hit_count, last_hit_at)
                VALUES (?, ?, ?, ?, 0, NULL)
            """, (cache_type, cache_key, json.dumps(response), datetime.now().isoformat()))
            self.conn.commit()
        except Exception:
            pass  # Don't fail on cache errors

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

        # Check session cache first (fastest)
        cache_key = f"{query}|{count}|{freshness}"
        if cache_key in self._search_cache:
            cached = self._search_cache[cache_key].copy()
            cached["cached"] = "session"
            return cached

        # Check persistent cache (still fast, local DB)
        db_cached = self._get_cached("web_search", cache_key)
        if db_cached:
            self._search_cache[cache_key] = db_cached  # Promote to session
            db_cached["cached"] = "persistent"
            return db_cached

        try:
            results = self.brave_client.search_simple(
                query=query,
                count=min(count, 10),
                freshness=freshness,
            )
            result = {
                "query": query,
                "results": results,
                "count": len(results),
            }
            # Cache in both session and persistent storage
            self._search_cache[cache_key] = result
            self._set_cached("web_search", cache_key, result)
            result["cached"] = False
            return result
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
        format: str = "md",
        include_metadata: bool = True,
    ) -> Dict[str, Any]:
        """Write a document to disk, optionally converting via pandoc.

        Args:
            title: Document title
            content: Markdown content (body only, title added automatically)
            filename: Optional filename (without extension)
            format: Output format (md, pdf, docx, html, txt, rst, epub)
            include_metadata: Include generation date and footer

        Returns:
            Dict with file path and status
        """
        import subprocess

        try:
            # Generate filename
            if filename:
                safe_filename = self._slugify_filename(filename)
            else:
                safe_filename = self._slugify_filename(title)

            # Add timestamp to ensure uniqueness
            timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')

            # Build document content (always start with markdown)
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

            full_content = "\n".join(doc_parts)

            # Always write markdown first
            md_filename = f"{safe_filename}-{timestamp}.md"
            md_path = self.documents_dir / md_filename
            md_path.write_text(full_content, encoding='utf-8')

            # If format is md, we're done
            if format == "md":
                self.created_documents.append(md_path)
                return {
                    "success": True,
                    "file_path": str(md_path),
                    "filename": md_filename,
                    "format": "md",
                    "title": title,
                    "size_bytes": len(full_content.encode('utf-8')),
                    "message": f"Document saved: {md_filename}",
                }

            # Convert to requested format using pandoc
            output_filename = f"{safe_filename}-{timestamp}.{format}"
            output_path = self.documents_dir / output_filename

            try:
                # For PDF, try multiple engines in order of preference
                if format == "pdf":
                    pdf_engines = ["wkhtmltopdf", "pdflatex", "xelatex", "lualatex"]
                    last_error = ""
                    success = False

                    for engine in pdf_engines:
                        cmd = ["pandoc", str(md_path), "-o", str(output_path), f"--pdf-engine={engine}"]
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                        if result.returncode == 0:
                            success = True
                            break
                        last_error = result.stderr

                    if not success:
                        # All engines failed - return markdown
                        self.created_documents.append(md_path)
                        return {
                            "success": True,
                            "file_path": str(md_path),
                            "filename": md_filename,
                            "format": "md",
                            "title": title,
                            "warning": f"PDF conversion failed (tried {', '.join(pdf_engines)}). Install one of: texlive-xetex, texlive-latex-base, or wkhtmltopdf. Returning markdown.",
                            "size_bytes": len(full_content.encode('utf-8')),
                        }
                else:
                    cmd = ["pandoc", str(md_path), "-o", str(output_path)]

                    # Add format-specific options
                    if format == "html":
                        cmd.extend(["--standalone", "--self-contained"])
                    # docx, txt, rst, epub work with pandoc defaults

                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

                    if result.returncode != 0:
                        # Pandoc failed - return markdown instead
                        self.created_documents.append(md_path)
                        return {
                            "success": True,
                            "file_path": str(md_path),
                            "filename": md_filename,
                            "format": "md",
                            "title": title,
                            "warning": f"Pandoc conversion to {format} failed: {result.stderr[:200]}. Returning markdown.",
                            "size_bytes": len(full_content.encode('utf-8')),
                        }

                # Conversion succeeded
                self.created_documents.append(output_path)
                # Also keep md as backup
                self.created_documents.append(md_path)

                return {
                    "success": True,
                    "file_path": str(output_path),
                    "filename": output_filename,
                    "format": format,
                    "title": title,
                    "md_backup": str(md_path),
                    "size_bytes": output_path.stat().st_size,
                    "message": f"Document saved as {format.upper()}: {output_filename}",
                }

            except FileNotFoundError:
                # Pandoc not installed
                self.created_documents.append(md_path)
                return {
                    "success": True,
                    "file_path": str(md_path),
                    "filename": md_filename,
                    "format": "md",
                    "title": title,
                    "warning": f"Pandoc not found. Saved as markdown instead.",
                    "size_bytes": len(full_content.encode('utf-8')),
                }
            except subprocess.TimeoutExpired:
                self.created_documents.append(md_path)
                return {
                    "success": True,
                    "file_path": str(md_path),
                    "filename": md_filename,
                    "format": "md",
                    "title": title,
                    "warning": f"Pandoc conversion timed out. Saved as markdown instead.",
                    "size_bytes": len(full_content.encode('utf-8')),
                }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to write document: {str(e)}",
            }

    # === Progress Updates ===

    def send_update(self, message: str, update_type: str = "progress") -> Dict[str, Any]:
        """Send an interim progress update to the user.

        Args:
            message: The update message to send
            update_type: Type of update (discovery, progress, result, question)

        Returns:
            Dict with success status
        """
        # Validate update type
        valid_types = ["discovery", "progress", "result", "question"]
        if update_type not in valid_types:
            update_type = "progress"

        # Queue the update for the Telegram bot to send
        self.pending_updates.append({
            "message": message,
            "type": update_type,
            "timestamp": datetime.now().isoformat(),
        })

        return {
            "success": True,
            "message": f"Update queued ({update_type})",
            "queued_updates": len(self.pending_updates),
        }

    # === URL Fetching ===

    def fetch_url(self, url: str, max_length: int = 8000) -> Dict[str, Any]:
        """Fetch and extract text from a URL.

        Args:
            url: URL to fetch
            max_length: Maximum characters to return

        Returns:
            Dict with extracted text or error
        """
        import requests

        # Check session cache first (fastest)
        cache_key = f"{url}|{max_length}"
        if cache_key in self._fetch_cache:
            cached = self._fetch_cache[cache_key].copy()
            cached["cached"] = "session"
            return cached

        # Check persistent cache (still fast, local DB)
        db_cached = self._get_cached("fetch_url", cache_key)
        if db_cached:
            self._fetch_cache[cache_key] = db_cached  # Promote to session
            db_cached["cached"] = "persistent"
            return db_cached

        try:
            # Fetch the page
            headers = {
                "User-Agent": "Mozilla/5.0 (compatible; Holocene/1.0; +https://github.com/endarthur/holocene)"
            }
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()

            content_type = response.headers.get('content-type', '')

            # Handle different content types
            if 'text/plain' in content_type:
                text = response.text[:max_length]
            elif 'text/html' in content_type or 'html' in content_type:
                # Try to extract text from HTML
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(response.text, 'html.parser')

                    # Remove script and style elements
                    for element in soup(['script', 'style', 'nav', 'footer', 'header']):
                        element.decompose()

                    # Get text
                    text = soup.get_text(separator='\n', strip=True)

                    # Clean up whitespace
                    lines = [line.strip() for line in text.splitlines() if line.strip()]
                    text = '\n'.join(lines)[:max_length]

                except ImportError:
                    # BeautifulSoup not available, return raw
                    text = response.text[:max_length]
            else:
                return {
                    "error": f"Unsupported content type: {content_type}",
                    "url": url,
                }

            result = {
                "success": True,
                "url": url,
                "content": text,
                "length": len(text),
                "truncated": len(response.text) > max_length,
            }
            # Cache in both session and persistent storage
            self._fetch_cache[cache_key] = result
            self._set_cached("fetch_url", cache_key, result)
            result["cached"] = False
            return result

        except requests.exceptions.Timeout:
            return {"error": "Request timed out", "url": url}
        except requests.exceptions.RequestException as e:
            return {"error": f"Failed to fetch URL: {str(e)}", "url": url}
        except Exception as e:
            return {"error": f"Error processing URL: {str(e)}", "url": url}

    # === Item Details ===

    def get_book_details(self, book_id: int) -> Dict[str, Any]:
        """Get full details of a book by ID.

        Args:
            book_id: Book database ID

        Returns:
            Complete book information
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, title, author, publication_year, publisher, isbn,
                   dewey_decimal, call_number, subjects, description,
                   enriched_summary, enriched_tags, source, ia_identifier,
                   created_at, metadata
            FROM books WHERE id = ?
        """, (book_id,))

        row = cursor.fetchone()
        if not row:
            return {"error": f"Book not found with ID: {book_id}"}

        return {
            "id": row[0],
            "title": row[1],
            "author": row[2] or "Unknown",
            "publication_year": row[3],
            "publisher": row[4],
            "isbn": row[5],
            "dewey_decimal": row[6],
            "call_number": row[7],
            "subjects": self._parse_json(row[8]),
            "description": row[9],
            "enriched_summary": row[10],
            "enriched_tags": self._parse_json(row[11]),
            "source": row[12],
            "ia_identifier": row[13],
            "created_at": row[14],
            "metadata": self._parse_json(row[15]) if row[15] else {},
        }

    def get_paper_details(self, paper_id: int) -> Dict[str, Any]:
        """Get full details of a paper by ID.

        Args:
            paper_id: Paper database ID

        Returns:
            Complete paper information
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT id, title, authors, abstract, publication_date, journal,
                   doi, arxiv_id, url, pdf_url, is_open_access, oa_status,
                   created_at, metadata
            FROM papers WHERE id = ?
        """, (paper_id,))

        row = cursor.fetchone()
        if not row:
            return {"error": f"Paper not found with ID: {paper_id}"}

        return {
            "id": row[0],
            "title": row[1],
            "authors": self._parse_json(row[2]),
            "abstract": row[3],
            "publication_date": row[4],
            "journal": row[5],
            "doi": row[6],
            "arxiv_id": row[7],
            "url": row[8],
            "pdf_url": row[9],
            "is_open_access": bool(row[10]),
            "oa_status": row[11],
            "created_at": row[12],
            "metadata": self._parse_json(row[13]) if row[13] else {},
        }

    # === Wikipedia ===

    def wikipedia_search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Search Wikipedia for articles.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching articles
        """
        try:
            from ..research.wikipedia_client import WikipediaClient
            client = WikipediaClient()
            results = client.search(query, limit=limit)
            return {
                "query": query,
                "results": results,
                "count": len(results),
            }
        except Exception as e:
            return {"error": f"Wikipedia search failed: {str(e)}"}

    def wikipedia_summary(self, title: str) -> Dict[str, Any]:
        """Get Wikipedia article summary.

        Args:
            title: Article title

        Returns:
            Article summary and metadata
        """
        try:
            from ..research.wikipedia_client import WikipediaClient
            client = WikipediaClient()
            result = client.get_summary(title)
            if result:
                return {
                    "title": result.get("title"),
                    "summary": result.get("extract"),
                    "description": result.get("description"),
                    "url": result.get("url"),
                }
            else:
                return {"error": f"Article not found: {title}"}
        except Exception as e:
            return {"error": f"Wikipedia lookup failed: {str(e)}"}

    # === User Profile (Personality Memory) ===

    # Reserved slug for user profile
    USER_PROFILE_SLUG = "_laney_user_profile"

    def get_user_profile(self) -> Dict[str, Any]:
        """Get the user profile memory.

        Returns:
            User profile content or empty if not set
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT content, updated_at FROM laney_notes WHERE slug = ?
        """, (self.USER_PROFILE_SLUG,))

        row = cursor.fetchone()
        if row:
            return {
                "profile": row[0],
                "last_updated": row[1],
            }
        else:
            return {
                "profile": "(No user profile yet. Learn about the user and update this!)",
                "last_updated": None,
            }

    def update_user_profile(
        self,
        addition: str,
        replace_all: bool = False,
    ) -> Dict[str, Any]:
        """Update the user profile memory.

        Args:
            addition: New content to add
            replace_all: If True, replace entire profile

        Returns:
            Update status
        """
        try:
            cursor = self.conn.cursor()
            now = datetime.now().isoformat()

            # Check if profile exists
            cursor.execute("""
                SELECT content FROM laney_notes WHERE slug = ?
            """, (self.USER_PROFILE_SLUG,))
            row = cursor.fetchone()

            if row:
                # Update existing
                if replace_all:
                    new_content = addition
                else:
                    # Append with timestamp
                    timestamp = datetime.now().strftime("%Y-%m-%d")
                    new_content = row[0] + f"\n\n[{timestamp}] {addition}"

                cursor.execute("""
                    UPDATE laney_notes
                    SET content = ?, updated_at = ?
                    WHERE slug = ?
                """, (new_content, now, self.USER_PROFILE_SLUG))
            else:
                # Create new profile
                cursor.execute("""
                    INSERT INTO laney_notes (slug, title, content, tags, note_type, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    self.USER_PROFILE_SLUG,
                    "User Profile",
                    addition,
                    '["system", "user-profile"]',
                    "reference",
                    now,
                    now,
                ))

            self.conn.commit()
            return {
                "success": True,
                "message": "User profile updated" if row else "User profile created",
                "replaced": replace_all,
            }

        except Exception as e:
            return {"error": f"Failed to update profile: {str(e)}"}

    def set_conversation_title(self, title: str) -> Dict[str, Any]:
        """Set the title of the current conversation.

        Use this proactively to name conversations based on their topic.

        Args:
            title: Short, descriptive title (max 60 chars)

        Returns:
            Success status
        """
        if not self.conversation_id:
            return {"error": "No active conversation to title"}

        # Truncate if too long
        if len(title) > 60:
            title = title[:57] + "..."

        try:
            # Use a separate connection to update laney_conversations table
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE laney_conversations
                SET title = ?
                WHERE id = ?
            """, (title, self.conversation_id))
            conn.commit()
            conn.close()

            return {
                "success": True,
                "title": title,
                "conversation_id": self.conversation_id,
            }
        except Exception as e:
            return {"error": f"Failed to set title: {str(e)}"}

    # === Task Management Methods ===

    def create_task(
        self,
        title: str,
        description: str,
        task_type: str,
        priority: int = 5,
        model: str = "primary",
        deadline: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a background task for later processing.

        Args:
            title: Short task title
            description: Detailed instructions
            task_type: research|discovery|enrichment|analysis|maintenance
            priority: 1-10 (1=urgent)
            model: primary|reasoning|fast
            deadline: Optional ISO datetime

        Returns:
            Task creation status with ID
        """
        try:
            now = datetime.now().isoformat()

            # Validate task_type
            valid_types = ["research", "discovery", "enrichment", "analysis", "maintenance"]
            if task_type not in valid_types:
                return {"error": f"Invalid task_type. Must be one of: {valid_types}"}

            # Validate priority
            priority = max(1, min(10, priority))

            # Get chat_id from conversation if available
            chat_id = None
            if self.conversation_id:
                cursor = self.conn.cursor()
                cursor.execute(
                    "SELECT chat_id FROM laney_conversations WHERE id = ?",
                    (self.conversation_id,)
                )
                row = cursor.fetchone()
                if row:
                    chat_id = row[0]

            # Create task
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO laney_tasks (
                    chat_id, title, description, task_type, status,
                    priority, model, deadline, created_at
                ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)
            """, (
                chat_id, title[:80], description, task_type,
                priority, model, deadline, now
            ))
            task_id = cursor.lastrowid
            conn.commit()
            conn.close()

            return {
                "success": True,
                "task_id": task_id,
                "title": title[:80],
                "task_type": task_type,
                "priority": priority,
                "status": "pending",
                "message": f"Task #{task_id} queued. Will be processed by daemon.",
            }

        except Exception as e:
            return {"error": f"Failed to create task: {str(e)}"}

    def list_my_tasks(
        self,
        status: str = "all",
        limit: int = 10,
    ) -> Dict[str, Any]:
        """List tasks by status.

        Args:
            status: all|pending|running|completed|failed
            limit: Max results

        Returns:
            List of tasks
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            if status == "all":
                cursor.execute("""
                    SELECT id, title, task_type, status, priority, model,
                           created_at, started_at, completed_at, error
                    FROM laney_tasks
                    ORDER BY
                        CASE status
                            WHEN 'running' THEN 1
                            WHEN 'pending' THEN 2
                            ELSE 3
                        END,
                        priority ASC, created_at DESC
                    LIMIT ?
                """, (limit,))
            else:
                cursor.execute("""
                    SELECT id, title, task_type, status, priority, model,
                           created_at, started_at, completed_at, error
                    FROM laney_tasks
                    WHERE status = ?
                    ORDER BY priority ASC, created_at DESC
                    LIMIT ?
                """, (status, limit))

            tasks = []
            for row in cursor.fetchall():
                tasks.append({
                    "id": row["id"],
                    "title": row["title"],
                    "type": row["task_type"],
                    "status": row["status"],
                    "priority": row["priority"],
                    "model": row["model"],
                    "created": row["created_at"],
                    "started": row["started_at"],
                    "completed": row["completed_at"],
                    "error": row["error"],
                })

            conn.close()

            # Summary counts
            conn2 = sqlite3.connect(self.db_path)
            cursor2 = conn2.cursor()
            cursor2.execute("""
                SELECT status, COUNT(*) FROM laney_tasks GROUP BY status
            """)
            counts = {row[0]: row[1] for row in cursor2.fetchall()}
            conn2.close()

            return {
                "tasks": tasks,
                "counts": counts,
                "total": sum(counts.values()),
            }

        except Exception as e:
            return {"error": f"Failed to list tasks: {str(e)}"}

    def get_task_result(self, task_id: int) -> Dict[str, Any]:
        """Get detailed result of a task.

        Args:
            task_id: Task ID to retrieve

        Returns:
            Task details including output and items added
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("""
                SELECT * FROM laney_tasks WHERE id = ?
            """, (task_id,))

            row = cursor.fetchone()
            conn.close()

            if not row:
                return {"error": f"Task #{task_id} not found"}

            return {
                "id": row["id"],
                "title": row["title"],
                "description": row["description"],
                "type": row["task_type"],
                "status": row["status"],
                "priority": row["priority"],
                "model": row["model"],
                "created": row["created_at"],
                "started": row["started_at"],
                "completed": row["completed_at"],
                "output": json.loads(row["output_data"]) if row["output_data"] else None,
                "items_added": json.loads(row["items_added"]) if row["items_added"] else [],
                "error": row["error"],
            }

        except Exception as e:
            return {"error": f"Failed to get task: {str(e)}"}

    # === Collection Addition Methods ===

    def add_link(
        self,
        url: str,
        title: Optional[str] = None,
        notes: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Add a link to the user's collection.

        Args:
            url: URL to add
            title: Optional title
            notes: Optional notes
            tags: Optional tags list

        Returns:
            Link creation status
        """
        try:
            now = datetime.now().isoformat()

            # Check if link already exists
            cursor = self.conn.cursor()
            cursor.execute("SELECT id, title FROM links WHERE url = ?", (url,))
            existing = cursor.fetchone()

            if existing:
                return {
                    "already_exists": True,
                    "id": existing[0],
                    "title": existing[1],
                    "message": f"Link already in collection (ID: {existing[0]})",
                }

            # Insert new link
            metadata = {}
            if notes:
                metadata["laney_notes"] = notes
            if tags:
                metadata["tags"] = tags

            cursor.execute("""
                INSERT INTO links (url, title, source, first_seen, created_at, metadata)
                VALUES (?, ?, 'laney', ?, ?, ?)
            """, (
                url,
                title,
                now,
                now,
                json.dumps(metadata) if metadata else None,
            ))
            link_id = cursor.lastrowid
            self.conn.commit()

            # Track for task items_added
            if hasattr(self, '_items_added'):
                self._items_added.append({"type": "link", "id": link_id})

            return {
                "success": True,
                "id": link_id,
                "url": url,
                "title": title,
                "source": "laney",
                "message": f"Link added to collection (ID: {link_id})",
            }

        except Exception as e:
            return {"error": f"Failed to add link: {str(e)}"}

    def add_paper(
        self,
        doi: Optional[str] = None,
        arxiv_id: Optional[str] = None,
        title: Optional[str] = None,
        authors: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a paper to the collection.

        Fetches metadata from DOI or arXiv if provided.

        Args:
            doi: DOI identifier
            arxiv_id: arXiv ID
            title: Paper title (fallback)
            authors: Authors (fallback)
            notes: Optional notes

        Returns:
            Paper creation status
        """
        try:
            now = datetime.now().isoformat()
            cursor = self.conn.cursor()

            # Check if already exists
            if doi:
                cursor.execute("SELECT id, title FROM papers WHERE doi = ?", (doi,))
                existing = cursor.fetchone()
                if existing:
                    return {
                        "already_exists": True,
                        "id": existing[0],
                        "title": existing[1],
                        "message": f"Paper already in collection (ID: {existing[0]})",
                    }

            if arxiv_id:
                cursor.execute("SELECT id, title FROM papers WHERE arxiv_id = ?", (arxiv_id,))
                existing = cursor.fetchone()
                if existing:
                    return {
                        "already_exists": True,
                        "id": existing[0],
                        "title": existing[1],
                        "message": f"Paper already in collection (ID: {existing[0]})",
                    }

            # Try to fetch metadata
            paper_data = {"title": title, "authors": authors}

            if arxiv_id:
                try:
                    from ..research.arxiv_client import ArxivClient
                    client = ArxivClient()
                    fetched = client.get_paper(arxiv_id)
                    if fetched:
                        paper_data = fetched
                except Exception:
                    pass

            if doi and not paper_data.get("abstract"):
                try:
                    from ..research.crossref import CrossrefClient
                    client = CrossrefClient()
                    fetched = client.get_paper_by_doi(doi)
                    if fetched:
                        paper_data.update(fetched)
                except Exception:
                    pass

            # Must have at least title
            if not paper_data.get("title"):
                return {"error": "Could not fetch paper metadata. Provide title manually."}

            # Insert paper
            authors_str = paper_data.get("authors", authors)
            if isinstance(authors_str, list):
                authors_str = ", ".join(authors_str)

            cursor.execute("""
                INSERT INTO papers (
                    doi, arxiv_id, title, authors, abstract,
                    publication_date, url, added_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doi,
                arxiv_id,
                paper_data.get("title"),
                authors_str,
                paper_data.get("abstract"),
                paper_data.get("published_date"),
                paper_data.get("url"),
                now,
                notes,
            ))
            paper_id = cursor.lastrowid
            self.conn.commit()

            # Track for task items_added
            if hasattr(self, '_items_added'):
                self._items_added.append({"type": "paper", "id": paper_id})

            return {
                "success": True,
                "id": paper_id,
                "title": paper_data.get("title"),
                "authors": authors_str,
                "doi": doi,
                "arxiv_id": arxiv_id,
                "source": "laney",
                "message": f"Paper added to collection (ID: {paper_id})",
            }

        except Exception as e:
            return {"error": f"Failed to add paper: {str(e)}"}

    def _parse_json(self, field: str) -> Any:
        """Parse JSON field, return empty list if invalid."""
        if not field:
            return []
        try:
            return json.loads(field)
        except (json.JSONDecodeError, TypeError):
            return field  # Return as-is if not JSON

    # === Email Tools ===

    def _is_email_whitelisted(self, address: str) -> bool:
        """Check if email address is whitelisted (config + DB)."""
        address_lower = address.lower()

        # Check config whitelist first
        for allowed in self.config_whitelist:
            allowed_lower = allowed.lower()
            if allowed_lower.startswith('@'):
                if address_lower.endswith(allowed_lower):
                    return True
            else:
                if address_lower == allowed_lower:
                    return True

        # Check DB whitelist
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT address FROM email_whitelist
                WHERE is_active = 1
            """)
            for row in cursor.fetchall():
                db_addr = row[0].lower()
                if db_addr.startswith('@'):
                    if address_lower.endswith(db_addr):
                        return True
                else:
                    if address_lower == db_addr:
                        return True
        except Exception:
            pass

        return False

    def send_email(self, to: str, subject: str, body: str) -> Dict[str, Any]:
        """Send an email to someone.

        Args:
            to: Recipient email address (must be whitelisted)
            subject: Email subject
            body: Email body

        Returns:
            Send status
        """
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        if not self.email_config:
            return {"error": "Email not configured. Cannot send emails."}

        # Check if recipient is whitelisted
        if not self._is_email_whitelisted(to):
            return {
                "error": f"Cannot send to {to}: address not whitelisted. Ask the owner to add them first."
            }

        try:
            # Create message
            msg = MIMEMultipart('alternative')
            msg['From'] = self.email_config.address
            msg['To'] = to
            msg['Subject'] = subject

            # Plain text
            text_part = MIMEText(body, 'plain', 'utf-8')
            msg.attach(text_part)

            # Basic HTML (convert markdown-ish)
            html_body = body.replace('\n', '<br>\n')
            html_body = f"<html><body>{html_body}<br><br>---<br><em>Laney - {self.email_config.address}</em></body></html>"
            html_part = MIMEText(html_body, 'html', 'utf-8')
            msg.attach(html_part)

            # Send
            with smtplib.SMTP(self.email_config.smtp_server, self.email_config.smtp_port) as server:
                server.starttls()
                server.login(self.email_config.username, self.email_config.password)
                server.send_message(msg)

            return {
                "success": True,
                "to": to,
                "subject": subject,
                "message": f"Email sent to {to}"
            }

        except Exception as e:
            return {"error": f"Failed to send email: {str(e)}"}

    def email_whitelist_add(self, address: str, notes: Optional[str] = None) -> Dict[str, Any]:
        """Add an email address or domain to the whitelist.

        Args:
            address: Email address or @domain.com
            notes: Optional description

        Returns:
            Add status
        """
        try:
            # Validate format
            address = address.strip().lower()
            if not address:
                return {"error": "Address cannot be empty"}

            if not address.startswith('@') and '@' not in address:
                return {"error": "Invalid format. Use user@example.com or @example.com"}

            cursor = self.conn.cursor()

            # Check if already exists
            cursor.execute("SELECT id FROM email_whitelist WHERE address = ?", (address,))
            existing = cursor.fetchone()
            if existing:
                # Reactivate if inactive
                cursor.execute("""
                    UPDATE email_whitelist SET is_active = 1, notes = ?
                    WHERE address = ?
                """, (notes, address))
                self.conn.commit()
                return {
                    "success": True,
                    "address": address,
                    "reactivated": True,
                    "message": f"Re-activated {address} in whitelist"
                }

            # Insert new
            cursor.execute("""
                INSERT INTO email_whitelist (address, added_by, added_at, notes, is_active)
                VALUES (?, 'owner', ?, ?, 1)
            """, (address, datetime.now().isoformat(), notes))
            self.conn.commit()

            return {
                "success": True,
                "address": address,
                "message": f"Added {address} to email whitelist"
            }

        except Exception as e:
            return {"error": f"Failed to add to whitelist: {str(e)}"}

    def email_whitelist_remove(self, address: str) -> Dict[str, Any]:
        """Remove an email address or domain from the whitelist.

        Args:
            address: Email address or domain to remove

        Returns:
            Removal status
        """
        try:
            address = address.strip().lower()
            cursor = self.conn.cursor()

            # Check if exists
            cursor.execute("SELECT id FROM email_whitelist WHERE address = ?", (address,))
            existing = cursor.fetchone()

            if not existing:
                # Check if it's in config (can't remove config entries)
                if any(a.lower() == address for a in self.config_whitelist):
                    return {
                        "error": f"{address} is in the config file whitelist. Edit config.yml to remove it."
                    }
                return {"error": f"{address} not found in whitelist"}

            # Soft delete (set inactive)
            cursor.execute("""
                UPDATE email_whitelist SET is_active = 0
                WHERE address = ?
            """, (address,))
            self.conn.commit()

            return {
                "success": True,
                "address": address,
                "message": f"Removed {address} from email whitelist"
            }

        except Exception as e:
            return {"error": f"Failed to remove from whitelist: {str(e)}"}

    def email_whitelist_list(self) -> Dict[str, Any]:
        """List all whitelisted email addresses and domains.

        Returns:
            List of whitelisted entries
        """
        try:
            entries = []

            # Config entries (always present)
            for addr in self.config_whitelist:
                entries.append({
                    "address": addr,
                    "source": "config",
                    "notes": "From config.yml"
                })

            # Database entries
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT address, added_by, added_at, notes
                FROM email_whitelist
                WHERE is_active = 1
                ORDER BY added_at DESC
            """)

            for row in cursor.fetchall():
                entries.append({
                    "address": row[0],
                    "source": "database",
                    "added_by": row[1],
                    "added_at": row[2],
                    "notes": row[3]
                })

            return {
                "count": len(entries),
                "entries": entries,
                "config_count": len(self.config_whitelist),
                "db_count": len(entries) - len(self.config_whitelist)
            }

        except Exception as e:
            return {"error": f"Failed to list whitelist: {str(e)}"}

    # === Export Tools ===

    def export_books_csv(self, query: Optional[str] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        """Export books to CSV file.

        Args:
            query: Optional search filter
            limit: Max books to export

        Returns:
            File path and count
        """
        try:
            cursor = self.conn.cursor()

            if query:
                cursor.execute("""
                    SELECT id, title, authors, isbn, publication_year, publisher,
                           dewey_number, cutter_number, call_number, subjects,
                           summary, added_at
                    FROM books
                    WHERE title LIKE ? OR authors LIKE ? OR subjects LIKE ?
                    ORDER BY title
                """, (f"%{query}%", f"%{query}%", f"%{query}%"))
            else:
                cursor.execute("""
                    SELECT id, title, authors, isbn, publication_year, publisher,
                           dewey_number, cutter_number, call_number, subjects,
                           summary, added_at
                    FROM books
                    ORDER BY title
                """)

            rows = cursor.fetchall()
            if limit:
                rows = rows[:limit]

            # Generate CSV
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['ID', 'Title', 'Authors', 'ISBN', 'Year', 'Publisher',
                           'Dewey', 'Cutter', 'Call Number', 'Subjects', 'Summary', 'Added'])

            for row in rows:
                writer.writerow(row)

            # Save to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"books_export_{timestamp}.csv"
            filepath = self.documents_dir / filename

            with open(filepath, 'w', encoding='utf-8', newline='') as f:
                f.write(output.getvalue())

            self.created_documents.append(filepath)

            return {
                "success": True,
                "file_path": str(filepath),
                "filename": filename,
                "count": len(rows),
                "message": f"Exported {len(rows)} books to {filename}"
            }

        except Exception as e:
            return {"error": f"Failed to export books: {str(e)}"}

    def export_links_csv(self, query: Optional[str] = None, limit: int = 500) -> Dict[str, Any]:
        """Export links to CSV file.

        Args:
            query: Optional search filter
            limit: Max links to export (default 500)

        Returns:
            File path and count
        """
        try:
            cursor = self.conn.cursor()

            if query:
                cursor.execute("""
                    SELECT id, url, title, source, trust_tier, created_at,
                           ia_url, last_checked, status_code
                    FROM links
                    WHERE url LIKE ? OR title LIKE ?
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (f"%{query}%", f"%{query}%", limit))
            else:
                cursor.execute("""
                    SELECT id, url, title, source, trust_tier, created_at,
                           ia_url, last_checked, status_code
                    FROM links
                    ORDER BY created_at DESC
                    LIMIT ?
                """, (limit,))

            rows = cursor.fetchall()

            # Generate CSV
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['ID', 'URL', 'Title', 'Source', 'Trust Tier', 'Created',
                           'Archive URL', 'Last Checked', 'Status'])

            for row in rows:
                writer.writerow(row)

            # Save to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"links_export_{timestamp}.csv"
            filepath = self.documents_dir / filename

            with open(filepath, 'w', encoding='utf-8', newline='') as f:
                f.write(output.getvalue())

            self.created_documents.append(filepath)

            return {
                "success": True,
                "file_path": str(filepath),
                "filename": filename,
                "count": len(rows),
                "message": f"Exported {len(rows)} links to {filename}"
            }

        except Exception as e:
            return {"error": f"Failed to export links: {str(e)}"}

    def export_papers_csv(self, query: Optional[str] = None, limit: Optional[int] = None) -> Dict[str, Any]:
        """Export papers to CSV file.

        Args:
            query: Optional search filter
            limit: Max papers to export

        Returns:
            File path and count
        """
        try:
            cursor = self.conn.cursor()

            if query:
                cursor.execute("""
                    SELECT id, title, authors, doi, arxiv_id, publication_date,
                           abstract, url, added_at
                    FROM papers
                    WHERE title LIKE ? OR authors LIKE ? OR abstract LIKE ?
                    ORDER BY added_at DESC
                """, (f"%{query}%", f"%{query}%", f"%{query}%"))
            else:
                cursor.execute("""
                    SELECT id, title, authors, doi, arxiv_id, publication_date,
                           abstract, url, added_at
                    FROM papers
                    ORDER BY added_at DESC
                """)

            rows = cursor.fetchall()
            if limit:
                rows = rows[:limit]

            # Generate CSV
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['ID', 'Title', 'Authors', 'DOI', 'arXiv ID', 'Published',
                           'Abstract', 'URL', 'Added'])

            for row in rows:
                writer.writerow(row)

            # Save to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"papers_export_{timestamp}.csv"
            filepath = self.documents_dir / filename

            with open(filepath, 'w', encoding='utf-8', newline='') as f:
                f.write(output.getvalue())

            self.created_documents.append(filepath)

            return {
                "success": True,
                "file_path": str(filepath),
                "filename": filename,
                "count": len(rows),
                "message": f"Exported {len(rows)} papers to {filename}"
            }

        except Exception as e:
            return {"error": f"Failed to export papers: {str(e)}"}

    def generate_collection_report(
        self,
        include_books: bool = True,
        include_papers: bool = True,
        include_links: bool = True,
        days: int = 30
    ) -> Dict[str, Any]:
        """Generate a markdown collection report.

        Args:
            include_books: Include books section
            include_papers: Include papers section
            include_links: Include links section
            days: Include items from last N days

        Returns:
            File path and summary
        """
        try:
            cursor = self.conn.cursor()
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
            report_lines = []

            report_lines.append(f"# Holocene Collection Report")
            report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
            report_lines.append(f"Period: Last {days} days")
            report_lines.append("")

            # Overall stats
            report_lines.append("## Collection Overview")
            report_lines.append("")

            cursor.execute("SELECT COUNT(*) FROM books")
            total_books = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM papers")
            total_papers = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM links")
            total_links = cursor.fetchone()[0]

            report_lines.append(f"- **Total Books:** {total_books}")
            report_lines.append(f"- **Total Papers:** {total_papers}")
            report_lines.append(f"- **Total Links:** {total_links}")
            report_lines.append("")

            if include_books:
                report_lines.append("## Books")
                report_lines.append("")

                # Recent books
                cursor.execute("""
                    SELECT title, authors, publication_year, call_number
                    FROM books
                    WHERE added_at >= ?
                    ORDER BY added_at DESC
                    LIMIT 10
                """, (cutoff_date,))
                recent_books = cursor.fetchall()

                if recent_books:
                    report_lines.append(f"### Recently Added ({len(recent_books)} in last {days} days)")
                    report_lines.append("")
                    for book in recent_books:
                        title, authors, year, call = book
                        year_str = f" ({year})" if year else ""
                        call_str = f" [{call}]" if call else ""
                        report_lines.append(f"- **{title}**{year_str} - {authors or 'Unknown'}{call_str}")
                    report_lines.append("")

                # By Dewey class
                cursor.execute("""
                    SELECT SUBSTR(dewey_number, 1, 1) as class, COUNT(*) as cnt
                    FROM books
                    WHERE dewey_number IS NOT NULL
                    GROUP BY class
                    ORDER BY cnt DESC
                """)
                dewey_dist = cursor.fetchall()

                if dewey_dist:
                    dewey_names = {
                        '0': 'Computer Science & Info', '1': 'Philosophy', '2': 'Religion',
                        '3': 'Social Sciences', '4': 'Language', '5': 'Science',
                        '6': 'Technology', '7': 'Arts', '8': 'Literature', '9': 'History'
                    }
                    report_lines.append("### Distribution by Subject")
                    report_lines.append("")
                    for cls, cnt in dewey_dist:
                        name = dewey_names.get(cls, 'Other')
                        report_lines.append(f"- {cls}00s {name}: {cnt}")
                    report_lines.append("")

            if include_papers:
                report_lines.append("## Papers")
                report_lines.append("")

                cursor.execute("""
                    SELECT title, authors, doi
                    FROM papers
                    WHERE added_at >= ?
                    ORDER BY added_at DESC
                    LIMIT 10
                """, (cutoff_date,))
                recent_papers = cursor.fetchall()

                if recent_papers:
                    report_lines.append(f"### Recently Added ({len(recent_papers)} in last {days} days)")
                    report_lines.append("")
                    for paper in recent_papers:
                        title, authors, doi = paper
                        authors_short = authors[:50] + "..." if authors and len(authors) > 50 else authors
                        report_lines.append(f"- **{title}** - {authors_short or 'Unknown'}")
                    report_lines.append("")

            if include_links:
                report_lines.append("## Links")
                report_lines.append("")

                cursor.execute("""
                    SELECT COUNT(*) FROM links WHERE created_at >= ?
                """, (cutoff_date,))
                recent_link_count = cursor.fetchone()[0]

                cursor.execute("""
                    SELECT trust_tier, COUNT(*) FROM links GROUP BY trust_tier
                """)
                tier_dist = cursor.fetchall()

                report_lines.append(f"### Summary")
                report_lines.append(f"- Added in last {days} days: {recent_link_count}")
                report_lines.append("")
                report_lines.append("### By Trust Tier")
                for tier, cnt in tier_dist:
                    report_lines.append(f"- {tier or 'unclassified'}: {cnt}")
                report_lines.append("")

                # Recent interesting links
                cursor.execute("""
                    SELECT title, url FROM links
                    WHERE created_at >= ? AND title IS NOT NULL AND title != ''
                    ORDER BY created_at DESC
                    LIMIT 5
                """, (cutoff_date,))
                recent_links = cursor.fetchall()

                if recent_links:
                    report_lines.append("### Recent Links")
                    for title, url in recent_links:
                        title_short = title[:60] + "..." if len(title) > 60 else title
                        report_lines.append(f"- [{title_short}]({url})")
                    report_lines.append("")

            report_lines.append("---")
            report_lines.append("*Generated by Laney*")

            # Save to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"collection_report_{timestamp}.md"
            filepath = self.documents_dir / filename

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(report_lines))

            self.created_documents.append(filepath)

            return {
                "success": True,
                "file_path": str(filepath),
                "filename": filename,
                "total_books": total_books,
                "total_papers": total_papers,
                "total_links": total_links,
                "message": f"Generated collection report: {filename}"
            }

        except Exception as e:
            return {"error": f"Failed to generate report: {str(e)}"}
