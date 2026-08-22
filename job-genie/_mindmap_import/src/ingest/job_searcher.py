import random
import time
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.core.constants import LINKEDIN_JOBS_SEARCH_URL, ExperienceLevel, JobType, LocationType
from src.ingest.browser_manager import BrowserManager
from src.ingest.selectors import (
    LOGIN_MODAL_SELECTORS,
    SEARCH_CARD_COMPANY_SELECTORS,
    SEARCH_CARD_LOCATION_SELECTORS,
    SEARCH_CARD_TITLE_SELECTORS,
    SEARCH_JOB_CARD_SELECTORS,
    SEARCH_RESULTS_LIST_SELECTORS,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class JobSearchResult:
    """Represents a job listing from search results."""

    id: str
    title: str
    company: str
    link: str
    location: str


class JobSearcher:
    """Constructs search URLs and scrapes LinkedIn job listings."""

    def __init__(self, browser_manager: BrowserManager):
        """
        Initialize the JobSearcher.

        Args:
            browser_manager: Initialized BrowserManager instance.
        """
        self.browser = browser_manager

    def construct_search_url(
        self, keywords: str, location: str, filters: Dict[str, List[str]] = None, location_type: str = "Any"
    ) -> str:
        """
        Constructs a LinkedIn search URL based on criteria.

        Args:
            keywords: Search keywords (e.g., "Python Developer").
            location: Search location (e.g., "United States").
            filters: Optional dictionary of filters (experience_level, job_type).
            location_type: On-site, Remote, Hybrid, or Any.

        Returns:
            A fully qualified LinkedIn search URL.
        """
        params = {
            "keywords": keywords,
            "location": location,
            "refresh": "true",
        }

        # Handle Location Type (f_WT)
        loc_val = LocationType.from_str(location_type)
        if loc_val:
            params["f_WT"] = loc_val

        # Handle Experience Level (f_E)
        if filters and "experience_level" in filters:
            levels = [ExperienceLevel.from_str(lvl) for lvl in filters["experience_level"]]
            levels = [v for v in levels if v]
            if levels:
                params["f_E"] = ",".join(levels)

        # Handle Job Type (f_JT)
        if filters and "job_type" in filters:
            types = [JobType.from_str(jt) for jt in filters["job_type"]]
            types = [v for v in types if v]
            if types:
                params["f_JT"] = ",".join(types)

        query_string = urllib.parse.urlencode(params)
        return f"{LINKEDIN_JOBS_SEARCH_URL}?{query_string}"

    def search(
        self, keywords: str, location: str, filters: Dict[str, List[str]] = None, location_type: str = "Any"
    ) -> List[JobSearchResult]:
        """
        Performs the job search and scrapes results.

        Args:
            keywords: Search keywords.
            location: Search location.
            filters: Optional filters.
            location_type: On-site, Remote, Hybrid, or Any.

        Returns:
            A list of JobSearchResult objects.
        """
        url = self.construct_search_url(keywords, location, filters, location_type)
        logger.info(f"Searching for jobs: {url}")

        # Add random delay before navigating to the search URL to mimic human behavior
        time.sleep(random.uniform(2.0, 5.0))

        self.browser.goto(url)
        page = self.browser.page

        # LinkedIn might show a login wall if cookies are not set or expired.
        # BrowserManager should handle state, but we should check if we are on the right page.
        if "login" in page.url:
            logger.error("LinkedIn login wall detected. Please ensure session.json is valid.")
            return []

        found_selector = None

        for selector in SEARCH_RESULTS_LIST_SELECTORS:
            try:
                # Wait longer for the first few selectors
                wait_time = 5000 if selector in SEARCH_RESULTS_LIST_SELECTORS[:3] else 1000
                page.wait_for_selector(selector, timeout=wait_time)
                found_selector = selector
                logger.info(f"Found results list container: {selector}")
                break
            except Exception:
                continue

        if not found_selector:
            # Check for "No matching jobs found"
            if "No matching jobs found" in page.content():
                logger.info("No matching jobs found.")
                return []

            # Fallback: check if any job cards exist directly
            card_detect_selector = (
                ".jobs-search-results-list__item, .job-card-container, .base-card, .job-search-card, .base-search-card"
            )
            if page.locator(card_detect_selector).count() > 0:
                logger.info("Found job cards without list container.")
                job_cards = page.locator(card_detect_selector).all()
            else:
                # Check for modal login wall or security check
                if page.locator(", ".join(LOGIN_MODAL_SELECTORS)).count() > 0:
                    logger.error(
                        "LinkedIn login modal or authwall detected. Please run 'login' to update session.json."
                    )
                    return []

                if "security-check" in page.url or "checkpoint" in page.url:
                    logger.error("LinkedIn security check detected. Please log in manually.")
                    return []

                logger.warning(f"Job results list not found after waiting. Current URL: {page.url}")
                return []
        else:
            # Scroll to load more
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(random.uniform(1.5, 3.5))

            # Determine card selector based on found list selector
            # Standard items or any card-like element inside the container
            card_selector = ", ".join(SEARCH_JOB_CARD_SELECTORS)

            job_cards = page.locator(found_selector).locator(card_selector).all()
        results = []

        for card in job_cards:
            try:
                # Try multiple selectors for each field
                title_elem = self._get_best_locator(card, SEARCH_CARD_TITLE_SELECTORS)
                if not title_elem:
                    logger.debug("Skipping job card: title element not found.")
                    continue

                # Clean up title - sometimes it contains duplicate text or screen reader text
                title_lines = [line.strip() for line in title_elem.inner_text().split("\n") if line.strip()]
                title = title_lines[0] if title_lines else ""

                link = title_elem.get_attribute("href")

                # If title is not a link, try to find a link inside the card
                if not link:
                    link_elem = self._get_best_locator(card, ["a"])
                    if link_elem:
                        link = link_elem.get_attribute("href")

                # Normalize link
                if link:
                    link = link.split("?")[0]
                    if link.startswith("/"):
                        link = f"https://www.linkedin.com{link}"

                job_id = ""
                if link:
                    parts = link.rstrip("/").split("/")
                    if parts:
                        job_id = parts[-1]
                        # Some links have IDs at the end, some in the middle
                        if "-" in job_id and not job_id.isdigit():
                            job_id = job_id.split("-")[-1]

                if not job_id:
                    logger.debug(f"Skipping job card '{title}': job_id not found in link {link}")
                    continue

                company_elem = self._get_best_locator(card, SEARCH_CARD_COMPANY_SELECTORS)
                if company_elem:
                    comp_lines = [line.strip() for line in company_elem.inner_text().split("\n") if line.strip()]
                    company = comp_lines[0] if comp_lines else "Unknown"
                else:
                    company = "Unknown"

                location_elem = self._get_best_locator(card, SEARCH_CARD_LOCATION_SELECTORS)
                if location_elem:
                    loc_lines = [line.strip() for line in location_elem.inner_text().split("\n") if line.strip()]
                    location_str = loc_lines[0] if loc_lines else ""
                else:
                    location_str = ""

                results.append(
                    JobSearchResult(id=job_id, title=title, company=company, link=link or "", location=location_str)
                )
            except Exception as e:
                logger.debug(f"Failed to parse job card: {e}")
                continue

        logger.info(f"Found {len(results)} jobs.")
        return results

    def _get_best_locator(self, root: Any, selectors: List[str]) -> Optional[Any]:
        """Helper to find the first matching locator from a list of selectors."""
        for selector in selectors:
            try:
                locator = root.locator(selector)
                if locator.count() > 0:
                    return locator.first
            except Exception:
                continue
        return None
