import os
from enum import Enum

# LinkedIn Search Base URL
LINKEDIN_JOBS_SEARCH_URL = os.getenv("LINKEDIN_JOBS_SEARCH_URL", "https://www.linkedin.com/jobs/search/")


class LocationType(Enum):
    """LinkedIn Location Type (f_WT) mapping."""

    ON_SITE = "1"
    REMOTE = "2"
    HYBRID = "3"

    @classmethod
    def from_str(cls, label: str) -> str:
        """Get the value from a string label (e.g., 'Remote')."""
        mapping = {
            "On-site": cls.ON_SITE.value,
            "Remote": cls.REMOTE.value,
            "Hybrid": cls.HYBRID.value,
        }
        return mapping.get(label, "")


class ExperienceLevel(Enum):
    """LinkedIn Experience Level (f_E) mapping."""

    INTERNSHIP = "1"
    ENTRY_LEVEL = "2"
    ASSOCIATE = "3"
    MID_SENIOR_LEVEL = "4"
    DIRECTOR = "5"
    EXECUTIVE = "6"

    @classmethod
    def from_str(cls, label: str) -> str:
        """Get the value from a string label (e.g., 'Mid-Senior level')."""
        mapping = {
            "Internship": cls.INTERNSHIP.value,
            "Entry level": cls.ENTRY_LEVEL.value,
            "Associate": cls.ASSOCIATE.value,
            "Mid-Senior level": cls.MID_SENIOR_LEVEL.value,
            "Director": cls.DIRECTOR.value,
            "Executive": cls.EXECUTIVE.value,
        }
        return mapping.get(label, "")


class JobType(Enum):
    """LinkedIn Job Type (f_JT) mapping."""

    FULL_TIME = "F"
    PART_TIME = "P"
    CONTRACT = "C"
    TEMPORARY = "T"
    VOLUNTEER = "V"
    INTERNSHIP = "I"

    @classmethod
    def from_str(cls, label: str) -> str:
        """Get the value from a string label (e.g., 'Full-time')."""
        mapping = {
            "Full-time": cls.FULL_TIME.value,
            "Part-time": cls.PART_TIME.value,
            "Contract": cls.CONTRACT.value,
            "Temporary": cls.TEMPORARY.value,
            "Volunteer": cls.VOLUNTEER.value,
            "Internship": cls.INTERNSHIP.value,
        }
        return mapping.get(label, "")
