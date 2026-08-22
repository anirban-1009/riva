import pathlib
from typing import Any, Dict, List

import pandas as pd

from src.utils.exceptions import LinkedInDataError


class LinkedInParser:
    """Parses LinkedIn Data Export files."""

    def __init__(self, connections_path: pathlib.Path):
        """
        Initialize the parser with the path to the Connections.csv file.

        Args:
            connections_path (pathlib.Path): Path to the Connections.csv file.
        """
        self.connections_path = connections_path

    def parse_connections(self) -> List[Dict[str, Any]]:
        """
        Parses the Connections.csv file and returns a list of connections.

        Returns:
            List[Dict[str, Any]]: A list of dictionaries, where each dictionary represents a connection.
            Each dictionary contains:
                - first_name
                - last_name
                - company
                - position
                - connected_on

        Raises:
            LinkedInDataError: If the file is missing or has invalid format.
        """
        if not self.connections_path.exists():
            raise LinkedInDataError(f"Connections file not found: {self.connections_path}")

        try:
            # LinkedIn export usually skips the first few lines describing the export
            # We need to find the header row. Typically it starts with "First Name"
            # It's safer to read the whole file and find the header

            try:
                df = pd.read_csv(self.connections_path, skiprows=3)  # commonly starts at line 4
            except Exception:
                # Fallback if skiprows fails (e.g. file too short)
                df = pd.read_csv(self.connections_path)

            # Helper to check if it's the right dataframe
            if "First Name" not in df.columns:
                # Try reading without skip if the format is different
                df = pd.read_csv(self.connections_path)
                if "First Name" not in df.columns:
                    raise LinkedInDataError("Invalid LinkedIn Connections CSV format: 'First Name' column missing.")

            connections = []
            for _, row in df.iterrows():
                company = row.get("Company")
                if pd.isna(company):
                    company = None

                position = row.get("Position")
                if pd.isna(position):
                    position = None

                connections.append(
                    {
                        "first_name": row.get("First Name"),
                        "last_name": row.get("Last Name"),
                        "company": self._normalize_company(company) if company else None,
                        "position": position,
                        "connected_on": row.get("Connected On"),
                    }
                )

            return connections

        except Exception as e:
            if isinstance(e, LinkedInDataError):
                raise e
            raise LinkedInDataError(f"Failed to parse LinkedIn connections: {e}") from e

    def get_companies(self) -> List[str]:
        """
        Extracts a list of unique companies from the connections.

        Returns:
             List[str]: A sorted list of unique company names.
        """
        connections = self.parse_connections()
        companies = set()
        for conn in connections:
            if conn["company"]:
                companies.add(conn["company"])
        return sorted(list(companies))

    def _normalize_company(self, company_name: str) -> str:
        """
        Cleans and normalizes company names.

        Args:
            company_name (str): The raw company name.

        Returns:
             str: Normalized company name.
        """
        if not company_name:
            return ""

        name = company_name.strip()

        # Remove common legal entities
        # Prioritize longer suffixes to avoid partial matches
        suffixes = [
            " Inc.",
            " Inc",
            ", Inc.",
            ", Inc",
            " LLC",
            " L.L.C.",
            " Pty Ltd",
            " PVT LTD",
            " Ltd.",
            " Ltd",
            ", Ltd.",
        ]

        temp_name = name
        for suffix in suffixes:
            if temp_name.lower().endswith(suffix.lower()):
                temp_name = temp_name[: -len(suffix)].strip()
                # If we removed a suffix, we might have trailing punctuation like a comma
                if temp_name.endswith(","):
                    temp_name = temp_name[:-1].strip()
                break  # only remove one main suffix

        return temp_name
