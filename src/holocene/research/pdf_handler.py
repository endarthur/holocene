"""PDF handling with text extraction and OCR fallback."""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
import io

try:
    from pypdf import PdfReader
    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

try:
    import pytesseract
    from PIL import Image
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False


class PDFHandler:
    """Handle PDF text extraction with OCR fallback."""

    def __init__(self):
        """Initialize PDF handler."""
        self.has_pypdf = HAS_PYPDF
        self.has_pdfplumber = HAS_PDFPLUMBER
        self.has_tesseract = HAS_TESSERACT

    def extract_text(self, pdf_path: Path) -> str:
        """
        Extract text from PDF.

        Tries multiple methods in order:
        1. pypdf (fast, works for text PDFs)
        2. pdfplumber (better for complex layouts)
        3. OCR fallback (if PDF is scanned)

        Args:
            pdf_path: Path to PDF file

        Returns:
            Extracted text content
        """
        # Try pypdf first (fastest)
        if self.has_pypdf:
            try:
                text = self._extract_with_pypdf(pdf_path)
                if self._is_meaningful_text(text):
                    return text
            except Exception as e:
                print(f"pypdf extraction failed: {e}")

        # Try pdfplumber (better for tables/layouts)
        if self.has_pdfplumber:
            try:
                text = self._extract_with_pdfplumber(pdf_path)
                if self._is_meaningful_text(text):
                    return text
            except Exception as e:
                print(f"pdfplumber extraction failed: {e}")

        # Fall back to OCR if available
        if self.has_tesseract:
            try:
                text = self._extract_with_ocr(pdf_path)
                return text
            except Exception as e:
                print(f"OCR extraction failed: {e}")
                return ""

        return ""

    def _extract_with_pypdf(self, pdf_path: Path) -> str:
        """Extract text using pypdf."""
        reader = PdfReader(str(pdf_path))
        text_parts = []

        for page in reader.pages:
            text_parts.append(page.extract_text())

        return "\n\n".join(text_parts)

    def _extract_with_pdfplumber(self, pdf_path: Path) -> str:
        """Extract text using pdfplumber."""
        text_parts = []

        with pdfplumber.open(str(pdf_path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)

        return "\n\n".join(text_parts)

    def _extract_with_ocr(self, pdf_path: Path) -> str:
        """Extract text using OCR (for scanned PDFs)."""
        if not self.has_tesseract:
            raise RuntimeError("Tesseract not available for OCR")

        # Convert PDF pages to images and OCR
        text_parts = []

        # Use pdfplumber to get page images
        with pdfplumber.open(str(pdf_path)) as pdf:
            for i, page in enumerate(pdf.pages):
                try:
                    # Get page as image
                    im = page.to_image(resolution=300)
                    pil_image = im.original

                    # Run OCR
                    text = pytesseract.image_to_string(pil_image)
                    text_parts.append(text)
                except Exception as e:
                    print(f"OCR failed on page {i+1}: {e}")

        return "\n\n".join(text_parts)

    def _is_meaningful_text(self, text: str, min_chars: int = 100) -> bool:
        """
        Check if extracted text is meaningful.

        Args:
            text: Extracted text
            min_chars: Minimum character threshold

        Returns:
            True if text appears meaningful
        """
        if not text:
            return False

        # Remove whitespace and check length
        cleaned = text.strip()
        if len(cleaned) < min_chars:
            return False

        # Check for actual words (not just symbols/numbers)
        words = cleaned.split()
        alpha_words = [w for w in words if any(c.isalpha() for c in w)]

        # Require at least 10% of "words" to contain letters
        if len(words) > 0 and len(alpha_words) / len(words) < 0.1:
            return False

        return True

    def extract_images(self, pdf_path: Path) -> List[Tuple[int, bytes]]:
        """
        Extract images from PDF for vision model analysis.

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of (page_number, image_bytes) tuples
        """
        images = []

        if not self.has_pypdf:
            return images

        try:
            reader = PdfReader(str(pdf_path))

            for page_num, page in enumerate(reader.pages, start=1):
                # Extract images from page
                if hasattr(page, 'images'):
                    for img_index, image in enumerate(page.images):
                        try:
                            image_data = image.data
                            images.append((page_num, image_data))
                        except Exception as e:
                            print(f"Failed to extract image {img_index} from page {page_num}: {e}")

        except Exception as e:
            print(f"Image extraction failed: {e}")

        return images

    def get_info(self, pdf_path: Path) -> Dict[str, any]:
        """
        Get PDF metadata.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Dictionary with PDF info
        """
        info = {
            "pages": 0,
            "title": None,
            "author": None,
            "subject": None,
            "creator": None,
        }

        if not self.has_pypdf:
            return info

        try:
            reader = PdfReader(str(pdf_path))
            info["pages"] = len(reader.pages)

            if reader.metadata:
                info["title"] = reader.metadata.get("/Title")
                info["author"] = reader.metadata.get("/Author")
                info["subject"] = reader.metadata.get("/Subject")
                info["creator"] = reader.metadata.get("/Creator")

        except Exception as e:
            print(f"Failed to get PDF info: {e}")

        return info

    def check_dependencies(self) -> Dict[str, bool]:
        """
        Check which PDF processing dependencies are available.

        Returns:
            Dictionary of dependency availability
        """
        return {
            "pypdf": self.has_pypdf,
            "pdfplumber": self.has_pdfplumber,
            "tesseract": self.has_tesseract,
        }
