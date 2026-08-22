import pathlib
from abc import ABC, abstractmethod
from typing import Any, Dict


class ResumeParser(ABC):
    """Abstract base class for resume parsing strategies."""

    @abstractmethod
    def extract_text(self, file_path: pathlib.Path) -> str:
        """
        Extracts raw text from the resume file.

        Args:
            file_path (pathlib.Path): Path to the resume file.

        Returns:
            str: The extracted raw text.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file format is unsupported.
        """
        pass

    @abstractmethod
    def parse(self, file_path: pathlib.Path) -> Dict[str, Any]:
        """
        Parses the resume into a structured dictionary.

        This method usually calls extract_text() internally and then
        processes the text (e.g., using regex or LLM).

        Args:
            file_path (pathlib.Path): Path to the resume file.

        Returns:
            Dict[str, Any]: Structured resume data (e.g., {'text': ..., 'skills': [...]})
        """
        pass
