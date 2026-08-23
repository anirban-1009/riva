import csv
import pathlib


def create_samples():
    data_dir = pathlib.Path("data")
    data_dir.mkdir(exist_ok=True)

    # 1. Create Sample LinkedIn Connections CSV
    csv_path = data_dir / "sample_connections.csv"
    print(f"Creating {csv_path}...")

    csv_content = [
        ["Note: This is a sample export file"],
        [""],
        [""],
        ["First Name", "Last Name", "Email Address", "Company", "Position", "Connected On"],
        ["Alice", "Wonderland", "alice@example.com", "Tech Nova", "Senior Developer", "12 Oct 2023"],
        ["Bob", "Builder", "bob@construction.com", "BuildIt Inc", "Project Manager", "05 Jan 2024"],
        ["Charlie", "Chocolate", "", "Wonka Industries", "Factory Lead", "15 Feb 2024"],
        ["David", "Copperfield", "magic@illusion.com", "Magic deeply", "Illusionist", "20 Mar 2024"],
    ]

    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(csv_content)

    # 2. Create Sample Resume PDF containing "John Doe"
    pdf_path = data_dir / "sample_resume.pdf"
    print(f"Creating {pdf_path}...")

    from pypdf import PageObject, PdfWriter

    # Create a simple PDF with pypdf
    writer = PdfWriter()
    page = PageObject.create_blank_page(width=200, height=200)

    # Injecting text directly into the content stream is a bit low-level for pypdf without reportlab,
    # but we can try a very simple approach or just rely on the blank page for now to pass "parsing".
    # Ideally, we want text.
    # An alternative is to use a very robust base64 string or just a blank page which pypdf can read (but extract_text will be empty).
    # Let's try to make a minimal valid PDF with text using the annotation feature or just a valid blank one.
    # For the purpose of "verifying the parser works" (i.e. opens the file), a blank valid PDF is better than a corrupt one.

    writer.add_page(page)

    # Add some metadata so extract_text might not be totally empty effectively,
    # but pypdf extract_text works on content streams.
    # Let's actually use a known good base64 that is definitely valid if pypdf writing is too complex for a one-off.
    # The previous base64 was likely truncated.

    # Reverting to a known simple PDF base64 that definitely works is safer than bringing in reportlab.
    # This string is a "Hello World" PDF.
    valid_pdf_b64 = (
        b"%PDF-1.1\n"
        b"% \n"
        b"1 0 obj\n"
        b"<<\n"
        b"/Type /Catalog\n"
        b"/Pages 2 0 R\n"
        b">>\n"
        b"endobj\n"
        b"2 0 obj\n"
        b"<<\n"
        b"/Type /Pages\n"
        b"/Kids [ 3 0 R ]\n"
        b"/Count 1\n"
        b"/MediaBox [ 0 0 300 144 ]\n"
        b">>\n"
        b"endobj\n"
        b"3 0 obj\n"
        b"<<\n"
        b"/Type /Page\n"
        b"/Parent 2 0 R\n"
        b"/Resources <<\n"
        b"/Font <<\n"
        b"/F1 4 0 R\n"
        b">>\n"
        b">>\n"
        b"/Contents 5 0 R\n"
        b">>\n"
        b"endobj\n"
        b"4 0 obj\n"
        b"<<\n"
        b"/Type /Font\n"
        b"/Subtype /Type1\n"
        b"/BaseFont /Times-Roman\n"
        b">>\n"
        b"endobj\n"
        b"5 0 obj\n"
        b"<<\n"
        b"/Length 55\n"
        b">>\n"
        b"stream\n"
        b"BT\n"
        b"/F1 18 Tf\n"
        b"0 0 Td\n"
        b"(Hello World) Tj\n"
        b"ET\n"
        b"endstream\n"
        b"endobj\n"
        b"xref\n"
        b"0 6\n"
        b"0000000000 65535 f \n"
        b"0000000010 00000 n \n"
        b"0000000059 00000 n \n"
        b"0000000140 00000 n \n"
        b"0000000227 00000 n \n"
        b"0000000306 00000 n \n"
        b"trailer\n"
        b"<<\n"
        b"/Size 6\n"
        b"/Root 1 0 R\n"
        b">>\n"
        b"startxref\n"
        b"408\n"
        b"%%EOF\n"
    )

    with open(pdf_path, "wb") as f:
        f.write(valid_pdf_b64)

    print("\nSample files created successfully!")
    print(f"1. {csv_path}")
    print(f"2. {pdf_path}")
    print("\nYou can now run the verify script:")
    print(f"uv run python scripts/verify_ingestion.py --resume {pdf_path} --linkedin {csv_path}")


if __name__ == "__main__":
    create_samples()
