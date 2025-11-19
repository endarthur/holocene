"""Extended Dewey Decimal Classification with W prefix for web content.

The Extended Dewey system adds a 'W' prefix to classify web content (links, bookmarks,
marketplace favorites) separately from physical items in the collection.

Example:
- W020 - Bibliography/book marketplace listings
- W550 - Geology-related web resources
- W621.9 - Hand tools on e-commerce sites
- W380.1 - Commerce/marketplace items (general)

The W prefix indicates "web content about X" rather than "physical item X".
"""

from datetime import datetime
from typing import Dict, Optional
import re
import json

from holocene.llm import NanoGPTClient
from holocene.config import load_config
from holocene.research.dewey_classifier import generate_cutter_number


# Extended Dewey main categories for web content
WEB_CONTENT_CATEGORIES = {
    "W000": "Computer science & information",
    "W004": "Computer hardware & devices",
    "W100": "Philosophy & psychology",
    "W200": "Religion",
    "W300": "Social sciences",
    "W380": "Commerce & trade",
    "W380.1": "E-commerce & online marketplaces",
    "W400": "Language",
    "W500": "Science",
    "W510": "Mathematics",
    "W550": "Earth sciences & geology",
    "W600": "Technology & applied sciences",
    "W610": "Medicine & health",
    "W620": "Engineering",
    "W621": "Applied physics & mechanical engineering",
    "W621.9": "Tools & machining",
    "W621.38": "Electronics",
    "W630": "Agriculture",
    "W640": "Home & family",
    "W641.3": "Food",
    "W650": "Management",
    "W681": "Precision instruments",
    "W700": "Arts & recreation",
    "W741.5": "Comics & graphic novels",
    "W800": "Literature",
    "W900": "History & geography",
}


