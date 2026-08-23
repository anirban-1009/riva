import json
from unittest.mock import MagicMock, patch

import pytest

from job_genie.generator.resume_tailorer import ResumeTailorer


@pytest.fixture
def mock_config():
    return {"ai": {"provider": "gemini", "gemini": {"api_key": "test_key"}}}


@pytest.fixture
def sample_resume_data():
    return {
        "first_name": "John",
        "last_name": "Doe",
        "job_title": "Software Engineer",
        "email": "john.doe@example.com",
        "professional_summary": "Experienced engineer with a focus on Python.",
        "experience": [
            {
                "dates": "2020--Present",
                "title": "Senior Developer",
                "company": "Tech Corp",
                "location": "San Francisco",
                "bullets": ["Developed Python services.", "Led a team of 5."],
            }
        ],
        "skills": {"Languages": ["Python", "JavaScript"], "Tools": ["Docker", "Git"]},
        "education": [
            {
                "dates": "2016--2020",
                "degree": "B.S. Computer Science",
                "institution": "State University",
                "location": "City, State",
                "description": "Graduated with honors.",
            }
        ],
    }


class TestResumeTailorer:
    @patch("job_genie.generator.resume_tailorer.get_llm_client")
    def test_tailor_resume(self, mock_get_llm, mock_config, sample_resume_data):
        mock_llm = MagicMock()
        mock_get_llm.return_value = mock_llm

        tailored_summary = "Expert Python developer for backend scalability."
        tailored_bullets = ["Optimized Python microservices for high throughput."]

        mock_llm.generate.return_value = json.dumps(
            {
                "professional_summary": tailored_summary,
                "experience": [{"title": "Senior Developer", "company": "Tech Corp", "bullets": tailored_bullets}],
            }
        )

        tailorer = ResumeTailorer(mock_config)
        result = tailorer.tailor_resume(sample_resume_data, "Software Engineer at HighTech")

        assert result["professional_summary"] == tailored_summary
        assert result["experience"][0]["bullets"] == tailored_bullets
        assert result["first_name"] == "John"  # Original data preserved

    @patch("job_genie.generator.resume_tailorer.get_llm_client")
    def test_generate_latex(self, mock_get_llm, mock_config, sample_resume_data):
        mock_get_llm.return_value = MagicMock()
        tailorer = ResumeTailorer(mock_config)

        latex = tailorer.generate_latex(sample_resume_data)

        assert "John" in latex
        assert "Doe" in latex
        assert "Jake Gutierrez" in latex  # Jake's Resume template author
        assert "\\documentclass[letterpaper,11pt]{article}" in latex  # Article class instead of moderncv
        assert "Senior Developer" in latex  # Job title from experience section
        assert "Tech Corp" in latex  # Company name from experience

    @patch("job_genie.generator.resume_tailorer.subprocess.run")
    @patch("job_genie.generator.resume_tailorer.get_llm_client")
    def test_compile_pdf(self, mock_get_llm, mock_run, mock_config, tmp_path):
        mock_get_llm.return_value = MagicMock()
        tailorer = ResumeTailorer(mock_config)

        # Mock subprocess successful run
        mock_run.return_value = MagicMock(returncode=0)

        # Mock file movement by creating the expected dummy file
        output_pdf = tmp_path / "tailored_resume.pdf"

        def side_effect(*args, **kwargs):
            # Create the dummy pdf that pdflatex would have made
            temp_pdf = tmp_path / "temp_compile" / "resume.pdf"
            temp_pdf.parent.mkdir(parents=True, exist_ok=True)
            temp_pdf.write_text("dummy pdf content")
            return MagicMock(returncode=0)

        mock_run.side_effect = side_effect

        result = tailorer.compile_pdf("latex content", output_pdf)

        assert result == output_pdf
        assert output_pdf.exists()
        assert mock_run.call_count == 2  # Called twice for references

    @patch("job_genie.generator.resume_tailorer.subprocess.run")
    @patch("job_genie.generator.resume_tailorer.get_llm_client")
    def test_compile_pdf_missing_binary_raises_actionable_error(self, mock_get_llm, mock_run, mock_config, tmp_path):
        mock_get_llm.return_value = MagicMock()
        tailorer = ResumeTailorer(mock_config)
        mock_run.side_effect = FileNotFoundError(2, "No such file or directory", "pdflatex")

        with pytest.raises(RuntimeError, match="pdflatex is not installed or not on PATH"):
            tailorer.compile_pdf("latex content", tmp_path / "resume.pdf")

    @patch("job_genie.generator.resume_tailorer.subprocess.run")
    @patch("job_genie.generator.resume_tailorer.get_llm_client")
    def test_compile_pdf_missing_package_raises_actionable_error(self, mock_get_llm, mock_run, mock_config, tmp_path):
        mock_get_llm.return_value = MagicMock()
        tailorer = ResumeTailorer(mock_config)
        mock_run.return_value = MagicMock(
            returncode=1, stdout="! LaTeX Error: File `titlesec.sty' not found.\n", stderr=""
        )

        with pytest.raises(RuntimeError, match="tlmgr install titlesec"):
            tailorer.compile_pdf("latex content", tmp_path / "resume.pdf")
