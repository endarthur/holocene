"""Markdown report generation for research findings."""

from datetime import datetime
from typing import List, Dict, Optional
from pathlib import Path


class ResearchReport:
    """Represents a research report."""

    def __init__(self, topic: str):
        """
        Initialize research report.

        Args:
            topic: Research topic
        """
        self.topic = topic
        self.timestamp = datetime.now()
        self.sources: List[Dict] = []
        self.books: List[Dict] = []
        self.figures: List[Dict] = []
        self.analysis: str = ""
        self.metadata: Dict = {}

    def add_source(self, url: str, trust_tier: str, content: str, title: Optional[str] = None):
        """Add a source to the report."""
        self.sources.append({
            "url": url,
            "title": title or url,
            "trust_tier": trust_tier,
            "content": content,
        })

    def add_book(self, title: str, author: str, notes: Optional[str] = None):
        """Add a relevant book from collection."""
        self.books.append({
            "title": title,
            "author": author,
            "notes": notes,
        })

    def add_figure(self, source: str, analysis: str, page: Optional[int] = None):
        """Add analyzed figure/diagram."""
        self.figures.append({
            "source": source,
            "analysis": analysis,
            "page": page,
        })

    def set_analysis(self, analysis: str):
        """Set the main LLM analysis."""
        self.analysis = analysis

    def set_metadata(self, key: str, value: any):
        """Set metadata field."""
        self.metadata[key] = value


class ReportGenerator:
    """Generates markdown reports from research findings."""

    def generate(self, report: ResearchReport) -> str:
        """
        Generate markdown report.

        Args:
            report: ResearchReport object

        Returns:
            Formatted markdown string
        """
        lines = []

        # Header
        lines.append(f"# Research Report: {report.topic}")
        lines.append(f"*Compiled: {report.timestamp.strftime('%Y-%m-%d %H:%M')}*")
        lines.append("")

        # Metadata summary
        if report.metadata:
            source_count = report.metadata.get("source_count", len(report.sources))
            api_calls = report.metadata.get("api_calls_used", 0)
            processing_time = report.metadata.get("processing_time", "unknown")

            lines.append(f"*Sources: {source_count} | API calls: {api_calls} | Time: {processing_time}*")
            lines.append("")

        # Trust tier summary
        if report.sources:
            trust_tiers = [s["trust_tier"] for s in report.sources]
            pre_llm_count = trust_tiers.count("pre-llm")
            total = len(trust_tiers)

            if total > 0:
                pre_llm_pct = int((pre_llm_count / total) * 100)
                trust_emoji = "🟢" if pre_llm_pct > 70 else "🟡" if pre_llm_pct > 30 else "🔴"
                lines.append(f"*Trust Level: {trust_emoji} ({pre_llm_pct}% pre-LLM sources)*")
                lines.append("")

        lines.append("---")
        lines.append("")

        # Executive Summary / Main Analysis
        if report.analysis:
            lines.append("## Executive Summary")
            lines.append("")
            lines.append(report.analysis)
            lines.append("")

        # Physical Books Section
        if report.books:
            lines.append("## Your Physical Book Collection")
            lines.append("")
            lines.append("Relevant books you own:")
            lines.append("")

            for book in report.books:
                lines.append(f"📚 **{book['title']}**")
                if book.get("author"):
                    lines.append(f"   *{book['author']}*")
                if book.get("notes"):
                    lines.append(f"   - {book['notes']}")
                lines.append("")

        # Figures & Diagrams
        if report.figures:
            lines.append("## Figures & Diagrams Analysis")
            lines.append("")

            for i, fig in enumerate(report.figures, 1):
                lines.append(f"### Figure {i}")
                lines.append(f"*Source: {fig['source']}*")
                if fig.get("page"):
                    lines.append(f"*Page: {fig['page']}*")
                lines.append("")
                lines.append(fig["analysis"])
                lines.append("")

        # Sources with Trust Tiers
        if report.sources:
            lines.append("## Sources")
            lines.append("")

            # Group by trust tier
            by_tier = {}
            for source in report.sources:
                tier = source["trust_tier"]
                if tier not in by_tier:
                    by_tier[tier] = []
                by_tier[tier].append(source)

            # Pre-LLM sources first
            for tier in ["pre-llm", "early-llm", "recent", "unknown"]:
                if tier not in by_tier:
                    continue

                tier_emoji = {
                    "pre-llm": "🟢",
                    "early-llm": "🟡",
                    "recent": "🔴",
                    "unknown": "⚪",
                }.get(tier, "⚪")

                lines.append(f"### {tier_emoji} {tier.replace('-', ' ').title()} Sources")
                lines.append("")

                for source in by_tier[tier]:
                    title = source.get("title", source["url"])
                    lines.append(f"- [{title}]({source['url']})")

                lines.append("")

        # Footer
        lines.append("---")
        lines.append("")
        timestamp_id = report.timestamp.strftime("%Y%m%d-%H%M%S")
        lines.append(f"*Report ID: research-{timestamp_id}*")
        lines.append(f"*Generated by Holocene Deep Research Mode*")

        return "\n".join(lines)

    def save(self, report: ResearchReport, output_dir: Path) -> Path:
        """
        Save report to markdown file.

        Args:
            report: ResearchReport object
            output_dir: Directory to save report

        Returns:
            Path to saved file
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename
        timestamp = report.timestamp.strftime("%Y%m%d-%H%M%S")
        # Sanitize topic for filename
        safe_topic = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in report.topic)
        safe_topic = safe_topic.replace(' ', '-')[:50]  # Limit length

        filename = f"research-{safe_topic}-{timestamp}.md"
        filepath = output_dir / filename

        # Generate and save
        content = self.generate(report)
        filepath.write_text(content, encoding="utf-8")

        return filepath
