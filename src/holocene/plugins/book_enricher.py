"""Book Enrichment Plugin - Automatically enriches books using LLM.

This plugin:
- Monitors for books.added events
- Enriches unenriched books automatically
- Uses NanoGPT (DeepSeek V3) for summaries and tags
- Runs enrichment in background (non-blocking)
- Publishes enrichment.complete events
"""

import json
from typing import Dict, List
from holocene.core import Plugin, Message
from holocene.llm.nanogpt import NanoGPTClient


class BookEnricherPlugin(Plugin):
    """Automatically enriches books with LLM-generated metadata."""

    def get_metadata(self):
        return {
            "name": "book_enricher",
            "version": "1.0.0",
            "description": "Automatically enriches books with AI-generated summaries and tags",
            "runs_on": ["rei", "wmut", "both"],  # Can run anywhere
            "requires": []
        }

    def on_load(self):
        """Initialize the plugin."""
        self.logger.info("BookEnricher plugin loaded")

        # Get NanoGPT API key from config
        self.api_key = getattr(self.core.config.llm, 'api_key', None)

        if not self.api_key:
            self.logger.warning("No NanoGPT API key configured - enrichment will be disabled")
            self.llm_client = None
        else:
            self.llm_client = NanoGPTClient(self.api_key)
            self.logger.info("NanoGPT client initialized")

        # Stats
        self.enriched_count = 0
        self.failed_count = 0

    def on_enable(self):
        """Enable the plugin and subscribe to events."""
        self.logger.info("BookEnricher plugin enabled")

        # Subscribe to book events
        self.subscribe('books.added', self._on_book_added)
        self.subscribe('enrichment.requested', self._on_enrichment_requested)

    def _on_book_added(self, msg: Message):
        """Handle books.added event - automatically enrich new books."""
        book_id = msg.data.get('book_id')
        if not book_id:
            return

        self.logger.info(f"New book added: {book_id}, checking if needs enrichment")

        # Check if book needs enrichment
        book = self.core.db.get_book(book_id)
        if not book:
            self.logger.warning(f"Book {book_id} not found")
            return

        # Check if already enriched
        if book.get('enriched_summary') or self._has_enrichment_metadata(book):
            self.logger.info(f"Book {book_id} already enriched, skipping")
            return

        # Enrich in background
        self.logger.info(f"Enriching book {book_id} in background")
        self._enrich_book_async(book_id, book)

    def _on_enrichment_requested(self, msg: Message):
        """Handle manual enrichment requests."""
        book_id = msg.data.get('book_id')
        force = msg.data.get('force', False)

        if not book_id:
            return

        book = self.core.db.get_book(book_id)
        if not book:
            self.logger.warning(f"Book {book_id} not found")
            return

        # Check if already enriched (unless forced)
        if not force and (book.get('enriched_summary') or self._has_enrichment_metadata(book)):
            self.logger.info(f"Book {book_id} already enriched (use force=True to re-enrich)")
            return

        self.logger.info(f"Enriching book {book_id} (force={force})")
        self._enrich_book_async(book_id, book)

    def _has_enrichment_metadata(self, book: Dict) -> bool:
        """Check if book has enrichment in metadata JSON."""
        metadata = book.get('metadata')
        if not metadata or metadata == '{}':
            return False

        try:
            metadata_dict = json.loads(metadata) if isinstance(metadata, str) else metadata
            return 'enrichment' in metadata_dict
        except (json.JSONDecodeError, TypeError):
            return False

    def _enrich_book_async(self, book_id: int, book: Dict):
        """Enrich a book asynchronously."""
        if not self.llm_client:
            self.logger.error("Cannot enrich: No LLM client configured")
            return

        def do_enrichment():
            """Actually perform the enrichment (runs in background thread)."""
            try:
                result = self._enrich_book(book_id, book)
                return result
            except Exception as e:
                self.logger.error(f"Enrichment failed for book {book_id}: {e}", exc_info=True)
                self.failed_count += 1
                raise

        def on_complete(result):
            """Called when enrichment completes."""
            self.enriched_count += 1
            self.logger.info(f"Enrichment complete for book {book_id} (total: {self.enriched_count})")

            # Publish completion event
            self.publish('enrichment.complete', {
                'book_id': book_id,
                'summary': result['summary'],
                'tags': result['tags'],
                'stats': {
                    'enriched': self.enriched_count,
                    'failed': self.failed_count
                }
            })

        def on_error(error):
            """Called if enrichment fails."""
            self.logger.error(f"Background enrichment failed: {error}")
            self.publish('enrichment.failed', {
                'book_id': book_id,
                'error': str(error)
            })

        # Run in background
        self.run_in_background(
            do_enrichment,
            callback=on_complete,
            error_handler=on_error
        )

    def _enrich_book(self, book_id: int, book: Dict) -> Dict:
        """Perform book enrichment using LLM.

        Args:
            book_id: Book ID
            book: Book dictionary

        Returns:
            Dict with 'summary' and 'tags'
        """
        title = book.get('title', 'Unknown')
        author = book.get('author', 'Unknown')
        subtitle = book.get('subtitle', '')
        subjects = book.get('subjects', '')

        # Build context
        book_info = f"Title: {title}"
        if author:
            book_info += f"\nAuthor: {author}"
        if subtitle:
            book_info += f"\nSubtitle: {subtitle}"
        if subjects:
            book_info += f"\nSubjects: {subjects}"

        # Create prompt
        prompt = f"""Analyze this book and provide:
1. A concise 1-2 sentence summary
2. A list of 5-8 relevant tags/topics

Book:
{book_info}

Respond in this exact JSON format:
{{
  "summary": "your summary here",
  "tags": ["tag1", "tag2", "tag3", ...]
}}"""

        system_message = "You are a librarian assistant helping catalog books. Provide accurate, concise summaries and relevant topic tags."

        # Call LLM
        self.logger.info(f"Calling LLM for book {book_id}")
        response = self.llm_client.simple_prompt(
            prompt,
            model="deepseek-ai/DeepSeek-V3.1",
            system=system_message,
            temperature=0.3  # Low temperature for consistency
        )

        # Parse response
        try:
            # Extract JSON from response (handle markdown code blocks)
            response_clean = response.strip()
            if response_clean.startswith('```'):
                # Remove markdown code blocks
                lines = response_clean.split('\n')
                response_clean = '\n'.join(lines[1:-1])

            result = json.loads(response_clean)
            summary = result.get('summary', '')
            tags = result.get('tags', [])

            if not summary or not tags:
                raise ValueError("Missing summary or tags in response")

            self.logger.info(f"LLM enrichment successful for book {book_id}")

        except (json.JSONDecodeError, ValueError) as e:
            self.logger.error(f"Failed to parse LLM response: {e}")
            self.logger.debug(f"Response was: {response}")

            # Fallback: simple extraction
            summary = f"A book about {subjects}" if subjects else f"Book by {author}"
            tags = subjects.split(',')[:5] if subjects else ['uncategorized']

        # Save to database
        success = self.core.db.update_book_enrichment(book_id, summary, tags)

        if success:
            self.logger.info(f"Saved enrichment for book {book_id}")
        else:
            self.logger.error(f"Failed to save enrichment for book {book_id}")

        return {
            'summary': summary,
            'tags': tags
        }

    def on_disable(self):
        """Disable the plugin."""
        self.logger.info(f"BookEnricher disabled - Stats: {self.enriched_count} enriched, {self.failed_count} failed")
