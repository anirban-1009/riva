from unittest.mock import MagicMock, patch

import pytest

from src.core.network_graph import Connection
from src.core.referral_service import ReferralService
from src.ingest.job_details_extractor import JobDetails


class TestReferralService:
    @pytest.fixture
    def mock_llm(self):
        return MagicMock()

    @pytest.fixture
    def referral_service(self, mock_llm):
        config = {"user": {"linkedin_connections_path": "dummy.csv"}}
        with patch("src.core.referral_service.NetworkGraphBuilder"):
            return ReferralService(mock_llm, config)

    def test_find_potential_connections(self, referral_service):
        job = MagicMock(spec=JobDetails)
        job.company = "Google"

        mock_conn = Connection(
            first_name="Alice", last_name="Smith", position="Engineer", company="Google", connected_on="2023-01-01"
        )

        with patch("src.core.referral_service.NetworkGraphBuilder") as mock_builder_cls:
            mock_builder = mock_builder_cls.return_value
            mock_builder.find_matches.return_value = [mock_conn]

            with patch("pathlib.Path.exists", return_value=True):
                matches = referral_service.find_potential_connections(job)
                assert len(matches) == 1
                assert matches[0].full_name == "Alice Smith"

    def test_generate_message(self, referral_service):
        job = MagicMock(spec=JobDetails)
        job.title = "AI Engineer"
        job.company = "Google"

        conn = Connection(
            first_name="Alice", last_name="Smith", position="Engineer", company="Google", connected_on="2023-01-01"
        )

        referral_service.llm.generate.return_value = "Hi Alice, refer me please."

        resume_data = {"first_name": "Anirban", "last_name": "Sikdar", "skills": {"Languages": ["Python"]}}

        message = referral_service.generate_message(job, conn, resume_data)
        assert "Hi Alice" in message
        referral_service.llm.generate.assert_called_once()

    def test_generate_message_exceeds_max_chars_warning(self, referral_service):
        """Test that a long message triggers a warning log (but is no longer truncated)."""
        job = MagicMock(spec=JobDetails)
        job.title = "Engineer"
        job.company = "Co"
        conn = MagicMock()
        conn.full_name = "Alice Smith"

        long_message = "A" * 400
        referral_service.llm.generate.return_value = long_message

        with patch("src.core.referral_service.logger") as mock_logger:
            message = referral_service.generate_message(job, conn, {}, max_chars=300)
            assert len(message) == 400
            mock_logger.warning.assert_called()

    def test_generate_message_extracts_role_from_experience(self, referral_service):
        """Test fallback role extraction when job_title is missing in resume."""
        job = MagicMock(spec=JobDetails)
        job.title = "Engineer"
        job.company = "Co"
        conn = MagicMock()
        conn.full_name = "Alice Smith"

        # Missing job_title, but has experience
        resume_data = {"experience": [{"title": "Senior ML Engineer", "company": "OldCo"}]}
        referral_service.llm.generate.return_value = "Hi"

        referral_service.generate_message(job, conn, resume_data)

        # Verify prompt contains the extracted role
        call_args = referral_service.llm.generate.call_args[0][0]
        assert "Senior ML Engineer" in call_args

    def test_save_referral_no_db(self, referral_service):
        """Test save_referral returns False if DB is not available."""
        referral_service.db = None
        res = referral_service.save_referral("123", "Alice", "Hi")
        assert res is False
