"""Dewey Decimal Classification system classifier using DeepSeek V3."""

from datetime import datetime
from pathlib import Path
from typing import Dict, Optional
import re

from holocene.llm import NanoGPTClient
from holocene.config import load_config
from holocene.storage.database import Database


def generate_cutter_number(author_name: str, length: int = 3) -> str:
    """
    Generate a Cutter number for an author's last name.

    This is a simplified Cutter-Sanborn algorithm.
    Real libraries use detailed tables, but this provides reasonable approximations.

    Args:
        author_name: Author's name (will extract last name)
        length: Desired length of Cutter number (2-4, typically 3)

    Returns:
        Cutter number (e.g., "I73" for Isaaks)
    """
    if not author_name:
        return "A00"

    # Extract last name (handle "Last, First" or "First Last" formats)
    if ',' in author_name:
        last_name = author_name.split(',')[0].strip()
    else:
        parts = author_name.strip().split()
        last_name = parts[-1] if parts else author_name

    # Remove any non-letter characters
    last_name = re.sub(r'[^A-Za-z]', '', last_name)
    if not last_name:
        return "A00"

    last_name = last_name.upper()
    first_letter = last_name[0]

    # Simplified Cutter algorithm - assign base numbers by first letter
    # This is a very simplified version of the Cutter-Sanborn tables
    letter_bases = {
        'A': 1, 'B': 20, 'C': 30, 'D': 40, 'E': 50, 'F': 60, 'G': 70,
        'H': 80, 'I': 90, 'J': 95, 'K': 100, 'L': 120, 'M': 140,
        'N': 160, 'O': 170, 'P': 180, 'Q': 200, 'R': 210, 'S': 230,
        'T': 250, 'U': 270, 'V': 280, 'W': 290, 'X': 300, 'Y': 310, 'Z': 320
    }

    base = letter_bases.get(first_letter, 1)

    # Add variation based on second/third letters if available
    if len(last_name) > 1:
        second_letter = last_name[1]
        # Add small offset based on second letter (0-19)
        second_offset = (ord(second_letter) - ord('A')) % 20
        base += second_offset

    # Format as letter + number
    number = str(base).zfill(2)

    # Truncate or pad to desired length
    if length == 2:
        cutter = f"{first_letter}{number[:1]}"
    elif length == 3:
        cutter = f"{first_letter}{number[:2]}"
    else:  # length == 4
        cutter = f"{first_letter}{number}"

    return cutter


class DeweyClassifier:
    """Classify books and papers using Dewey Decimal Classification."""

    def __init__(self, config_path: Path = None):
        """
        Initialize Dewey classifier.

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
        Classify a book using Dewey Decimal Classification.

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

        system_prompt = """You are a professional librarian expert in the Dewey Decimal Classification (DDC) system.

DDC is the world's most widely used library classification system, particularly strong in sciences and technical subjects.

Key Dewey main classes:
000 - Computer science, information & general works
100 - Philosophy & psychology
200 - Religion
300 - Social sciences
400 - Language
500 - Science
  510 - Mathematics
  520 - Astronomy
  530 - Physics
  540 - Chemistry
  550 - Earth sciences & geology
    550.1 - Philosophy and theory
    550.182 - Mathematical geology, geostatistics
    551 - Geology, hydrology, meteorology
    552 - Petrology
    553 - Economic geology
    554-559 - Regional geology
  560 - Paleontology
  570 - Life sciences, biology
  580 - Plants (botany)
  590 - Animals (zoology)
600 - Technology
  610 - Medicine & health
  620 - Engineering
  621 - Applied physics (mechanical, electrical)
    621.9 - Tools, machining
  630 - Agriculture
  640 - Home & family management
    641.3 - Food
      641.3373 - Coffee
  650 - Management & public relations
  660 - Chemical engineering
  670 - Manufacturing
  680 - Manufacture for specific uses
  690 - Building & construction
700 - Arts & recreation
  741 - Drawing & drawings
    741.5 - Comics, graphic novels, manga
  780 - Music
  790 - Sports, games & entertainment
