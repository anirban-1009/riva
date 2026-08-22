import json
from dataclasses import asdict
from typing import Any

from job_genie.core.ai import LLMClient
from job_genie.core.gap_analysis import GapAnalyzer
from job_genie.core.relevance_scorer import RelevanceScorer, ScoringResult
from job_genie.ingest.job_details_extractor import JobDetails, JobDetailsExtractor
from job_genie.utils.logger import get_logger

logger = get_logger(__name__)


class AnalysisService:
    """Orchestrates job scoring and gap analysis."""

    def __init__(
        self,
        llm_client: LLMClient,
        user_experience_years: int | None = None,
        experience_tolerance_years: int = 0,
    ):
        """
        Initialize the AnalysisService.

        Args:
            llm_client: LLM client for analysis.
            user_experience_years: Candidate's maximum years of experience.
            experience_tolerance_years: Years above user_experience_years a job's
                stated requirement may still exceed before being auto-rejected.
        """
        self.llm = llm_client
        self.scorer = RelevanceScorer(llm_client, user_experience_years, experience_tolerance_years)
        self.gap_analyzer = GapAnalyzer(llm_client)
        self.extractor = JobDetailsExtractor(None)

    def score_job(self, job: JobDetails, resume_text: str, force: bool = False) -> ScoringResult | None:
        """Scores a single job and saves the analysis, unless already scored."""
        if not force and self.extractor.db:
            job_data = self.extractor.db.get_job(job.id)
            if job_data and job_data.get("relevance_score") is not None and job_data.get("analysis_data"):
                try:
                    data = json.loads(job_data["analysis_data"])
                    logger.info(f"Using cached analysis for job {job.id}")
                    return ScoringResult(**data)
                except Exception as e:
                    logger.warning(f"Failed to load cached analysis for job {job.id}: {e}")

        # Perform scoring if not found or forced
        result = self.scorer.score_job(resume_text, job)
        if result and self.extractor.db:
            analysis_json = json.dumps(asdict(result))
            self.extractor.db.save_analysis(job.id, result.score, analysis_json)
            if result.score == 0:
                logger.info(f"Job {job.id} scored 0 (experience filter). Marking as rejected.")
                self.extractor.db.update_job_status(job.id, "rejected")
            return result
        return result

    def score_all_cached_jobs(self, resume_text: str, force: bool = False) -> list[tuple[JobDetails, ScoringResult]]:
        """Scores all jobs found in the database that haven't been scored or need refreshing."""
        if not self.extractor.db:
            return []

        all_jobs = self.extractor.db.get_all_jobs(limit=1000)
        scored = []
        for job_data in all_jobs:
            # Reconstruct JobDetails from DB
            job = self.extractor.get_cached_job(job_data["id"])
            if job:
                result = self.score_job(job, resume_text, force=force)
                if result:
                    scored.append((job, result))
        return scored

    def run_gap_analysis(self, min_score: int, tag: str | None = None) -> Any:
        """Runs gap analysis across high-scoring jobs using database records."""
        if not self.extractor.db:
            return None

        analyses = self.extractor.db.get_all_analyses(min_score=min_score)
        results = []
        for row in analyses:
            try:
                # Reconstruct JobDetails from DB or cache
                job = self.extractor.get_cached_job(row["id"])
                if not job:
                    continue

                # Filter by tag if requested
                if tag and job.specialization != tag:
                    continue

                data = json.loads(row["analysis_data"])
                res = ScoringResult(**data)
                results.append((job, res))
            except Exception as e:
                logger.warning(f"Failed to load analysis for {row['id']}: {e}")

        if not results:
            return None

        return self.gap_analyzer.analyze_gaps(results)
