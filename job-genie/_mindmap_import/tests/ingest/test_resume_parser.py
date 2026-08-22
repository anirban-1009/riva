import pytest

from src.ingest.resume_parser import PDFResumeParser
from src.utils.exceptions import ResumeParsingError


# Define a fixture for a sample PDF file path
@pytest.fixture
def sample_pdf_path(tmp_path):
    # This will create a temporary directory and return the path
    # We can create a dummy PDF file here
    pdf_file = tmp_path / "sample.pdf"

    # Create a minimal valid PDF using pypdf
    from pypdf import PageObject, PdfWriter

    writer = PdfWriter()
    page = PageObject.create_blank_page(width=100, height=100)
    # Adding text to a blank page is tricky without proper font embedding,
    # so for testing extraction, we rely on pypdf's ability to read *something*
    # or handle empty files gracefully. However, creating a truly empty PDF might not work.

    # Instead, let's just create an empty file first to test basic file handling
    # For actual text extraction, we might need a real PDF resource or mock pypdf.

    writer.add_page(page)
    with open(pdf_file, "wb") as f:
        writer.write(f)

    return pdf_file


@pytest.fixture
def non_existent_pdf_path(tmp_path):
    return tmp_path / "non_existent.pdf"


@pytest.fixture
def parser():
    return PDFResumeParser()


def test_extract_text_file_not_found(parser, non_existent_pdf_path):
    with pytest.raises(FileNotFoundError):
        parser.extract_text(non_existent_pdf_path)


def test_parse_basic_structure(parser, sample_pdf_path):
    # This test verifies that the parse method returns the expected dictionary structure
    # regardless of the PDF content (which is minimal/empty in this fixture)
    result = parser.parse(sample_pdf_path)

    assert isinstance(result, dict)
    assert "text" in result
    assert "source" in result
    assert result["source"] == str(sample_pdf_path)
    assert result["format"] == "pdf"


def test_extract_text_invalid_file(parser, tmp_path):
    # Create a file that is not a PDF
    invalid_file = tmp_path / "invalid.pdf"
    with open(invalid_file, "w") as f:
        f.write("This is not a PDF content")

    with pytest.raises(ResumeParsingError):
        parser.extract_text(invalid_file)
