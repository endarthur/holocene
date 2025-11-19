"""PDF metadata extraction using DeepSeek V3 via NanoGPT."""

import re
import json
from pathlib import Path
from typing import Dict, Optional
import pdfplumber

# Import is needed but may be circular, so we'll use import inside function if needed

from holocene.llm import NanoGPTClient


class PDFMetadataExtractor:
    """Extract bibliographic metadata from PDFs using LLM analysis."""

    def __init__(self, config):
        """
        Initialize PDF metadata extractor.

        Args:
            config: Holocene configuration object
        """
        self.config = config
        self.llm_client = NanoGPTClient(config.llm.api_key, config.llm.base_url)

    def extract_text(self, pdf_path: Path, max_pages: int = 5) -> str:
        """
        Extract text from first N pages of PDF.

        Args:
            pdf_path: Path to PDF file
            max_pages: Maximum number of pages to extract

        Returns:
            Extracted text with page breaks
        """
        try:
            with pdfplumber.open(pdf_path) as pdf:
                pages_text = []
                for i in range(min(max_pages, len(pdf.pages))):
                    text = pdf.pages[i].extract_text()
                    if text:
                        pages_text.append(text.strip())

                return "\n\n---PAGE BREAK---\n\n".join(pages_text)
        except Exception as e:
            raise ValueError(f"Failed to extract text from PDF: {e}")

    def extract_doi_from_text(self, text: str) -> Optional[str]:
        """
        Extract DOI from text using regex patterns.

        Args:
            text: Text to search

        Returns:
            DOI string if found, else None
        """
        # Common DOI patterns
        doi_patterns = [
            r'doi:\s*(10\.\d{4,}/[^\s]+)',  # doi: 10.xxxx/...
            r'DOI:\s*(10\.\d{4,}/[^\s]+)',  # DOI: 10.xxxx/...
            r'https?://doi\.org/(10\.\d{4,}/[^\s]+)',  # https://doi.org/10.xxxx/...
            r'https?://dx\.doi\.org/(10\.\d{4,}/[^\s]+)',  # http://dx.doi.org/10.xxxx/...
        ]

        for pattern in doi_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                doi = match.group(1)
                # Clean up DOI (remove trailing punctuation)
                doi = re.sub(r'[.,;]$', '', doi)
                return doi

        return None

    def extract_isbn_from_text(self, text: str) -> Optional[str]:
        """
        Extract ISBN from text using regex patterns.

        Args:
            text: Text to search

        Returns:
            ISBN string if found, else None
        """
        # ISBN-13 and ISBN-10 patterns
        isbn_patterns = [
            r'ISBN[-:\s]*(97[89][-\s]?\d{1,5}[-\s]?\d{1,7}[-\s]?\d{1,7}[-\s]?\d)',  # ISBN-13
            r'ISBN[-:\s]?(\d{1,5}[-\s]?\d{1,7}[-\s]?\d{1,7}[-\s]?[\dX])',  # ISBN-10
        ]

        for pattern in isbn_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                isbn = match.group(1)
                # Clean up ISBN (remove hyphens and spaces)
                isbn = re.sub(r'[-\s]', '', isbn)
                return isbn

        return None

    def extract_metadata_with_llm(
        self,
        text: str,
        doi: Optional[str] = None,
        isbn: Optional[str] = None,
        extract_summary: bool = False
    ) -> Dict:
        """
        Extract metadata using DeepSeek V3.

        Args:
            text: PDF text excerpt
            doi: Pre-extracted DOI (if found)
            isbn: Pre-extracted ISBN (if found)

        Returns:
            Dictionary with extracted metadata
        """
        # Limit text to ~10K tokens (roughly 40K characters)
        text_excerpt = text[:40000]

        system_prompt = """You are a bibliographic metadata extraction expert.
Extract metadata from PDF excerpts and return valid JSON only.
Be precise and conservative - if you're not confident, indicate low confidence."""

        # Build JSON schema based on whether summary is requested
        json_schema = """{{
  "type": "book" | "paper" | "thesis" | "report" | "unknown",
  "title": "exact title from document",
  "authors": ["First Last", "First Last"],
  "year": 2024,
  "publisher": "...",
  "journal": "...",
  "doi": "{doi or '...'}",
  "isbn": "{isbn or '...'}",
  "abstract": "brief abstract if available",
  "keywords": ["keyword1", "keyword2"],
  "confidence": "high" | "medium" | "low"""

        if extract_summary:
            json_schema += """,
  "summary": "High-quality markdown summary covering: main contribution/thesis, key methodology, major findings/arguments, and significance. Use headers (##), bullet points, and **bold** for emphasis. 2-4 paragraphs."
}}"""
        else:
            json_schema += """
}}"""

        user_prompt = f"""Extract bibliographic metadata from this PDF excerpt.

Return ONLY valid JSON (no markdown, no explanation, no code blocks):
{json_schema}

Notes:
- If DOI or ISBN was pre-extracted, verify it matches the document
- For papers: include journal name
- For books: include publisher
- For thesis: include university/institution
- Mark confidence based on clarity of metadata
- Use "unknown" for type if truly unclear"""

        if extract_summary:
            user_prompt += """
- For summary: Focus on intellectual content, not bibliographic details
- Summary should be comprehensive but concise
- Use proper markdown formatting for readability"""

        user_prompt += f"""

PDF Excerpt:
{text_excerpt}
"""

        try:
            response = self.llm_client.simple_prompt(
                prompt=user_prompt,
                system=system_prompt,
                model=self.config.llm.primary,  # DeepSeek V3
                temperature=0.1  # Low temperature for factual extraction
            )

            # Parse JSON response
            # Remove markdown code blocks if present
            response = response.strip()
            if response.startswith('```'):
                # Remove markdown code blocks
                response = re.sub(r'```json\n?', '', response)
                response = re.sub(r'```\n?', '', response)

            metadata = json.loads(response)

            return metadata

        except json.JSONDecodeError as e:
            return {
                "error": f"Failed to parse LLM response: {e}",
                "raw_response": response,
                "confidence": "low"
            }
        except Exception as e:
            return {
                "error": f"LLM extraction failed: {e}",
                "confidence": "low"
            }

    def extract_metadata(
        self,
        pdf_path: Path,
        max_pages: Optional[int] = None,
        full_text: bool = False,
        extract_summary: bool = False
    ) -> Dict:
        """
        Full metadata extraction pipeline.

        Args:
            pdf_path: Path to PDF file
            max_pages: Maximum pages to extract (default: 10 for summaries, 5 otherwise)
            full_text: Extract entire PDF instead of excerpt
            extract_summary: Request detailed summary from LLM

        Returns:
            Dictionary with extracted metadata
        """
        # Step 1: Extract text from PDF
        if full_text:
            # Extract all pages
            text = self.extract_text(pdf_path, max_pages=999999)
        else:
            # Extract first N pages (more pages if summarizing)
            if max_pages is None:
                max_pages = 15 if extract_summary else 5
            text = self.extract_text(pdf_path, max_pages=max_pages)

        # Count total pages
        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
        except Exception:
            total_pages = None

        # Step 2: Try to extract DOI and ISBN with regex
        doi = self.extract_doi_from_text(text)
        isbn = self.extract_isbn_from_text(text)

        # Step 3: Use LLM to extract full metadata
        metadata = self.extract_metadata_with_llm(
            text,
            doi=doi,
            isbn=isbn,
            extract_summary=extract_summary
        )

        # Step 4: Add file information
        metadata["source_file"] = str(pdf_path)
        metadata["extraction_method"] = "deepseek_v3"
        metadata["total_pages"] = total_pages

        # Calculate analysis_pages based on what was actually analyzed
        if full_text:
            metadata["analysis_pages"] = total_pages
        else:
            metadata["analysis_pages"] = min(max_pages, total_pages) if total_pages else max_pages

        metadata["full_text_analyzed"] = full_text

        return metadata
