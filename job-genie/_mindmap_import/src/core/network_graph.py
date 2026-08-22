import json
import pathlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from src.ingest.job_details_extractor import JobDetails
from src.ingest.linkedin_parser import LinkedInParser
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ConnectionMetadata:
    """Extra tracking data for a LinkedIn connection."""

    last_contacted: Optional[str] = None
    achievements: List[str] = field(default_factory=list)
    notes: Optional[str] = None


@dataclass
class Connection:
    """Represents a LinkedIn connection with metadata."""

    first_name: str
    last_name: str
    company: Optional[str]
    position: Optional[str]
    connected_on: str
    metadata: ConnectionMetadata = field(default_factory=ConnectionMetadata)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"


class NetworkGraphBuilder:
    """Matches job opportunities with professional connections."""

    def __init__(self, connections_path: pathlib.Path, metadata_path: Optional[pathlib.Path] = None):
        """
        Initialize the NetworkGraphBuilder.

        Args:
            connections_path: Path to the Connections.csv file.
            metadata_path: Path to the JSON file for connection metadata.
        """
        self.parser = LinkedInParser(connections_path)
        self.metadata_path = metadata_path or pathlib.Path("data/network_metadata.json")
        self.connections: List[Connection] = []
        self._load_data()

    def _load_data(self):
        """Loads connections and merges with metadata."""
        try:
            raw_connections = self.parser.parse_connections()
            metadata = self._load_metadata()

            self.connections = []
            for raw in raw_connections:
                conn_id = f"{raw['first_name']}_{raw['last_name']}_{raw['connected_on']}"
                meta_dict = metadata.get(conn_id, {})

                meta = ConnectionMetadata(
                    last_contacted=meta_dict.get("last_contacted"),
                    achievements=meta_dict.get("achievements", []),
                    notes=meta_dict.get("notes"),
                )

                self.connections.append(
                    Connection(
                        first_name=raw["first_name"],
                        last_name=raw["last_name"],
                        company=raw["company"],
                        position=raw["position"],
                        connected_on=raw["connected_on"],
                        metadata=meta,
                    )
                )
        except Exception as e:
            logger.error(f"Failed to load network data: {e}")

    def _load_metadata(self) -> Dict[str, Any]:
        """Loads metadata from JSON file."""
        if self.metadata_path.exists():
            try:
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load metadata file: {e}")
        return {}

    def save_metadata(self):
        """Saves current metadata to JSON file."""
        metadata = {}
        for conn in self.connections:
            # We don't save empty metadata to keep the file clean
            if conn.metadata.last_contacted or conn.metadata.achievements or conn.metadata.notes:
                conn_id = f"{conn.first_name}_{conn.last_name}_{conn.connected_on}"
                metadata[conn_id] = asdict(conn.metadata)

        try:
            self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")

    def find_matches(self, job: JobDetails) -> List[Connection]:
        """
        Finds connections working at the job's company using sanitized matching.

        Args:
            job: The JobDetails object.

        Returns:
            List[Connection]: List of matching connections.
        """
        if not job.company:
            return []

        # Normalize and sanitize job company for matching
        job_company = self._sanitize_for_search(self.parser._normalize_company(job.company))

        matches = []
        for conn in self.connections:
            if conn.company:
                conn_company = self._sanitize_for_search(conn.company)
                # Sanitized fuzzy-ish match: contains
                if job_company in conn_company or conn_company in job_company:
                    matches.append(conn)

        return matches

    def _sanitize_for_search(self, text: str) -> str:
        """
        Removes all non-alphanumeric characters for robust string comparison.

        Args:
            text: The string to sanitize.

        Returns:
            A lowercase string containing only alphanumeric characters.
        """
        if not text:
            return ""
        # Keep only alphanumeric characters
        sanitized = re.sub(r"[^a-zA-Z0-9]", "", text)
        return sanitized.lower()

    def update_connection(self, first_name: str, last_name: str, connected_on: str, **kwargs):
        """
        Updates metadata for a specific connection.

        Args:
            first_name: Connection's first name.
            last_name: Connection's last name.
            connected_on: When they were connected (used for ID uniqueness).
            **kwargs: Metadata fields to update (last_contacted, achievements, notes).
        """
        for conn in self.connections:
            if conn.first_name == first_name and conn.last_name == last_name and conn.connected_on == connected_on:
                if "last_contacted" in kwargs:
                    conn.metadata.last_contacted = kwargs["last_contacted"]
                if "achievements" in kwargs:
                    conn.metadata.achievements = kwargs["achievements"]
                if "notes" in kwargs:
                    conn.metadata.notes = kwargs["notes"]
                break
