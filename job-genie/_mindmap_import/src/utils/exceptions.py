class MindMapError(Exception):
    """Base exception for all Job Hunt Mindmap errors."""

    pass


# Configuration
class ConfigError(MindMapError):
    """Raised when configuration file is invalid or missing required keys."""

    pass


# Data Ingestion
class DataSourceError(MindMapError):
    """Base exception for errors related to fetching or parsing data."""

    pass


class ResumeParsingError(DataSourceError):
    """Raised when resume parsing fails due to invalid format or content."""

    pass


class LinkedInDataError(DataSourceError):
    """Raised when LinkedIn data format is invalid or missing columns."""

    pass


class ScraperError(DataSourceError):
    """Raised when web scraping or browser automation fails."""

    pass


# Logic/AI
class AnalysisError(MindMapError):
    """Base exception for errors during data analysis or matching."""

    pass


class LLMError(AnalysisError):
    """Raised when the LLM provider (e.g., Gemini) fails or returns invalid response."""

    pass


# Generation/Output
class GenerationError(MindMapError):
    """Base exception for errors during artifact generation."""

    pass


class ObsidianError(GenerationError):
    """Raised when there are issues creating or updating Obsidian vault files."""

    pass


class LatexError(GenerationError):
    """Raised when LaTeX compilation for resume fails."""

    pass


# Notification
class NotificationError(MindMapError):
    """Raised when sending notifications (e.g., email) fails."""

    pass
