import json
import pathlib
from typing import Any, Dict, Optional

from src.core.ai import LLMClient
from src.ingest.resume_parser import PDFResumeParser
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ResumeService:
    """Handles resume data extraction and structured management."""

    def __init__(self, llm_client: LLMClient, resume_path: Optional[str] = None):
        """
        Initialize the ResumeService.

        Args:
            llm_client: An instance of LLMClient for AI-based structuring.
            resume_path: Default path to the resume PDF.
        """
        self.llm = llm_client
        self.resume_path = pathlib.Path(resume_path) if resume_path else None
        self.cache_path = pathlib.Path("data/resume.json")

    def get_resume_data(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Retrieves structured resume data, parsing PDF if necessary.

        Args:
            force_refresh: Whether to ignore cached JSON and re-parse PDF.

        Returns:
            Dict[str, Any]: Structured resume data.
        """
        # 1. Try cached JSON first
        if not force_refresh and self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cached resume: {e}")

        # 2. Parse PDF if available
        if self.resume_path and self.resume_path.exists():
            return self._parse_pdf_to_json()

        logger.error("No resume data found and no PDF path provided/exists.")
        return {}

    def _parse_pdf_to_json(self) -> Dict[str, Any]:
        """Parses PDF and uses LLM to structure the content."""
        try:
            logger.info(f"Parsing resume PDF from {self.resume_path}...")
            parser = PDFResumeParser()
            resume_text = parser.extract_text(self.resume_path)

            prompt = f"""
            You are a data extraction assistant. Convert the following Resume Text into a valid JSON object matching this structure:
            {{
              "first_name": "String", "last_name": "String", "email": "String", "phone": "String",
              "linkedin": "String (URL)", "github": "String (URL)", "website": "String (URL)",
              "job_title": "String", "professional_summary": "String",
              "total_experience_years": "Number (Total years of professional experience)",
              "experience": [ {{"title": "String", "company": "String", "dates": "String", "location": "String", "bullets": ["String"]}} ],
              "education": [ {{"institution": "String", "degree": "String", "dates": "String", "location": "String", "description": "String"}} ],
              "skills": {{ "Category": ["Skill"] }}
            }}
            
            RESUME TEXT:
            {resume_text[:4000]}
            
            Return ONLY valid JSON.
            """
            json_str = self.llm.generate(prompt)

            # Clean markdown blocks
            if "```json" in json_str:
                json_str = json_str.split("```json")[1].split("```")[0].strip()
            elif "```" in json_str:
                json_str = json_str.split("```")[1].split("```")[0].strip()

            resume_data = json.loads(json_str)

            # Cache the result
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(resume_data, f, indent=2)

            return resume_data

        except Exception as e:
            logger.error(f"Failed to parse PDF to JSON: {e}")
            return {}
