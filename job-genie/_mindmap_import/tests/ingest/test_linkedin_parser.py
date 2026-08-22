import pathlib

import pytest

from src.ingest.linkedin_parser import LinkedInParser
from src.utils.exceptions import LinkedInDataError


class TestLinkedInParser:
    @pytest.fixture
    def mock_csv_file(self, tmp_path):
        """Creates a temporary CSV file mimicking LinkedIn export structure."""

        # LinkedIn export usually has some metadata at the top
        content = """Note: This is a sample
        
        First Name,Last Name,Email Address,Company,Position,Connected On
        John,Doe,john@example.com,Tech Corp,Software Engineer,12 Dec 2023
        Jane,Smith,,StartUp Inc,CTO,10 Jan 2024
        
        """
        file_path = tmp_path / "Connections.csv"
        file_path.write_text(content, encoding="utf-8")
        return file_path

    @pytest.fixture
    def invalid_csv_file(self, tmp_path):
        """Creates an invalid CSV file."""
        file_path = tmp_path / "Invalid.csv"
        file_path.write_text("Some random text", encoding="utf-8")
        return file_path

    def test_parse_connections_success(self, mock_csv_file):
        """Test successful parsing of a valid LinkedIn connections file."""
        parser = LinkedInParser(mock_csv_file)
        # Mocking pd.read_csv to return the expected DataFrame structure,
        # or relying on the file content.
        # Since the file content is structured to simulate the skip behavior:
        # We need to ensure LinkedInParser logic handles the skip correctly.

        # Let's adjust the mock CSV to actually work with the parser logic
        # The parser tries `skiprows=3`.

        content = """Note: This is a sample
Some other line
And another line
First Name,Last Name,Email Address,Company,Position,Connected On
John,Doe,john@example.com,Tech Corp,Software Engineer,12 Dec 2023
Jane,Smith,,StartUp Inc,CTO,10 Jan 2024
"""
        mock_csv_file.write_text(content, encoding="utf-8")

        connections = parser.parse_connections()

        assert len(connections) == 2
        assert connections[0]["first_name"] == "John"
        assert connections[0]["company"] == "Tech Corp"
        assert connections[1]["last_name"] == "Smith"

    def test_parse_connections_file_not_found(self):
        """Test valid file path requirement."""
        with pytest.raises(LinkedInDataError):
            parser = LinkedInParser(pathlib.Path("nonexistent.csv"))
            parser.parse_connections()

    def test_parse_connections_invalid_format(self, invalid_csv_file):
        """Test handling of invalid CSV format."""
        parser = LinkedInParser(invalid_csv_file)
        with pytest.raises(LinkedInDataError, match="Invalid LinkedIn Connections CSV format"):
            parser.parse_connections()  # Will fail inside logic

    def test_get_companies(self, mock_csv_file):
        """Test extraction of unique companies."""

        content = """Note: This is a sample
Some other line
And another line
First Name,Last Name,Email Address,Company,Position,Connected On
John,Doe,,Tech Corp,Dev,12 Dec 2023
Jane,Smith,,StartUp Inc,CTO,10 Jan 2024
Bob,Builder,,Tech Corp,Manager,15 Jan 2024
"""
        mock_csv_file.write_text(content, encoding="utf-8")

        parser = LinkedInParser(mock_csv_file)
        companies = parser.get_companies()

        assert len(companies) == 2
        assert "Tech Corp" in companies
        assert "StartUp" in companies

    def test_normalize_company(self, mock_csv_file):
        """Test company name normalization."""
        parser = LinkedInParser(mock_csv_file)

        # Test basic whitespace
        assert parser._normalize_company("  Google  ") == "Google"

        # Test suffix removal
        assert parser._normalize_company("OpenAI Inc.") == "OpenAI"
        assert parser._normalize_company("OpenAI, Inc.") == "OpenAI"
        assert parser._normalize_company("Example LLC") == "Example"
        assert parser._normalize_company("Example L.L.C.") == "Example"
        assert parser._normalize_company("Global Ltd.") == "Global"

        # Test mixed case
        assert parser._normalize_company("STARTUP pvt ltd") == "STARTUP"

        # Test no suffix
        assert parser._normalize_company("Microsoft") == "Microsoft"
