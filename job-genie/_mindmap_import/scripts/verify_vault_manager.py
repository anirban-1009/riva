from pathlib import Path

from src.generator.vault_manager import VaultManager
from src.utils.logger import setup_logging


def verify_vault_manager():
    setup_logging()

    # 1. Simulate Configuration
    test_vault_path = Path("output/verification_vault")
    config = {
        "obsidian": {
            "vault_path": str(test_vault_path),
            "folders": {"jobs": "Jobs", "companies": "Companies", "people": "People"},
        }
    }

    print("--- Verifying VaultManager ---")
    print(f"Target Vault Path: {test_vault_path.absolute()}")

    # 2. Initialize Manager
    manager = VaultManager(config)
    print("VaultManager initialized.")

    # 3. Create Folders
    manager.ensure_folders_exist()
    if test_vault_path.exists() and (test_vault_path / "Jobs").exists():
        print("Folders created successfully.")
    else:
        print("Failed to create folders.")
        return

    # 4. Create a Job File
    job_content = "# Software Engineer at TechCorp\n\n- **Role**: Software Engineer\n- **Company**: TechCorp"
    job_file = manager.write_file(job_content, "Software Engineer.md", "jobs")

    if job_file.exists():
        print(f"Created Job File: {job_file}")
    else:
        print("Failed to create Job file.")

    # 5. Create a Company File
    company_content = "# TechCorp\n\n- **Industry**: Tech"
    company_file = manager.write_file(company_content, "TechCorp.md", "companies")

    if company_file.exists():
        print(f"Created Company File: {company_file}")
    else:
        print("Failed to create Company file.")

    # 6. Check File Existence Logic
    if manager.file_exists("Software Engineer.md", "jobs"):
        print("file_exists check passed.")
    else:
        print("file_exists check failed.")

    print("\nVerification Complete! Check the 'output/verification_vault' folder.")


if __name__ == "__main__":
    verify_vault_manager()
