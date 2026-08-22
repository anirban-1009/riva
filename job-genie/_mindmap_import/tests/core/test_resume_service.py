import json
from unittest.mock import MagicMock, mock_open, patch

import pytest

from src.core.resume_service import ResumeService


class TestResumeService:
    @pytest.fixture
    def mock_llm(self):
        return MagicMock()

    @pytest.fixture
    def resume_service(self, mock_llm):
        return ResumeService(mock_llm, resume_path="data/resume.pdf")

    def test_get_resume_data_cache_hit(self, resume_service):
        mock_data = {"first_name": "Anirban"}
        with patch("pathlib.Path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=json.dumps(mock_data))):
                data = resume_service.get_resume_data()
                assert data == mock_data

    @patch("src.core.resume_service.PDFResumeParser")
    def test_get_resume_data_pdf_parse(self, mock_parser_cls, resume_service):
        mock_parser = mock_parser_cls.return_value
        mock_parser.extract_text.return_value = "Resume Text"

        resume_service.llm.generate.return_value = '{"first_name": "Anirban"}'

        # Mocking exists: cache doesn't exist, PDF exists
        with patch("pathlib.Path.exists") as mock_exists:
            mock_exists.side_effect = lambda: mock_exists.call_count == 2

            with patch("builtins.open", mock_open()):
                data = resume_service.get_resume_data()
                assert data["first_name"] == "Anirban"
                mock_parser.extract_text.assert_called_once()

    def test_parse_pdf_to_json_success(self, resume_service):
        resume_service.llm.generate.return_value = '```json\n{"first_name": "Anirban"}\n```'

        with patch("src.core.resume_service.PDFResumeParser") as mock_parser_cls:
            mock_parser = mock_parser_cls.return_value
            mock_parser.extract_text.return_value = "Resume Text"

            with patch("builtins.open", mock_open()):
                data = resume_service._parse_pdf_to_json()
                assert data["first_name"] == "Anirban"

    def test_get_resume_data_cache_corrupt(self, resume_service):
        """Test that get_resume_data handles corrupted cache by falling back to PDF."""
        with patch("pathlib.Path.exists", return_value=True):
            # First call for cache exists, second call for PDF exists
            with patch("builtins.open", side_effect=[Exception("Read error"), mock_open().return_value]):
                with patch.object(resume_service, "_parse_pdf_to_json") as mock_parse:
                    mock_parse.return_value = {"from": "pdf"}
                    data = resume_service.get_resume_data()
                    assert data == {"from": "pdf"}

    def test_get_resume_data_no_files(self, resume_service):
        """Test get_resume_data returns empty dict when no files exist."""
        with patch("pathlib.Path.exists", return_value=False):
            data = resume_service.get_resume_data()
            assert data == {}

    def test_parse_pdf_to_json_invalid_json(self, resume_service):
        """Test _parse_pdf_to_json returns empty dict on LLM JSON error."""
        resume_service.llm.generate.return_value = "Not JSON"
        with patch("src.core.resume_service.PDFResumeParser") as mock_parser_cls:
            mock_parser = mock_parser_cls.return_value
            mock_parser.extract_text.return_value = "Text"
            data = resume_service._parse_pdf_to_json()
            assert data == {}

    def test_parse_pdf_to_json_exception(self, resume_service):
        """Test _parse_pdf_to_json returns empty dict on parser exception."""
        with patch("src.core.resume_service.PDFResumeParser") as mock_parser_cls:
            mock_parser = mock_parser_cls.return_value
            mock_parser.extract_text.side_effect = Exception("Parser error")
            data = resume_service._parse_pdf_to_json()
            assert data == {}
