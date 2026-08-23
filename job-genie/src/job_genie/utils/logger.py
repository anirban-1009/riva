import logging
import sys
from pathlib import Path
from typing import ClassVar

from colorama import Fore, Style


class ColoredFormatter(logging.Formatter):
    """Custom formatter for colored console output."""

    TIME_PREFIX = Fore.BLACK + Style.BRIGHT + "%(asctime)s" + Style.RESET_ALL + " "

    FORMATS: ClassVar[dict[int, str]] = {
        logging.DEBUG: TIME_PREFIX + Fore.CYAN + "%(levelname)s" + Style.RESET_ALL + ": %(message)s",
        logging.INFO: TIME_PREFIX + Fore.GREEN + "%(levelname)s" + Style.RESET_ALL + ": %(message)s",
        logging.WARNING: TIME_PREFIX + Fore.YELLOW + "%(levelname)s" + Style.RESET_ALL + ": %(message)s",
        logging.ERROR: TIME_PREFIX + Fore.RED + "%(levelname)s" + Style.RESET_ALL + ": %(message)s",
        logging.CRITICAL: TIME_PREFIX + Fore.RED + Style.BRIGHT + "%(levelname)s" + Style.RESET_ALL + ": %(message)s",
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt="%H:%M:%S")
        return formatter.format(record)


def setup_logging(log_file: str = "logs/mindmap.log", level=logging.INFO):
    """
    Configures the root logger for the application.
    """
    # Create logs directory
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Get root logger
    logger = logging.getLogger()
    logger.setLevel(level)

    # Remove existing handlers to avoid duplicates
    if logger.hasHandlers():
        logger.handlers.clear()

    # Console Handler (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColoredFormatter())
    logger.addHandler(console_handler)

    # File Handler
    file_handler = logging.FileHandler(log_path)
    file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Suppress noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Helper to get a logger for a specific module."""
    return logging.getLogger(name)
