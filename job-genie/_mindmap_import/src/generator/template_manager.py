import json
import pathlib
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader

from src.core.network_graph import Connection
from src.core.relevance_scorer import ScoringResult
from src.ingest.job_details_extractor import JobDetails
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _yaml_scalar(value: Any) -> str:
    """Renders a value as a safely-quoted YAML scalar for use in frontmatter."""
    if value is None or value == "":
        return "null"
    return json.dumps(str(value))


def _code_fence(text: Optional[str]) -> str:
    """Picks a backtick fence long enough that it can't be closed early by a run of backticks
    already inside `text` (Markdown fenced code blocks end at the first line of >= as many
    backticks as the opener)."""
    longest_run = 0
    current_run = 0
    for char in text or "":
        if char == "`":
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0
    return "`" * max(3, longest_run + 1)


class TemplateManager:
    """Manages Jinja2 templates for Obsidian file generation."""

    def __init__(self, templates_dir: Optional[pathlib.Path] = None):
        """
        Initialize the TemplateManager.

        Args:
            templates_dir: Directory containing Jinja2 templates.
        """
        if templates_dir is None:
            # Default to src/generator/templates
            current_dir = pathlib.Path(__file__).parent
            self.templates_dir = current_dir / "templates"
        else:
            self.templates_dir = templates_dir

        if not self.templates_dir.exists():
            raise FileNotFoundError(f"Templates directory not found: {self.templates_dir}")

        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.filters["yaml"] = _yaml_scalar

    def render_job(
        self,
        job: JobDetails,
        score: ScoringResult,
        specialization: str = "General",
        people: Optional[List[Dict[str, str]]] = None,
        referrals: Optional[List[Dict[str, Any]]] = None,
        resume_data: Optional[Dict[str, Any]] = None,
        status: str = "ToApply",
        applied_at: Optional[str] = None,
        poc_name: str = "",
        poc_link: str = "",
    ) -> str:
        """
        Renders the Job.md template.

        Args:
            job: JobDetails object.
            score: ScoringResult object.
            specialization: Job specialization tag.
            people: List of person dictionaries (name, filename, title).
            referrals: List of referral request dictionaries.
            resume_data: Dictionary containing candidate's resume data.
            status: Display value for the job's application status (e.g. "ToApply", "Applied").
            applied_at: Timestamp the job was marked "Applied", if any.
            poc_name: Name of the LinkedIn POC the user sent a connection request to for this
                job. Carried forward from the existing note, since this is authored in Obsidian
                rather than tracked in the database.
            poc_link: LinkedIn profile URL for `poc_name`.

        Returns:
            Rendered Markdown string.
        """
        people = people or []
        referrals = referrals or []
        resume_data = resume_data or {}
        template = self.env.get_template("Job.md.j2")
        return template.render(
            job=job,
            score=score,
            specialization=specialization,
            people=people,
            referrals=referrals,
            resume=resume_data,
            status=status,
            applied_at=applied_at,
            poc_name=poc_name,
            poc_link=poc_link,
            description_fence=_code_fence(job.description),
        )

    def render_company(
        self,
        name: str,
        industry: str = "Unknown",
        location: str = "Unknown",
        website: str = "",
        jobs: Optional[List[Dict[str, str]]] = None,
        people: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        Renders the Company.md template.

        Args:
            name: Company name.
            industry: Industry name.
            location: Company location.
            website: Company website URL.
            jobs: List of job dictionaries (title, filename, status).
            people: List of person dictionaries (name, filename, title).

        Returns:
            Rendered Markdown string.
        """
        jobs = jobs or []
        people = people or []
        template = self.env.get_template("Company.md.j2")
        return template.render(
            name=name,
            industry=industry,
            location=location,
            website=website,
            jobs=jobs,
            people=people,
        )

    def render_person(
        self,
        person: Connection,
        jobs: Optional[List[Dict[str, str]]] = None,
        referrals: Optional[List[Dict[str, Any]]] = None,
        resume_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Renders the Person.md template.

        Args:
            person: Connection object.
            jobs: List of job dictionaries (title, filename, status).
            referrals: List of referral request dictionaries.
            resume_data: Dictionary containing candidate's resume data.

        Returns:
            Rendered Markdown string.
        """
        jobs = jobs or []
        referrals = referrals or []
        resume_data = resume_data or {}
        template = self.env.get_template("Person.md.j2")
        return template.render(person=person, jobs=jobs, referrals=referrals, resume=resume_data)

    def render_gap_analysis(self, report: Any, min_score: int, tag: Optional[str] = None) -> str:
        """
        Renders the GapAnalysis.md template.

        Args:
            report: GapAnalysisResult object.
            min_score: Minimum score used for analysis.
            tag: Optional tag filter used.

        Returns:
            Rendered Markdown string.
        """
        import datetime

        template = self.env.get_template("GapAnalysis.md.j2")
        return template.render(
            report=report,
            min_score=min_score,
            tag=tag,
            generated_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
