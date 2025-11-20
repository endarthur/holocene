"""Book Classification Plugin - Automatically classifies books with Dewey/UDC.

This plugin:
- Monitors for books.added and enrichment.complete events
- Classifies unclassified books automatically
- Uses NanoGPT (DeepSeek V3) for Dewey Decimal Classification
- Generates Cutter numbers and full call numbers
- Runs classification in background (non-blocking)
- Publishes classification.complete events
"""

import json
from typing import Dict
from holocene.core import Plugin, Message
from holocene.research.dewey_classifier import DeweyClassifier, generate_cutter_number


class BookClassifierPlugin(Plugin):
    """Automatically classifies books with Dewey Decimal Classification."""

    def get_metadata(self):
        return {
            "name": "book_classifier",
            "version": "1.0.0",
            "description": "Automatically classifies books with Dewey Decimal Classification",
            "runs_on": ["rei", "wmut", "both"],
            "requires": []
        }

    def on_load(self):
        """Initialize the plugin."""
        self.logger.info("BookClassifier plugin loaded")

        # Get API key from config
        api_key = getattr(self.core.config.llm, 'api_key', None)

        if not api_key:
            self.logger.warning("No NanoGPT API key configured - classification will be disabled")
            self.classifier = None
        else:
            try:
                self.classifier = DeweyClassifier()
                self.logger.info("DeweyClassifier initialized")
            except Exception as e:
                self.logger.error(f"Failed to initialize DeweyClassifier: {e}")
                self.classifier = None

        # Stats
        self.classified_count = 0
        self.failed_count = 0

    def on_enable(self):
        """Enable the plugin and subscribe to events."""
        self.logger.info("BookClassifier plugin enabled")

        # Subscribe to book events
        self.subscribe('books.added', self._on_book_added)
        self.subscribe('enrichment.complete', self._on_enrichment_complete)
        self.subscribe('classification.requested', self._on_classification_requested)

    def _on_book_added(self, msg: Message):
        """Handle books.added event - classify new books."""
        book_id = msg.data.get('book_id')
        if not book_id:
            return

        self.logger.info(f"New book added: {book_id}, checking if needs classification")

        # Check if book needs classification
        book = self.core.db.get_book(book_id)
        if not book:
            self.logger.warning(f"Book {book_id} not found")
            return

        # Check if already classified
        if book.get('udc_classification') or self._has_classification_metadata(book):
            self.logger.info(f"Book {book_id} already classified, skipping")
            return

        # Check if enriched (classification is better after enrichment)
        if not book.get('enriched_summary') and not self._has_enrichment_metadata(book):
            self.logger.info(f"Book {book_id} not yet enriched, waiting for enrichment first")
            return

        # Classify in background
        self.logger.info(f"Classifying book {book_id} in background")
        self._classify_book_async(book_id, book)

    def _on_enrichment_complete(self, msg: Message):
        """Handle enrichment.complete event - classify newly enriched books."""
        book_id = msg.data.get('book_id')
        if not book_id:
            return

        self.logger.info(f"Book {book_id} enrichment complete, checking if needs classification")

        book = self.core.db.get_book(book_id)
        if not book:
            return

        # Check if already classified
        if book.get('udc_classification') or self._has_classification_metadata(book):
            self.logger.info(f"Book {book_id} already classified")
            return

        # Classify now that we have enrichment
        self.logger.info(f"Classifying newly enriched book {book_id}")
        self._classify_book_async(book_id, book)

    def _on_classification_requested(self, msg: Message):
        """Handle manual classification requests."""
        book_id = msg.data.get('book_id')
        force = msg.data.get('force', False)

        if not book_id:
            return

        book = self.core.db.get_book(book_id)
        if not book:
            self.logger.warning(f"Book {book_id} not found")
            return

        # Check if already classified (unless forced)
        if not force and (book.get('udc_classification') or self._has_classification_metadata(book)):
            self.logger.info(f"Book {book_id} already classified (use force=True to re-classify)")
            return

        self.logger.info(f"Classifying book {book_id} (force={force})")
        self._classify_book_async(book_id, book)

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

    def _has_classification_metadata(self, book: Dict) -> bool:
        """Check if book has classification in metadata JSON."""
        metadata = book.get('metadata')
        if not metadata or metadata == '{}':
            return False

        try:
            metadata_dict = json.loads(metadata) if isinstance(metadata, str) else metadata
            return 'classification' in metadata_dict
        except (json.JSONDecodeError, TypeError):
            return False

    def _classify_book_async(self, book_id: int, book: Dict):
        """Classify a book asynchronously."""
        if not self.classifier:
            self.logger.error("Cannot classify: No classifier configured")
            return

        def do_classification():
            """Actually perform the classification (runs in background thread)."""
            try:
                result = self._classify_book(book_id, book)
                return result
            except Exception as e:
                self.logger.error(f"Classification failed for book {book_id}: {e}", exc_info=True)
                self.failed_count += 1
                raise

        def on_complete(result):
            """Called when classification completes."""
            self.classified_count += 1
            self.logger.info(f"Classification complete for book {book_id} (total: {self.classified_count})")

            # Publish completion event
            self.publish('classification.complete', {
                'book_id': book_id,
                'dewey_number': result['dewey_number'],
                'dewey_label': result.get('dewey_label', ''),
                'confidence': result.get('confidence', 'medium'),
                'cutter_number': result.get('cutter_number', ''),
                'call_number': result.get('call_number', ''),
                'stats': {
                    'classified': self.classified_count,
                    'failed': self.failed_count
                }
            })

        def on_error(error):
            """Called if classification fails."""
            self.logger.error(f"Background classification failed: {error}")
            self.publish('classification.failed', {
                'book_id': book_id,
                'error': str(error)
            })

        # Run in background
        self.run_in_background(
            do_classification,
            callback=on_complete,
            error_handler=on_error
        )

    def _classify_book(self, book_id: int, book: Dict) -> Dict:
        """Perform book classification using Dewey classifier.

        Args:
            book_id: Book ID
            book: Book dictionary

        Returns:
            Dict with classification results
        """
        title = book.get('title', 'Unknown')
        author = book.get('author', '')
        subtitle = book.get('subtitle', '')
        subjects = book.get('subjects', '')
        publisher = book.get('publisher', '')
        publication_year = book.get('publication_year')

        # Get enriched summary from old column or metadata JSON
        enriched_summary = book.get('enriched_summary', '')
        if not enriched_summary:
            metadata = book.get('metadata')
            if metadata and metadata != '{}':
                try:
                    metadata_dict = json.loads(metadata) if isinstance(metadata, str) else metadata
                    enriched_summary = metadata_dict.get('enrichment', {}).get('summary', '')
                except (json.JSONDecodeError, TypeError):
                    pass

        # Call classifier
        self.logger.info(f"Calling DeweyClassifier for book {book_id}")
        result = self.classifier.classify_book(
            title=title,
            author=author,
            subtitle=subtitle,
            subjects=subjects,
            publisher=publisher,
            publication_year=publication_year,
            enriched_summary=enriched_summary
        )

        # Extract results
        dewey_number = result.get('dewey_number', '')
        confidence = result.get('confidence', 'medium')
        cutter_number = result.get('cutter_number', '')
        call_number = result.get('call_number', '')

        self.logger.info(f"Classification result: {dewey_number} (confidence: {confidence})")

        # Save to database
        success = self.core.db.update_book_classification(
            book_id=book_id,
            udc_number=dewey_number,
            classification_system="Dewey",
            confidence=confidence,
            cutter_number=cutter_number,
            call_number=call_number
        )

        if success:
            self.logger.info(f"Saved classification for book {book_id}")
        else:
            self.logger.error(f"Failed to save classification for book {book_id}")

        return result

    def on_disable(self):
        """Disable the plugin."""
        self.logger.info(f"BookClassifier disabled - Stats: {self.classified_count} classified, {self.failed_count} failed")
