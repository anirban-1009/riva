from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional

from src.core.ai import LLMClient
from src.core.relevance_scorer import ScoringResult
from src.ingest.job_details_extractor import JobDetails
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class JobGapDetail:
    """Detailed missing skills for a specific job."""

    job_id: str
    title: str
    company: str
    missing_skills: List[str]


@dataclass
class GapAnalysisResult:
    """Result of the gap analysis."""

    top_missing_skills: List[str]
    skill_frequency: Dict[str, int]
    improvement_plan: str
    details: List[JobGapDetail]


class GapAnalyzer:
    """Analyzes missing skills across multiple job applications to identify learning opportunities."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    def analyze_gaps(
        self, job_results: List[tuple[JobDetails, ScoringResult]], top_n: int = 5
    ) -> Optional[GapAnalysisResult]:
        """
        Aggregates missing skills from a list of (job, result) tuples and generates an improvement plan.

        Args:
            job_results: List of (JobDetails, ScoringResult) tuples.
            top_n: Number of top missing skills to focus on.

        Returns:
            GapAnalysisResult containing aggregated data, details, and advice.
        """
        if not job_results:
            logger.warning("No results provided for gap analysis.")
            return None

        # 1. Aggregate missing skills and collect details
        all_missing_skills = []
        details = []
        for job, res in job_results:
            normalized_skills = [s.strip() for s in res.missing_skills]
            all_missing_skills.extend([s.lower() for s in normalized_skills])

            details.append(
                JobGapDetail(job_id=job.id, title=job.title, company=job.company, missing_skills=normalized_skills)
            )

        if not all_missing_skills:
            logger.info("No missing skills found in the provided results.")
            return GapAnalysisResult(
                top_missing_skills=[],
                skill_frequency={},
                improvement_plan="No major gaps identified! You are a strong candidate.",
                details=details,
            )

        # 2. Calculate Frequency
        counter = Counter(all_missing_skills)
        most_common = counter.most_common(top_n)
        top_skills = [skill for skill, count in most_common]
        frequency_dict = dict(most_common)

        # 3. Generate Improvement Plan via LLM
        plan = self._generate_improvement_plan(top_skills)

        return GapAnalysisResult(
            top_missing_skills=top_skills, skill_frequency=frequency_dict, improvement_plan=plan, details=details
        )

    def _generate_improvement_plan(self, missing_skills: List[str]) -> str:
        """Uses LLM to suggest how to close the identified skill gaps."""
        skills_str = ", ".join(missing_skills)
        prompt = f"""
        I have analyzed multiple job descriptions and identified the following recurring missing skills in my profile:
        {skills_str}

        Act as a senior career coach.
        1. Briefly explain why these skills are important in the current market.
        2. Propose a concrete, actionable learning path to acquire these skills efficiently.
        3. Suggest a project idea that would demonstrate proficiency in these areas combined.

        Keep the response concise, encouraging, and actionable.
        """

        system_instruction = "You are a pragmatic technical career coach focused on efficient upskilling."

        try:
            plan = self.llm.generate(prompt, system_instruction)
            return plan or "Could not generate improvement plan."
        except Exception as e:
            logger.error(f"Error generating improvement plan: {e}")
            return "Error generating improvement plan."
