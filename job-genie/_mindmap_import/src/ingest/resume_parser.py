import pathlib
from typing import Any, Dict

import pypdf
from colorama import init

from src.ingest.parsing_interface import ResumeParser
from src.utils.exceptions import ResumeParsingError
from src.utils.logger import get_logger

init(autoreset=True)
logger = get_logger(__name__)


class PDFResumeParser(ResumeParser):
    """Parses PDF resumes into structured data."""

    def extract_text(self, file_path: pathlib.Path) -> str:
        """
        Extracts raw text from a PDF file using pypdf.

        Args:
            file_path (pathlib.Path): Path to the PDF resume.

        Returns:
            str: Extracted text from all pages.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file is not a valid PDF or is encrypted.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Resume file not found: {file_path}")

        raw_text = []

        try:
            reader = pypdf.PdfReader(str(file_path))

            if reader.is_encrypted:
                # Check if we can decrypt with empty password (common for readable PDFs)
                try:
                    reader.decrypt("")
                except Exception:
                    raise ValueError("PDF is encrypted and cannot be read.")

            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    raw_text.append(text)
                else:
                    # Log warning or handle image-based PDFs (OCR TODO)
                    logger.warning(f"No text found on page {i + 1}. It might be an image.")

        except Exception as e:
            # Identify specific pypdf exceptions if needed, otherwise wrap generic ones
            if isinstance(e, (ValueError, FileNotFoundError)):
                raise e
            raise ResumeParsingError(f"Failed to parse PDF: {e}") from e

        full_text = "\n".join(raw_text)
        return full_text.strip()

    def parse(self, file_path: pathlib.Path) -> Dict[str, Any]:
        """
        Extracts text and performs basic cleaning.

        Args:
            file_path (pathlib.Path): Path to the PDF resume.

        Returns:
            Dict[str, Any]: {'text': raw_text}
        """
        text = self.extract_text(file_path)

        # Future: Add basic keyword extraction here (regex/spacy) or call LLM

        return {"text": text, "source": str(file_path), "format": "pdf"}
