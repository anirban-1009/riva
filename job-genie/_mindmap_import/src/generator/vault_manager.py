from pathlib import Path
from typing import Any, Dict

from src.utils.logger import get_logger

logger = get_logger(__name__)


class VaultManager:
    """Manages file operations within the Obsidian Vault."""

    def __init__(self, config: Dict[str, Any]):
        """Initialize VaultManager with configuration.

        Args:
            config: Dictionary containing 'obsidian' configuration section.
        """
        self.config = config.get("obsidian", {})
        self.vault_path = Path(self.config.get("vault_path", "./output"))
        self.folders = self.config.get("folders", {})

        # Ensure base path exists
        if not self.vault_path.exists():
            logger.info(f"Creating vault directory: {self.vault_path}")
            self.vault_path.mkdir(parents=True, exist_ok=True)

    def ensure_folders_exist(self) -> None:
        """Create all configured subfolders in the vault if they don't exist."""
        for key, folder_name in self.folders.items():
            folder_path = self.vault_path / folder_name
            if not folder_path.exists():
                logger.info(f"Creating folder: {folder_path}")
                folder_path.mkdir(parents=True, exist_ok=True)

    def write_file(self, content: str, filename: str, folder_key: str, subfolder: str = "") -> Path:
        """Write content to a file in the specified folder (and optional subfolder).

        Args:
            content: The string content to write.
            filename: The name of the file (including extension).
            folder_key: The key in 'folders' config identifying the base folder.
            subfolder: Optional subfolder within the base folder (e.g. "ToApply").

        Returns:
            The absolute path to the written file.

        Raises:
            ValueError: If the folder_key is not found in configuration.
        """
        if folder_key not in self.folders:
            raise ValueError(f"Folder key '{folder_key}' not found in configuration.")

        folder_name = self.folders[folder_key]
        folder_path = self.vault_path / folder_name

        if subfolder:
            folder_path = folder_path / subfolder

        # Ensure the folder exists before writing
        folder_path.mkdir(parents=True, exist_ok=True)

        sanitized_filename = self._sanitize_filename(filename)
        file_path = folder_path / sanitized_filename

        logger.debug(f"Writing file: {file_path}")
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def file_exists(self, filename: str, folder_key: str) -> bool:
        """Check if a file exists in the specified folder.

        Args:
            filename: The name of the file.
            folder_key: The key in 'folders' config.

        Returns:
            True if the file exists, False otherwise.
        """
        if folder_key not in self.folders:
            return False

        folder_name = self.folders[folder_key]
        sanitized_filename = self._sanitize_filename(filename)
        file_path = self.vault_path / folder_name / sanitized_filename
        return file_path.exists()

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to be safe for file systems.

        Args:
            filename: The original filename.

        Returns:
            A clean filename string.
        """
        # Replace common illegal characters
        invalid_chars = '<>:"/\\|?*'
        clean_name = filename
        for char in invalid_chars:
            clean_name = clean_name.replace(char, "_")
        return clean_name.strip()
