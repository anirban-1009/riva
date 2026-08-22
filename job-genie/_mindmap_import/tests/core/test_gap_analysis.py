from unittest.mock import MagicMock

import pytest

from src.core.gap_analysis import GapAnalysisResult, GapAnalyzer
from src.core.relevance_scorer import ScoringResult
from src.ingest.job_details_extractor import JobDetails


class TestGapAnalyzer:
    @pytest.fixture
    def mock_llm(self):
        llm = MagicMock()
        llm.generate.return_value = "Mock Improvement Plan"
        return llm

    @pytest.fixture
    def analyzer(self, mock_llm):
        return GapAnalyzer(mock_llm)

    def test_analyze_gaps_success(self, analyzer):
        """Test gap analysis with common missing skills."""
        mock_job = MagicMock(spec=JobDetails)
        mock_job.id = "1"
        mock_job.title = "Job 1"
        mock_job.company = "Co 1"

        results = [
            (mock_job, ScoringResult(score=80, matching_skills=[], missing_skills=["Python", "AWS"], reasoning="")),
            (mock_job, ScoringResult(score=70, matching_skills=[], missing_skills=["AWS", "Docker"], reasoning="")),
            (
                mock_job,
                ScoringResult(
                    score=60, matching_skills=[], missing_skills=["Python", "Docker", "Kubernetes"], reasoning=""
                ),
            ),
        ]

        # Call the method
        analysis = analyzer.analyze_gaps(results, top_n=2)

        assert isinstance(analysis, GapAnalysisResult)

        # Verify top skills (Python: 2, AWS: 2, Docker: 2, K8s: 1)
        top_skills = analysis.top_missing_skills
        assert len(top_skills) <= 2
        assert "python" in analysis.skill_frequency
        assert analysis.skill_frequency["python"] == 2

        # Verify details
        assert len(analysis.details) == 3
        assert analysis.details[0].job_id == "1"

        # Verify LLM call
        analyzer.llm.generate.assert_called_once()
        assert analysis.improvement_plan == "Mock Improvement Plan"

    def test_analyze_gaps_empty(self, analyzer):
        """Test behavior with no results."""
        assert analyzer.analyze_gaps([]) is None

    def test_analyze_gaps_no_missing_skills(self, analyzer):
        """Test behavior when results exist but no skills are missing."""
        mock_job = MagicMock(spec=JobDetails)
        mock_job.id = "1"
        mock_job.title = "Job 1"
        mock_job.company = "Co 1"

        results = [
            (mock_job, ScoringResult(score=100, matching_skills=["All"], missing_skills=[], reasoning="Perfect match"))
        ]
        analysis = analyzer.analyze_gaps(results)

        assert analysis is not None
        assert analysis.top_missing_skills == []
        assert analysis.improvement_plan == "No major gaps identified! You are a strong candidate."
        analyzer.llm.generate.assert_not_called()