800 - Literature
900 - History & geography

DDC uses pure decimal notation for unlimited subdivision:
- Three digits before decimal (e.g., 550)
- Decimal point + additional precision (e.g., 550.182)
- Can go to any depth needed (e.g., 641.3373 for coffee)

Your task is to assign accurate DDC numbers to books based on their metadata."""

        user_prompt = f"""Classify this book using Dewey Decimal Classification.

Book metadata:
{metadata}

Return ONLY valid JSON (no markdown, no explanation):
{{
  "dewey_number": "primary DDC number with appropriate decimal precision",
  "dewey_label": "human-readable subject label",
  "alternative_numbers": ["other possible DDC numbers if applicable"],
  "confidence": "high" | "medium" | "low",
  "reasoning": "brief explanation of classification choice"
}}

Guidelines:
- Use appropriate decimal precision (e.g., "550.182" for geostatistics, not just "550")
- For interdisciplinary works, choose the primary focus
- Be as specific as possible while remaining accurate
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

            # Remove markdown code blocks if present
            response = response.strip()
            if response.startswith('```'):
                response = re.sub(r'```json\n?', '', response)
                response = re.sub(r'```\n?', '', response)

            result = json.loads(response)

            # Generate Cutter number if configured and author provided
            if self.config.classification.generate_cutter_numbers and author:
                cutter = generate_cutter_number(author, self.config.classification.cutter_length)
                result["cutter_number"] = cutter

                # Generate full call number if configured
                if self.config.classification.generate_full_call_numbers:
                    dewey = result["dewey_number"]

                    # Add work letter (simplified - just use first letter of title lowercased)
                    work_letter = title[0].lower() if title else "a"

                    # Format: "Dewey Cutter[work_letter]"
                    # e.g., "550.182 I73a" for "An Introduction to Applied Geostatistics" by Isaaks
                    full_call_number = f"{dewey} {cutter}{work_letter}"
                    result["call_number"] = full_call_number

            # Add metadata
            result["classified_at"] = datetime.now().isoformat()
            result["classification_system"] = "Dewey"

            return result

        except json.JSONDecodeError as e:
            return {
                "error": f"Failed to parse LLM response: {e}",
                "raw_response": response,
                "confidence": "low",
                "classification_system": "Dewey"
            }
        except Exception as e:
            return {
                "error": f"Classification failed: {e}",
                "confidence": "low",
                "classification_system": "Dewey"
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
        Classify an academic paper using Dewey.

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

        system_prompt = """You are a professional librarian expert in the Dewey Decimal Classification (DDC) system.

Focus on scientific disciplines using the 500s:
510 - Mathematics
520 - Astronomy
530 - Physics
540 - Chemistry
550 - Earth sciences (550.182 = geostatistics, 551 = geology, etc.)
560 - Paleontology
570 - Life sciences
610 - Medicine

Use appropriate decimal precision for specificity."""

        user_prompt = f"""Classify this academic paper using Dewey Decimal Classification.

Paper metadata:
{metadata}

Return ONLY valid JSON (no markdown):
{{
  "dewey_number": "DDC number",
  "dewey_label": "subject label",
  "alternative_numbers": ["other possible numbers"],
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

            response = response.strip()
            if response.startswith('```'):
                response = re.sub(r'```json\n?', '', response)
                response = re.sub(r'```\n?', '', response)

            result = json.loads(response)

            # Generate Cutter number for first author if configured
            if self.config.classification.generate_cutter_numbers and authors and len(authors) > 0:
                cutter = generate_cutter_number(authors[0], self.config.classification.cutter_length)
                result["cutter_number"] = cutter

                if self.config.classification.generate_full_call_numbers:
                    dewey = result["dewey_number"]
                    work_letter = title[0].lower() if title else "a"
                    result["call_number"] = f"{dewey} {cutter}{work_letter}"

            result["classified_at"] = datetime.now().isoformat()
            result["classification_system"] = "Dewey"

            return result

        except Exception as e:
            return {
                "error": f"Classification failed: {e}",
                "confidence": "low",
                "classification_system": "Dewey"
            }
