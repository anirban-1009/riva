from pathlib import Path

import pytest

from src.generator.vault_manager import VaultManager


class TestVaultManager:
    @pytest.fixture
    def config(self, tmp_path):
        return {
            "obsidian": {
                "vault_path": str(tmp_path / "test_vault"),
                "folders": {"jobs": "Jobs", "companies": "Companies"},
            }
        }

    def test_init_creates_vault_path(self, config):
        """Test that initializing VaultManager creates the vault directory."""
        vault_path = Path(config["obsidian"]["vault_path"])
        assert not vault_path.exists()

        manager = VaultManager(config)

        assert vault_path.exists()
        assert manager.vault_path == vault_path

    def test_ensure_folders_exist(self, config):
        """Test that ensure_folders_exist creates subfolders."""
        manager = VaultManager(config)
        manager.ensure_folders_exist()

        vault_path = Path(config["obsidian"]["vault_path"])
        assert (vault_path / "Jobs").exists()
        assert (vault_path / "Companies").exists()

    def test_write_file_success(self, config):
        """Test writing a file to a valid folder."""
        manager = VaultManager(config)
        content = "# Test Job"
        filename = "test_job.md"

        file_path = manager.write_file(content, filename, "jobs")

        expected_path = Path(config["obsidian"]["vault_path"]) / "Jobs" / "test_job.md"
        assert file_path == expected_path
        assert expected_path.exists()
        assert expected_path.read_text(encoding="utf-8") == content

    def test_write_file_invalid_key(self, config):
        """Test write_file raises ValueError for invalid folder key."""
        manager = VaultManager(config)

        with pytest.raises(ValueError, match="Folder key 'invalid' not found"):
            manager.write_file("content", "file.md", "invalid")

    def test_file_exists(self, config):
        """Test file_exists check."""
        manager = VaultManager(config)
        manager.write_file("content", "exist.md", "jobs")

        assert manager.file_exists("exist.md", "jobs")
        assert not manager.file_exists("non_existent.md", "jobs")
        assert not manager.file_exists("exist.md", "companies")

    def test_sanitize_filename(self, config):
        """Test filename sanitization."""
        manager = VaultManager(config)

        dirty_name = "Job: Title / with | chars?"
        clean = manager._sanitize_filename(dirty_name)

        assert ":" not in clean
        assert "/" not in clean
        assert "|" not in clean
        assert "?" not in clean
        assert clean == "Job_ Title _ with _ chars_"
