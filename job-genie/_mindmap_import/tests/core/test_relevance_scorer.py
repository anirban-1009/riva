from unittest.mock import MagicMock

import pytest

from src.core.ai import LLMClient
from src.core.relevance_scorer import FastScorer, RelevanceScorer, ScoringResult
from src.ingest.job_details_extractor import JobDetails
from src.ingest.job_searcher import JobSearchResult


class TestRelevanceScorer:
    @pytest.fixture
    def mock_llm(self):
        return MagicMock(spec=LLMClient)

    @pytest.fixture
    def scorer(self, mock_llm):
        return RelevanceScorer(mock_llm)

    @pytest.fixture
    def sample_job(self):
        return JobDetails(
            id="123",
            title="Python Developer",
            company="Tech Co",
            location="Remote",
            description="Looking for a Python dev with FastAPI experience.",
            posted_date="1d",
            seniority_level="Mid",
            employment_type="Full-time",
            job_function="Engineering",
            industries="Software",
            link="http://link",
        )

    def test_score_job_success(self, scorer, mock_llm, sample_job):
        """Test successful scoring with valid LLM response."""
        mock_llm.generate_json.return_value = {
            "score": 85,
            "matching_skills": ["Python", "FastAPI"],
            "missing_skills": ["AWS"],
            "reasoning": "Strong match for Python and FastAPI.",
        }

        result = scorer.score_job("I know Python and FastAPI very well.", sample_job)

        assert isinstance(result, ScoringResult)
        assert result.score == 85
        assert "Python" in result.matching_skills
        assert result.reasoning == "Strong match for Python and FastAPI."
        mock_llm.generate_json.assert_called_once()

    def test_score_job_llm_failure(self, scorer, mock_llm, sample_job):
        """Test behavior when LLM returns empty or fails."""
        mock_llm.generate_json.return_value = {}

        result = scorer.score_job("Resume text", sample_job)

        assert result is None

    def test_score_job_exception(self, scorer, mock_llm, sample_job):
        """Test behavior when LLM client raises an exception."""
        mock_llm.generate_json.side_effect = Exception("API Error")

        result = scorer.score_job("Resume text", sample_job)

        assert result is None

    def test_plus_syntax_requirement_matching_candidate_years_is_not_rejected(self, mock_llm, sample_job):
        """'2+ years' means 2 or more - a candidate with exactly 2 years qualifies
        and must reach the LLM, not be killed by the regex pre-filter."""
        scorer = RelevanceScorer(mock_llm, user_experience_years=2)
        sample_job.description = "Requires 2+ years of experience with Python."
        mock_llm.generate_json.return_value = {
            "score": 80,
            "matching_skills": ["Python"],
            "missing_skills": [],
            "reasoning": "Good fit.",
        }

        result = scorer.score_job("I know Python.", sample_job)

        assert result.score == 80
        mock_llm.generate_json.assert_called_once()

    def test_plus_syntax_requirement_above_candidate_years_is_rejected(self, mock_llm, sample_job):
        """'3+ years' genuinely excludes a candidate with only 2 years."""
        scorer = RelevanceScorer(mock_llm, user_experience_years=2)
        sample_job.description = "Requires 3+ years of experience with Python."

        result = scorer.score_job("I know Python.", sample_job)

        assert result.score == 0
        mock_llm.generate_json.assert_not_called()

    def test_experience_tolerance_lets_near_miss_reach_llm(self, mock_llm, sample_job):
        """A 1-year tolerance lets a '3 years required' posting reach the LLM
        for a candidate with 2 years, instead of being auto-rejected."""
        scorer = RelevanceScorer(mock_llm, user_experience_years=2, experience_tolerance_years=1)
        sample_job.description = "Requires 3 years of experience with Python."
        mock_llm.generate_json.return_value = {
            "score": 60,
            "matching_skills": ["Python"],
            "missing_skills": [],
            "reasoning": "Plausible stretch fit.",
        }

        result = scorer.score_job("I know Python.", sample_job)

        assert result.score == 60
        mock_llm.generate_json.assert_called_once()

    def test_experience_tolerance_still_rejects_beyond_buffer(self, mock_llm, sample_job):
        """A 1-year tolerance still auto-rejects a gap larger than the buffer."""
        scorer = RelevanceScorer(mock_llm, user_experience_years=2, experience_tolerance_years=1)
        sample_job.description = "Requires 5 years of experience with Python."

        result = scorer.score_job("I know Python.", sample_job)

        assert result.score == 0
        mock_llm.generate_json.assert_not_called()


class TestExtractExperienceRegex:
    @pytest.fixture
    def scorer(self):
        return RelevanceScorer(MagicMock(spec=LLMClient))

    def test_plus_syntax(self, scorer):
        assert scorer._extract_experience_regex("5+ years of experience required") == (5, True)

    def test_range_uses_upper_bound(self, scorer):
        assert scorer._extract_experience_regex("3-5 years of experience") == (5, False)

    def test_no_years_mentioned(self, scorer):
        assert scorer._extract_experience_regex("entry level, no experience required") == (None, False)

    def test_equivalent_experience_suppresses_same_sentence_match(self, scorer):
        assert scorer._extract_experience_regex(
            "3 years of experience or equivalent required for this specific role"
        ) == (None, False)

    def test_unrelated_equivalent_experience_does_not_suppress_real_requirement(self, scorer):
        """Education boilerplate ("degree or equivalent experience") elsewhere in the
        description must not blind the filter to an explicit years requirement stated
        in a different sentence."""
        description = (
            "We are looking for a Senior Engineer with 8+ years of professional experience.\n"
            "Education: Bachelor's degree in Computer Science or equivalent experience."
        )
        assert scorer._extract_experience_regex(description) == (8, True)

    def test_score_result_empty_keywords(self):
        """Test score with empty keyword list."""
        scorer = FastScorer([])
        result = JobSearchResult(id="1", title="Python Engineer", company="A", link="", location="")
        assert scorer.score_result(result) == 0

    def test_score_result_no_matches(self):
        """Test score with no keyword matches."""
        scorer = FastScorer(["Java", "Spring"])
        result = JobSearchResult(id="1", title="Python Engineer", company="A", link="", location="")
        assert scorer.score_result(result) == 0

    def test_score_result_partial_matches(self):
        """Test score with some keyword matches."""
        scorer = FastScorer(["Python", "Django", "Cloud"])
        # Matches Python and Django
        result = JobSearchResult(id="1", title="Senior Python Django Developer", company="A", link="", location="")
        # matches = 2, total = 3 -> (2/3)*100 = 66.6 -> +20 = 86
        score = scorer.score_result(result)
        assert score == 86

    def test_score_result_full_matches(self):
        """Test score with all keywords matching."""
        scorer = FastScorer(["Python"])
        result = JobSearchResult(id="1", title="Python Developer", company="A", link="", location="")
        # matches = 1, total = 1 -> 100 -> min(100, 100+20) = 100
        assert scorer.score_result(result) == 100
