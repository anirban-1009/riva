class MindMapError(Exception):
    """Base exception for all Job Hunt Mindmap errors."""



# Configuration
class ConfigError(MindMapError):
    """Raised when configuration file is invalid or missing required keys."""



# Data Ingestion
class DataSourceError(MindMapError):
    """Base exception for errors related to fetching or parsing data."""



class ResumeParsingError(DataSourceError):
    """Raised when resume parsing fails due to invalid format or content."""



class LinkedInDataError(DataSourceError):
    """Raised when LinkedIn data format is invalid or missing columns."""



class ScraperError(DataSourceError):
    """Raised when web scraping or browser automation fails."""



# Logic/AI
class AnalysisError(MindMapError):
    """Base exception for errors during data analysis or matching."""



class LLMError(AnalysisError):
    """Raised when the LLM provider (e.g., Gemini) fails or returns invalid response."""



# Generation/Output
class GenerationError(MindMapError):
    """Base exception for errors during artifact generation."""



class ObsidianError(GenerationError):
    """Raised when there are issues creating or updating Obsidian vault files."""



class LatexError(GenerationError):
    """Raised when LaTeX compilation for resume fails."""



# Notification
class NotificationError(MindMapError):
    """Raised when sending notifications (e.g., email) fails."""