class ExtendedDeweyClassifier:
    """Classifier for web content using Extended Dewey with W prefix."""

    def __init__(self, config_path=None):
        """
        Initialize Extended Dewey classifier.

        Args:
            config_path: Optional path to config file
        """
        self.config = load_config(config_path)
        self.llm_client = NanoGPTClient(self.config.llm.api_key, self.config.llm.base_url)

    def classify_web_content(
        self,
        title: str,
        url: Optional[str] = None,
        description: Optional[str] = None,
        category: Optional[str] = None,
        content_type: str = "link",
    ) -> Dict:
        """
        Classify web content (link, bookmark, marketplace item) using Extended Dewey.

        Args:
            title: Title of the web content
            url: URL (optional)
            description: Description or summary
            category: Existing category (e.g., from Mercado Livre)
            content_type: Type of content ("link", "bookmark", "marketplace_item")

        Returns:
            Dictionary with classification results including W-prefix Dewey number
        """
        # Build metadata description
        metadata_parts = [f"Title: {title}"]
        metadata_parts.append(f"Content Type: {content_type}")

        if url:
            metadata_parts.append(f"URL: {url}")
        if description:
            metadata_parts.append(f"Description: {description}")
        if category:
            metadata_parts.append(f"Category: {category}")

        metadata = "\n".join(metadata_parts)

        system_prompt = """You are a professional librarian expert in the Extended Dewey Decimal Classification system.

Extended Dewey uses a 'W' prefix for web content (links, bookmarks, marketplace listings).
The W prefix indicates "web content ABOUT this topic" rather than the physical item itself.

Key Extended Dewey categories:
W000 - Computer science, information & general works
W004 - Computer hardware & devices
W100 - Philosophy & psychology
W200 - Religion
W300 - Social sciences
W380 - Commerce & trade
  W380.1 - E-commerce & online marketplaces (use for marketplace listings)
W400 - Language
W500 - Science
  W510 - Mathematics
  W550 - Earth sciences & geology
  W560 - Paleontology
  W570 - Life sciences
W600 - Technology & applied sciences
  W610 - Medicine & health
  W620 - Engineering
  W621 - Applied physics & mechanical engineering
    W621.9 - Tools & machining
    W621.38 - Electronics
  W630 - Agriculture
  W640 - Home & family
    W641.3 - Food
  W650 - Management
  W681 - Precision instruments
W700 - Arts & recreation
  W741.5 - Comics & graphic novels
W800 - Literature
  W020 - Bibliography & book trade (for books sold online)
W900 - History & geography

Classification guidelines:
- Marketplace items: Classify by the item's subject, not just as "commerce"
  - Book on marketplace → W020 (bibliography)
  - Tool on marketplace → W621.9 (tools)
  - Electronics → W621.38
- General e-commerce/shopping → W380.1
- Use appropriate decimal precision
- Always include the W prefix"""

        user_prompt = f"""Classify this web content using Extended Dewey Decimal Classification.

Content metadata:
{metadata}

Return ONLY valid JSON (no markdown, no explanation):
{{
  "dewey_number": "W-prefix DDC number with appropriate precision",
  "dewey_label": "human-readable subject label",
  "alternative_numbers": ["other possible W-prefix DDC numbers"],
  "confidence": "high" | "medium" | "low",
  "reasoning": "brief explanation of classification choice",
  "is_web_content": true
}}

Guidelines:
- ALWAYS start with W prefix (e.g., "W550", "W621.9", "W380.1")
- For marketplace items, classify by subject matter, not just as commerce
- Use decimal precision as needed (e.g., "W621.38" for electronics)
- Be specific while remaining accurate"""

        try:
            response = self.llm_client.simple_prompt(
                prompt=user_prompt,
                system=system_prompt,
                model=self.config.llm.primary,  # DeepSeek V3
                temperature=0.1
            )

            # Parse JSON response
            response = response.strip()
            if response.startswith('```'):
                response = re.sub(r'```json\n?', '', response)
                response = re.sub(r'```\n?', '', response)

            result = json.loads(response)

            # Ensure W prefix is present
            dewey_num = result.get("dewey_number", "W000")
            if not dewey_num.startswith("W"):
                dewey_num = f"W{dewey_num}"
                result["dewey_number"] = dewey_num

            # Extract base title/author for Cutter generation
            # For marketplace items, use simplified approach
            author = self._extract_author_from_title(title)

            if self.config.classification.generate_cutter_numbers and author:
                cutter = generate_cutter_number(author, self.config.classification.cutter_length)
                result["cutter_number"] = cutter

                if self.config.classification.generate_full_call_numbers:
                    # Format: "W-Dewey Cutter[work_letter]"
                    # e.g., "W621.9 T45a" for "Tool - Adjustable Wrench"
                    work_letter = title[0].lower() if title else "a"
                    full_call_number = f"{dewey_num} {cutter}{work_letter}"
                    result["call_number"] = full_call_number

            result["classified_at"] = datetime.now().isoformat()
            result["classification_system"] = "Extended Dewey"
            result["is_web_content"] = True

            return result

        except json.JSONDecodeError as e:
            return {
                "error": f"Failed to parse LLM response: {e}",
                "raw_response": response,
                "confidence": "low",
                "classification_system": "Extended Dewey",
                "is_web_content": True
            }
        except Exception as e:
            return {
                "error": f"Classification failed: {e}",
                "confidence": "low",
                "classification_system": "Extended Dewey",
                "is_web_content": True
            }

    def classify_marketplace_item(
        self,
        title: str,
        price: Optional[float] = None,
        category: Optional[str] = None,
        description: Optional[str] = None,
        condition: Optional[str] = None,
    ) -> Dict:
        """
        Classify a marketplace item (e.g., Mercado Livre favorite) using Extended Dewey.

        Args:
            title: Item title
            price: Item price
            category: Marketplace category
            description: Item description
            condition: "new" or "used"

        Returns:
            Dictionary with Extended Dewey classification
        """
        # Build richer description
        desc_parts = []

        if category:
            desc_parts.append(f"Category: {category}")
        if description:
            desc_parts.append(f"Description: {description}")
        if condition:
            desc_parts.append(f"Condition: {condition}")
        if price:
            desc_parts.append(f"Listed for sale")

        full_description = ". ".join(desc_parts) if desc_parts else None

        return self.classify_web_content(
            title=title,
            description=full_description,
            category=category,
            content_type="marketplace_item",
        )

    def classify_bookmark(
        self,
        title: str,
        url: str,
    ) -> Dict:
        """
        Classify a browser bookmark using Extended Dewey.

        Args:
            title: Bookmark title
            url: Bookmark URL

        Returns:
            Dictionary with Extended Dewey classification
        """
        # Try to extract context from URL
        url_context = self._extract_url_context(url)

        return self.classify_web_content(
            title=title,
            url=url,
            description=url_context,
            content_type="bookmark",
        )

    def classify_link(
        self,
        url: str,
        title: Optional[str] = None,
        context: Optional[str] = None,
    ) -> Dict:
        """
        Classify a tracked link using Extended Dewey.

        Args:
            url: Link URL
            title: Page title (if available)
            context: Context where link was found

        Returns:
            Dictionary with Extended Dewey classification
        """
        return self.classify_web_content(
            title=title or url,
            url=url,
            description=context,
            content_type="link",
        )

    def _extract_author_from_title(self, title: str) -> Optional[str]:
        """
        Extract author/brand name from title for Cutter generation.

        Examples:
        - "Book: Geostatistics by Isaaks" → "Isaaks"
        - "Tool - Adjustable Wrench - Brand XYZ" → "XYZ"
        - "Samsung Galaxy Phone" → "Samsung"

        Args:
            title: Item title

        Returns:
            Extracted author/brand or first word
        """
        if not title:
            return None

        # Look for "by Author" pattern
        by_match = re.search(r'\bby\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', title)
        if by_match:
            return by_match.group(1)

        # Look for brand names (capitalized words)
        words = title.split()
        for word in words:
            if word and word[0].isupper() and len(word) > 2:
                # Skip common words
                if word.lower() not in {'the', 'and', 'for', 'with', 'book', 'tool', 'kit'}:
                    return word

        # Default to first word
        return words[0] if words else None

    def _extract_url_context(self, url: str) -> Optional[str]:
        """
        Extract context hints from URL.

        Args:
            url: URL to analyze

        Returns:
            Context string or None
        """
        if not url:
            return None

        context_parts = []

        # Domain hints
        if 'github.com' in url:
            context_parts.append("Software repository")
        elif 'stackoverflow.com' in url:
            context_parts.append("Programming Q&A")
        elif 'wikipedia.org' in url or 'wiki' in url:
            context_parts.append("Encyclopedia/Wiki")
        elif 'arxiv.org' in url:
            context_parts.append("Academic preprint")
        elif 'amazon.com' in url or 'mercadolivre.com' in url or 'mercadolibre.com' in url:
            context_parts.append("E-commerce listing")
        elif any(blog_hint in url for blog_hint in ['blog', 'medium.com', 'substack.com']):
            context_parts.append("Blog/Article")
        elif '.edu' in url:
            context_parts.append("Educational resource")
        elif '.gov' in url:
            context_parts.append("Government resource")

        return ". ".join(context_parts) if context_parts else None
