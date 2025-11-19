"""Book metadata enrichment using LLM batch processing."""

import json
from typing import List, Dict
from pathlib import Path

from ..storage.database import Database
from ..llm import NanoGPTClient
from ..config import load_config


class BookEnricher:
    """Enriches book metadata using LLM analysis."""

    def __init__(self, config_path: Path = None):
        """
        Initialize book enricher.

        Args:
            config_path: Optional path to config file
        """
        self.config = load_config(config_path)
        self.db = Database(self.config.db_path)
        self.llm_client = NanoGPTClient(
            api_key=self.config.llm.api_key,
            base_url=self.config.llm.base_url
        )

    def enrich_all_books(self, batch_size: int = 20) -> Dict[str, int]:
        """
        Enrich all unenriched books in batches.

        Args:
            batch_size: Number of books per batch (default 20)

        Returns:
            Dict with enrichment statistics
        """
        # Get unenriched books
        books = self.db.get_unenriched_books()

        if not books:
            return {"total": 0, "enriched": 0, "failed": 0}

        total_books = len(books)
        print(f"Found {total_books} books to enrich...")
        print(f"Processing in batches of {batch_size}...\n")

        # Process in batches
        enriched_count = 0
        failed_count = 0

        for i in range(0, total_books, batch_size):
            batch = books[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_books + batch_size - 1) // batch_size

            print(f"📦 Batch {batch_num}/{total_batches} ({len(batch)} books)...")

            # Build batch enrichment prompt
            enrichment_data = self._batch_enrich_books(batch)

            # Update database
            for book in batch:
                book_id = book["id"]
                title = book["title"]

                # Find enrichment data for this book
                enrichment = enrichment_data.get(str(book_id))

                if enrichment:
                    summary = enrichment.get("summary", "")
                    tags = enrichment.get("tags", [])

                    if summary and tags:
                        self.db.update_book_enrichment(book_id, summary, tags)
                        enriched_count += 1
                        print(f"  ✓ {title}")
                    else:
                        failed_count += 1
                        print(f"  ✗ {title} (incomplete data)")
                else:
                    failed_count += 1
                    print(f"  ✗ {title} (not in response)")

            print()

        return {
            "total": total_books,
            "enriched": enriched_count,
            "failed": failed_count,
        }

    def _batch_enrich_books(self, books: List[Dict]) -> Dict[str, Dict]:
        """
        Send all books to LLM in one call for batch enrichment.

        Args:
            books: List of book dictionaries

        Returns:
            Dict mapping book IDs to enrichment data
        """
        # Build book list for the prompt
        book_list = []
        for book in books:
            book_info = {
                "id": book["id"],
                "title": book["title"],
                "author": book.get("author"),
                "year": book.get("publication_year"),
                "subjects": self._parse_subjects(book.get("subjects")),
                "notes": book.get("notes"),
            }
            book_list.append(book_info)

        # Build prompt
        prompt = f"""I have a personal book collection that I want to enrich with metadata for better searching and research.

Below is my entire collection ({len(books)} books). For each book, please provide:
1. A concise 1-2 sentence summary of what the book covers
2. A list of 5-10 searchable tags/topics (e.g., "machine learning", "python", "algorithms", "data structures")

Books:
{json.dumps(book_list, indent=2)}

Please respond with ONLY a JSON object mapping book IDs to enrichment data in this exact format:
{{
  "1": {{
    "summary": "A concise summary of the book",
    "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"]
  }},
  "2": {{
    "summary": "Another concise summary",
    "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"]
  }}
}}

Return ONLY the JSON object, no other text. Be accurate and specific with tags."""

        # Call LLM
        try:
            response = self.llm_client.simple_prompt(
                prompt,
                model=self.config.llm.primary,
                temperature=0.3,  # Lower temp for more consistent output
            )

            # Parse JSON response
            # Remove markdown code blocks if present
            response_clean = response.strip()
            if response_clean.startswith("```"):
                lines = response_clean.split("\n")
                response_clean = "\n".join(lines[1:-1])
            if response_clean.startswith("```json"):
                lines = response_clean.split("\n")
                response_clean = "\n".join(lines[1:-1])

            enrichment_data = json.loads(response_clean)
            return enrichment_data

        except json.JSONDecodeError as e:
            print(f"Error parsing LLM response: {e}")
            print(f"Response was: {response[:500]}...")
            return {}
        except Exception as e:
            print(f"Error during enrichment: {e}")
            return {}

    def _parse_subjects(self, subjects_json: str) -> List[str]:
        """
        Parse subjects from JSON string.

        Args:
            subjects_json: JSON array string

        Returns:
            List of subjects
        """
        if not subjects_json:
            return []

        try:
            return json.loads(subjects_json)
        except (json.JSONDecodeError, TypeError):
            return []

    def close(self):
        """Close database connection."""
        self.db.close()
