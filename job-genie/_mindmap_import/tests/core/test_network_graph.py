import pathlib
from unittest.mock import patch

import pytest

from src.core.network_graph import NetworkGraphBuilder
from src.ingest.job_details_extractor import JobDetails


class TestNetworkGraphBuilder:
    @pytest.fixture
    def mock_connections_csv(self, tmp_path):
        return tmp_path / "Connections.csv"

    @pytest.fixture
    def metadata_path(self, tmp_path):
        return tmp_path / "metadata.json"

    @pytest.fixture
    def builder(self, mock_connections_csv, metadata_path):
        with patch("src.core.network_graph.LinkedInParser") as mock_parser_class:
            mock_parser = mock_parser_class.return_value
            mock_parser.parse_connections.return_value = [
                {
                    "first_name": "Alice",
                    "last_name": "Wonderland",
                    "company": "Tech Nova",
                    "position": "Senior Developer",
                    "connected_on": "12 Oct 2023",
                },
                {
                    "first_name": "Bob",
                    "last_name": "Builder",
                    "company": "BuildIt",
                    "position": "Project Manager",
                    "connected_on": "05 Jan 2024",
                },
            ]
            # Mock normalization helper
            mock_parser._normalize_company.side_effect = lambda x: x.replace(" Inc", "").strip()

            return NetworkGraphBuilder(mock_connections_csv, metadata_path)

    def test_find_matches(self, builder):
        """Test matching jobs with connections by company."""
        job = JobDetails(
            id="job1",
            title="SDE",
            company="Tech Nova Inc.",
            location="Remote",
            description="",
            posted_date="",
            seniority_level="",
            employment_type="",
            job_function="",
            industries="",
            link="",
        )

        matches = builder.find_matches(job)
        assert len(matches) == 1
        assert matches[0].first_name == "Alice"

    def test_update_and_save_metadata(self, builder, metadata_path):
        """Test updating connection metadata and saving to file."""
        builder.update_connection(
            "Bob",
            "Builder",
            "05 Jan 2024",
            last_contacted="2024-02-01",
            achievements=["Completed Project X"],
            notes="Interested in AI",
        )

        builder.save_metadata()

        assert metadata_path.exists()

        # New builder should load this metadata
        with patch("src.core.network_graph.LinkedInParser") as mock_parser_class:
            mock_parser = mock_parser_class.return_value
            mock_parser.parse_connections.return_value = [
                {
                    "first_name": "Bob",
                    "last_name": "Builder",
                    "company": "BuildIt",
                    "position": "Project Manager",
                    "connected_on": "05 Jan 2024",
                }
            ]
            new_builder = NetworkGraphBuilder(pathlib.Path("fake"), metadata_path)
            assert new_builder.connections[0].metadata.last_contacted == "2024-02-01"
            assert "Completed Project X" in new_builder.connections[0].metadata.achievements

    def test_find_matches_no_company(self, builder):
        """Test no matches found for job with no company."""
        job = JobDetails(
            id="job2",
            title="SDE",
            company=None,
            location="Remote",
            description="",
            posted_date="",
            seniority_level="",
            employment_type="",
            job_function="",
            industries="",
            link="",
        )
        matches = builder.find_matches(job)
        assert len(matches) == 0

    def test_find_matches_sanitized(self, builder):
        """Test matching jobs with connections using sanitized names (punctuation/case)."""
        job = JobDetails(
            id="job3",
            title="SDE",
            company="Build-It!!! ",
            location="Remote",
            description="",
            posted_date="",
            seniority_level="",
            employment_type="",
            job_function="",
            industries="",
            link="",
        )
        # 'BuildIt' was the connection company in the fixture
        matches = builder.find_matches(job)
        assert len(matches) == 1
        assert matches[0].first_name == "Bob"
