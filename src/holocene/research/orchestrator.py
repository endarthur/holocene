"""Research orchestration - the main engine for overnight research compilation."""

from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import time

from ..storage.database import Database, calculate_trust_tier
from ..llm import NanoGPTClient, BudgetTracker
from ..config import load_config
from .report_generator import ResearchReport, ReportGenerator
from .pdf_handler import PDFHandler
from .wikipedia_client import WikipediaClient


class ResearchOrchestrator:
    """Coordinates overnight research compilation."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize research orchestrator.

        Args:
            config_path: Optional path to config file
        """
        self.config = load_config(config_path)
        self.db = Database(self.config.db_path)
        self.llm_client = NanoGPTClient(
            api_key=self.config.llm.api_key,
            base_url=self.config.llm.base_url
        )
        self.budget_tracker = BudgetTracker(
            data_dir=self.config.data_dir,
            daily_limit=self.config.llm.daily_budget,
            api_key=self.config.llm.api_key,
            base_url=self.config.llm.base_url
        )
        self.pdf_handler = PDFHandler()
        self.report_gen = ReportGenerator()
        self.wikipedia = WikipediaClient(
            cache_dir=self.config.data_dir / "wikipedia_cache"
        )

    def research(
        self,
        topic: str,
        depth: str = "quick",
        include_books: bool = True,
        include_papers: bool = True,
        include_vision: bool = True,
        include_wikipedia: bool = False
    ) -> Path:
        """
        Conduct research on a topic.

        Args:
            topic: Research topic/question
            depth: Research depth - "quick" (10 calls), "deep" (50 calls), "thorough" (100 calls)
            include_books: Check book collection for relevant titles
            include_papers: Check papers collection for relevant academic papers
            include_vision: Analyze figures with vision models
            include_wikipedia: Fetch Wikipedia background information

        Returns:
            Path to generated markdown report
        """
        start_time = time.time()

        # Determine call budget
        call_budget = {
            "quick": 10,
            "deep": 50,
            "thorough": 100,
        }.get(depth, 10)

        print(f"🔍 Starting research on: {topic}")
        print(f"   Depth: {depth} (up to {call_budget} API calls)")
        print()

        # Create report
        report = ResearchReport(topic)
        calls_used = 0

        # Step 1: Search links database
        print("📚 Searching your link collection...")
        relevant_links = self._search_links(topic, limit=20)
        print(f"   Found {len(relevant_links)} relevant links")

        # Step 2: Search book collection (if enabled)
        relevant_books = []
        if include_books:
            print("📖 Checking your book collection...")
            relevant_books = self._search_books(topic, limit=5)
            if relevant_books:
                print(f"   Found {len(relevant_books)} relevant books")
                for book in relevant_books:
                    report.add_book(
                        title=book["title"],
                        author=book.get("author", "Unknown"),
                        notes=book.get("notes")
                    )

        # Step 2.5: Search papers collection (if enabled)
        relevant_papers = []
        if include_papers:
            print("📄 Checking your papers collection...")
            relevant_papers = self._search_papers(topic, limit=5)
            if relevant_papers:
                print(f"   Found {len(relevant_papers)} relevant papers")

        # Step 3: Fetch Wikipedia background (if enabled)
        wikipedia_data = None
        if include_wikipedia:
            print("📚 Fetching Wikipedia background...")
            wikipedia_data = self._fetch_wikipedia_background(topic)
            if wikipedia_data:
                print(f"   Found Wikipedia article: {wikipedia_data['title']}")

        # Step 4: Compile sources for analysis
        print(f"\n🤖 Analyzing sources with DeepSeek...")
        sources_text = self._compile_sources(relevant_links, relevant_books, relevant_papers, wikipedia_data)

        # Step 5: LLM analysis
        analysis = self._analyze_topic(topic, sources_text, relevant_links, relevant_books, relevant_papers)
        report.set_analysis(analysis)
        calls_used += 1

        # Add sources to report
        for link in relevant_links[:10]:  # Limit to top 10 in report
            report.add_source(
                url=link["url"],
                title=link.get("title", link["url"]),
                trust_tier=link.get("trust_tier", "unknown"),
                content=""  # Don't store full content
            )

        # Set metadata
        elapsed = time.time() - start_time
        elapsed_min = int(elapsed // 60)
        elapsed_sec = int(elapsed % 60)

        report.set_metadata("source_count", len(relevant_links))
        report.set_metadata("book_count", len(relevant_books))
        report.set_metadata("paper_count", len(relevant_papers))
        report.set_metadata("api_calls_used", calls_used)
        report.set_metadata("processing_time", f"{elapsed_min}m {elapsed_sec}s")

        # Save report
        output_dir = self.config.data_dir / "research"
        report_path = self.report_gen.save(report, output_dir)

        # Update budget tracker
        self.budget_tracker.increment_usage(calls_used)

        print(f"\n✅ Research complete!")
        print(f"   Report saved: {report_path}")
        print(f"   API calls used: {calls_used}")
        print(f"   Time: {elapsed_min}m {elapsed_sec}s")

        return report_path

    def _search_links(self, topic: str, limit: int = 20) -> List[Dict]:
        """
        Search links database for relevant sources.

        Args:
            topic: Research topic
            limit: Maximum results

        Returns:
            List of relevant links
        """
        # Extract keywords from topic
        keywords = self._extract_keywords(topic)

        # Search links database
        # For now, simple keyword matching on URL and title
        all_links = self.db.get_links(limit=1000)  # Get recent links

        scored_links = []
        for link in all_links:
            score = 0
            url_lower = link["url"].lower()
            title_lower = (link.get("title") or "").lower()

            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in url_lower:
                    score += 2
                if keyword_lower in title_lower:
                    score += 3

            if score > 0:
                scored_links.append((score, link))

        # Sort by score and return top results
        scored_links.sort(reverse=True, key=lambda x: x[0])
        return [link for score, link in scored_links[:limit]]

    def _search_books(self, topic: str, limit: int = 5) -> List[Dict]:
        """
        Search book collection for relevant titles.

        Args:
            topic: Research topic
            limit: Maximum results

        Returns:
            List of relevant books
        """
        keywords = self._extract_keywords(topic)
        return self.db.search_books_for_research(keywords, limit=limit)

    def _search_papers(self, topic: str, limit: int = 5) -> List[Dict]:
        """
        Search papers collection for relevant academic papers.

        Args:
            topic: Research topic
            limit: Maximum results

        Returns:
            List of relevant papers
        """
        keywords = self._extract_keywords(topic)
        return self.db.search_papers_for_research(keywords, limit=limit)

    def _extract_keywords(self, topic: str) -> List[str]:
        """
        Extract keywords from research topic.

        Args:
            topic: Research topic

        Returns:
            List of keywords
        """
        # Simple keyword extraction
        # Remove common words, split on spaces
        stop_words = {"the", "a", "an", "in", "on", "at", "for", "to", "of", "and", "or", "but"}

        words = topic.lower().split()
        keywords = [w.strip(".,!?;:") for w in words if w not in stop_words and len(w) > 2]

        return keywords

    def _compile_sources(self, links: List[Dict], books: List[Dict], papers: List[Dict], wikipedia_data: Optional[Dict] = None) -> str:
        """
        Compile sources into text for LLM analysis.

        Args:
            links: List of relevant links
            books: List of relevant books
            papers: List of relevant papers
            wikipedia_data: Optional Wikipedia article data

        Returns:
            Formatted source text
        """
        parts = []

        # Wikipedia background (if available)
        if wikipedia_data:
            parts.append("## Wikipedia Background")
            parts.append(f"**{wikipedia_data['title']}**")
            parts.append(f"\n{wikipedia_data['extract']}")
            parts.append(f"\n[Read more on Wikipedia]({wikipedia_data['url']})")
            parts.append("")  # Blank line

        if links:
            parts.append("## Web Sources")
            for i, link in enumerate(links[:10], 1):  # Limit to top 10
                trust_emoji = {
                    "pre-llm": "🟢",
                    "early-llm": "🟡",
                    "recent": "🔴",
                    "unknown": "⚪",
                }.get(link.get("trust_tier", "unknown"), "⚪")

                title = link.get("title", link["url"])
                parts.append(f"{i}. {trust_emoji} [{title}]({link['url']})")

        if books:
            parts.append("\n## Books from Your Collection")
            for book in books:
                parts.append(f"- {book['title']} by {book.get('author', 'Unknown')}")
                if book.get("notes"):
                    parts.append(f"  Note: {book['notes']}")

        if papers:
            parts.append("\n## Academic Papers from Your Collection")
            for paper in papers:
                authors_str = ", ".join(paper.get("authors", [])[:2])
                if len(paper.get("authors", [])) > 2:
                    authors_str += " et al."
                parts.append(f"- {paper['title']}")
                if authors_str:
                    parts.append(f"  Authors: {authors_str}")
                if paper.get("journal") and paper.get("publication_date"):
                    parts.append(f"  {paper['journal']} ({paper['publication_date']})")
                if paper.get("notes"):
                    parts.append(f"  Note: {paper['notes']}")

        return "\n".join(parts)

    def _analyze_topic(
        self,
        topic: str,
        sources_text: str,
        links: List[Dict],
        books: List[Dict],
        papers: List[Dict]
    ) -> str:
        """
        Use LLM to analyze topic and sources.

        Args:
            topic: Research topic
            sources_text: Compiled source text
            links: List of links
            books: List of books
            papers: List of papers

        Returns:
            LLM analysis
        """
        # Build prompt
        prompt = f"""I'm researching: {topic}

I've found the following sources from my personal collection:

{sources_text}

Please provide a comprehensive research summary:

1. **Key Concepts**: What are the main ideas related to this topic based on these sources?
2. **Source Quality**: Comment on the trust levels of these sources (note the trust tier indicators)
3. **Book Recommendations**: Which books from my collection should I prioritize? Suggest specific chapters if known.
4. **Paper Insights**: What do the academic papers in my collection tell us? Highlight key findings and methodologies.
5. **Information Gaps**: What aspects of this topic aren't well covered by these sources?
6. **Research Directions**: What should I explore next?

Keep the tone informational and helpful. This is for academic/professional research preparation.
"""

        # Call LLM
        try:
            response = self.llm_client.simple_prompt(
                prompt,
                model="deepseek-ai/DeepSeek-V3.1",
                temperature=0.7
            )
            return response
        except Exception as e:
            return f"Error during analysis: {e}"

    def _fetch_wikipedia_background(self, topic: str) -> Optional[Dict]:
        """
        Fetch Wikipedia background for a topic.

        Args:
            topic: Research topic

        Returns:
            Wikipedia article data or None
        """
        # Try exact title match first
        result = self.wikipedia.get_summary(topic)
        if result:
            return result

        # Try search if exact match fails
        search_results = self.wikipedia.search(topic, limit=1)
        if search_results:
            # Get summary for first result
            return self.wikipedia.get_summary(search_results[0]["title"])

        return None

    def close(self):
        """Close database connection."""
        self.db.close()
