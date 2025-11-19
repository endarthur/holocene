"""UDC (Universal Decimal Classification) classifier using DeepSeek V3."""

from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

from holocene.llm import NanoGPTClient
from holocene.config import load_config
from holocene.storage.database import Database


class UDCClassifier:
    """Classify books and papers using UDC system."""

    def __init__(self, config_path: Path = None):
        """
        Initialize UDC classifier.

        Args:
            config_path: Optional path to config file
        """
        self.config = load_config(config_path)
        self.llm_client = NanoGPTClient(self.config.llm.api_key, self.config.llm.base_url)
        self.db = Database(self.config.db_path)

    def classify_book(
        self,
        title: str,
        author: Optional[str] = None,
        subtitle: Optional[str] = None,
        subjects: Optional[str] = None,
        publisher: Optional[str] = None,
        publication_year: Optional[int] = None,
        enriched_summary: Optional[str] = None,
    ) -> Dict:
        """
        Classify a book using UDC.

        Args:
            title: Book title
            author: Author name(s)
            subtitle: Book subtitle
            subjects: Subject headings
            publisher: Publisher name
            publication_year: Year of publication
            enriched_summary: AI-generated summary if available

        Returns:
            Dictionary with classification results
        """
        # Build metadata description
        metadata_parts = [f"Title: {title}"]

        if author:
            metadata_parts.append(f"Author: {author}")
        if subtitle:
            metadata_parts.append(f"Subtitle: {subtitle}")
        if subjects:
            metadata_parts.append(f"Subjects: {subjects}")
        if publisher:
            metadata_parts.append(f"Publisher: {publisher}")
        if publication_year:
            metadata_parts.append(f"Year: {publication_year}")
        if enriched_summary:
            metadata_parts.append(f"Summary: {enriched_summary}")

        metadata = "\n".join(metadata_parts)

        system_prompt = """You are a professional librarian expert in the Universal Decimal Classification (UDC) system.

UDC is an international classification system used primarily in European and Latin American libraries, including Brazilian universities.

Key UDC main classes:
0 - Generalities, Science and Knowledge
1 - Philosophy, Psychology
2 - Religion, Theology
3 - Social Sciences
31 - Statistics, Demography, Sociology
32 - Politics
33 - Economics
34 - Law
35 - Public administration, Military art
36 - Social welfare
37 - Education
39 - Ethnology, Folklore

5 - Mathematics and Natural Sciences
50 - Generalities about pure sciences
51 - Mathematics
52 - Astronomy
53 - Physics
54 - Chemistry
55 - Geology
56 - Paleontology
57 - Biological sciences
58 - Botany
59 - Zoology

6 - Applied Sciences, Medicine, Technology
61 - Medical sciences
62 - Engineering
63 - Agriculture
64 - Home economics
65 - Business management
66 - Chemical technology
67 - Manufacturing
68 - Industries for finished goods
69 - Building industry

7 - The Arts
8 - Language, Linguistics, Literature
9 - Geography, Biography, History

UDC uses synthesis - numbers can be combined with auxiliaries:
(1/9) - Place (e.g., (81) = Brazil)
=1/=9 - Language
"..." - Time
-0 - Common form auxiliaries

Your task is to assign accurate UDC numbers to books based on their metadata."""

        user_prompt = f"""Classify this book using UDC notation.

Book metadata:
{metadata}

Return ONLY valid JSON (no markdown, no explanation):
{{
  "udc_number": "primary UDC classification number",
  "udc_label": "human-readable subject label",
  "alternative_numbers": ["other possible UDC numbers if applicable"],
  "confidence": "high" | "medium" | "low",
  "reasoning": "brief explanation of classification choice"
}}

Guidelines:
- Use specific numbers when possible (e.g., "550.8" for geostatistics, not just "55" for geology)
- Consider subject, geographic location, and time period
- For interdisciplinary works, choose the primary focus
- Mark confidence based on clarity of subject matter"""

        try:
            response = self.llm_client.simple_prompt(
                prompt=user_prompt,
                system=system_prompt,
                model=self.config.llm.primary,  # DeepSeek V3
                temperature=0.1  # Low temperature for classification accuracy
            )

            # Parse JSON response
            import json
            import re

            # Remove markdown code blocks if present
            response = response.strip()
            if response.startswith('```'):
                response = re.sub(r'```json\n?', '', response)
                response = re.sub(r'```\n?', '', response)

            result = json.loads(response)

            # Add metadata
            result["classified_at"] = datetime.now().isoformat()
            result["classification_system"] = "UDC"

            return result

        except json.JSONDecodeError as e:
            return {
                "error": f"Failed to parse LLM response: {e}",
                "raw_response": response,
                "confidence": "low",
                "classification_system": "UDC"
            }
        except Exception as e:
            return {
                "error": f"Classification failed: {e}",
                "confidence": "low",
                "classification_system": "UDC"
            }

    def classify_paper(
        self,
        title: str,
        authors: Optional[list] = None,
        abstract: Optional[str] = None,
        journal: Optional[str] = None,
        year: Optional[int] = None,
        summary: Optional[str] = None,
    ) -> Dict:
        """
        Classify an academic paper using UDC.

        Args:
            title: Paper title
            authors: List of author names
            abstract: Paper abstract
            journal: Journal name
            year: Publication year
            summary: AI-generated summary if available

        Returns:
            Dictionary with classification results
        """
        # Build metadata description
        metadata_parts = [f"Title: {title}"]

        if authors:
            authors_str = ", ".join(authors[:3])  # First 3 authors
            if len(authors) > 3:
                authors_str += " et al."
            metadata_parts.append(f"Authors: {authors_str}")

        if journal:
            metadata_parts.append(f"Journal: {journal}")
        if year:
            metadata_parts.append(f"Year: {year}")
        if abstract:
            metadata_parts.append(f"Abstract: {abstract}")
        if summary:
            metadata_parts.append(f"Summary: {summary}")

        metadata = "\n".join(metadata_parts)

        # Use same system prompt but adjust user prompt
        system_prompt = """You are a professional librarian expert in the Universal Decimal Classification (UDC) system.

UDC is used for classifying academic papers in library catalogs. Focus on the scientific discipline and specific subfield.

Key science UDC classes:
51 - Mathematics
52 - Astronomy
53 - Physics
54 - Chemistry
55 - Geology (55.1 Petrology, 550.8 Geostatistics, etc.)
56 - Paleontology
57 - Biological sciences
61 - Medicine
62 - Engineering
63 - Agriculture

Use specific subdivision numbers for precision."""

        user_prompt = f"""Classify this academic paper using UDC notation.

Paper metadata:
{metadata}

Return ONLY valid JSON (no markdown):
{{
  "udc_number": "UDC classification number",
  "udc_label": "subject label",
  "alternative_numbers": ["other possible UDC numbers"],
  "confidence": "high" | "medium" | "low",
  "reasoning": "brief explanation"
}}"""

        try:
            response = self.llm_client.simple_prompt(
                prompt=user_prompt,
                system=system_prompt,
                model=self.config.llm.primary,
                temperature=0.1
            )

            import json
            import re

            response = response.strip()
            if response.startswith('```'):
                response = re.sub(r'```json\n?', '', response)
                response = re.sub(r'```\n?', '', response)

            result = json.loads(response)
            result["classified_at"] = datetime.now().isoformat()
            result["classification_system"] = "UDC"

            return result

        except Exception as e:
            return {
                "error": f"Classification failed: {e}",
                "confidence": "low",
                "classification_system": "UDC"
            }
