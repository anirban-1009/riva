from pathlib import Path

from src.generator.resume_tailorer import ResumeTailorer
from src.utils.logger import setup_logging


def verify_resume_tailoring():
    setup_logging()

    config = {"ai": {"provider": "ollama", "ollama": {"base_url": "http://localhost:11434", "model_name": "llama3.2"}}}

    print("--- Verifying ResumeTailorer ---")
    tailorer = ResumeTailorer(config)

    sample_data = {
        "first_name": "Antigravity",
        "last_name": "AI",
        "job_title": "Senior Coding Assistant",
        "email": "anti@gravity.ai",
        "professional_summary": "Expert AI assistant specialized in complex software engineering tasks and pair programming.",
        "experience": [
            {
                "dates": "2024--Present",
                "title": "Lead Assistant",
                "company": "Google DeepMind",
                "location": "London, UK",
                "bullets": [
                    "Autonomously navigated complex codebases.",
                    "Implemented advanced tool-calling architectures.",
                    "Reduced developer friction by 40%.",
                ],
            }
        ],
        "skills": {
            "AI/ML": ["LLMs", "Tool-Calling", "RAG"],
            "Development": ["Python", "JavaScript", "Rust"],
            "DevOps": ["Docker", "K8s", "CI/CD"],
        },
        "education": [
            {
                "dates": "2023--2024",
                "degree": "Advanced Training",
                "institution": "DeepMind Academy",
                "location": "Virtual",
                "description": "Specialized in reasoning and tool use.",
            }
        ],
    }

    # 1. Generate LaTeX
    print("Generating LaTeX content...")
    latex_content = tailorer.generate_latex(sample_data)

    # 2. Compile PDF (Only if pdflatex is present)
    output_dir = Path("output/resumes")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_pdf = output_dir / "verification_resume.pdf"

    try:
        print(f"Attempting to compile PDF to {output_pdf}...")
        tailorer.compile_pdf(latex_content, output_pdf)
        if output_pdf.exists():
            print(f"SUCCESS: PDF generated at {output_pdf}")
        else:
            print("FAILURE: PDF file was not created.")
    except Exception as e:
        print(f"ERROR during PDF compilation: {e}")
        print("Note: This might be due to missing moderncv package or pdflatex issues.")


if __name__ == "__main__":
    verify_resume_tailoring()
