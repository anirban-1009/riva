from unittest.mock import MagicMock, patch

from src.notification.email_service import EmailService
from src.utils.logger import setup_logging


def verify_email_digest():
    setup_logging()

    config = {
        "notifications": {
            "email": {
                "enabled": True,
                "smtp_server": "smtp.gmail.com",
                "smtp_port": 587,
                "smtp_user": "sender@gmail.com",
                "smtp_password": "dummy_password",
            }
        },
        "user": {"email": "recipient@example.com", "full_name": "Antigravity Explorer"},
    }

    # Mock jobs
    scored_jobs = [
        {
            "job": MagicMock(
                title="AI Research Engineer",
                company="DeepMind",
                location="London, UK",
                link="https://deepmind.google/jobs/123",
            ),
            "score": MagicMock(
                score=92,
                key_matches=["Transformers", "PyTorch", "Reinforcement Learning"],
                reasoning="Your background in agentic architectures matches their core needs perfectly.",
            ),
        },
        {
            "job": MagicMock(
                title="Backend Developer", company="GitHub", location="Remote", link="https://github.com/jobs/456"
            ),
            "score": MagicMock(
                score=78,
                key_matches=["Python", "PostgreSQL", "CI/CD"],
                reasoning="Solid match for backend skills, though missing some Go experience requested.",
            ),
        },
    ]

    service = EmailService(config)

    print("--- Verifying Email Digest Generation ---")

    # We mock smtplib.SMTP to avoid actually sending but capture the rendered output
    with patch("smtplib.SMTP") as mock_smtp:
        # Success case
        result = service.send_job_digest(scored_jobs)

        if result:
            print("SUCCESS: send_job_digest logical flow completed.")
            # Check the rendered content from the mock
            args, _ = mock_smtp.return_value.__enter__.return_value.send_message.call_args
            msg = args[0]

            # The message is MIMEMultipart, we want the HTML part
            html_part = None
            for part in msg.walk():
                if part.get_content_type() == "text/html":
                    html_part = part.get_payload(decode=True).decode()
                    break

            if html_part:
                print("\nCaptured Rendered HTML Content (truncated):")
                print("-" * 40)
                # Print first 500 chars
                print(html_part[:500] + "...")
                print("-" * 40)

                # Save to a file for manual inspection if needed
                output_path = "output/test_digest.html"
                with open(output_path, "w") as f:
                    f.write(html_part)
                print(f"Full HTML digest saved to: {output_path}")
            else:
                print("FAILURE: Could not find HTML part in the message.")
        else:
            print("FAILURE: send_job_digest returned False.")


if __name__ == "__main__":
    verify_email_digest()
