import json
import random
import time
from dataclasses import asdict, dataclass, fields
from typing import Any, Dict, List, Optional

from src.core.ai import LLMClient
from src.core.database import DatabaseManager
from src.ingest.browser_manager import BrowserManager
from src.ingest.selectors import (
    JOB_APPLY_SELECTORS,
    JOB_COMPANY_SELECTORS,
    JOB_CRITERIA_HEADER_SELECTORS,
    JOB_CRITERIA_ITEM_SELECTORS,
    JOB_CRITERIA_VALUE_SELECTORS,
    JOB_DESCRIPTION_SELECTORS,
    JOB_ERROR_SELECTORS,
    JOB_INSIGHT_SELECTORS,
    JOB_LOCATION_SELECTORS,
    JOB_PAGE_WAIT_SELECTORS,
    JOB_POSTED_DATE_SELECTORS,
    JOB_SALARY_SELECTORS,
    JOB_TITLE_SELECTORS,
    LOGIN_MODAL_SELECTORS,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class JobDetails:
    """Represents full details of a job listing."""

    id: str
    title: str
    company: str
    location: str
    description: str
    posted_date: str
    seniority_level: str
    employment_type: str
    job_function: str
    industries: str
    link: str
    salary: str = ""
    apply_link: str = ""
    created_at: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None
    specialization: str = "General"

    def determine_specialization(self) -> str:
        """Categorize job into typical tech specializations based on title."""
        title_lower = self.title.lower()

        if any(
            x in title_lower
            for x in [
                "machine learning",
                "ml",
                "ai ",
                "artificial intelligence",
                "nlp",
                "computer vision",
                "generative ai",
                "llm",
                "deep learning",
                "transformers",
                "pytorch",
                "tensorflow",
                "neural",
            ]
        ):
            return "AI_ML"
        if any(x in title_lower for x in ["data scientist", "data analyst", "data engineer", "big data", "analytics"]):
            return "Data_Science"
        if any(x in title_lower for x in ["python", "django", "flask", "fastapi", "numpy", "pandas"]):
            return "Python_Dev"
        if any(
            x in title_lower
            for x in ["backend", "back-end", "server", "distributed systems", "api engineer", "platform engineer"]
        ):
            return "Backend"
        if any(
            x in title_lower
            for x in [
                "frontend",
                "front-end",
                "react",
                "vue",
                "angular",
                "javascript",
                "typescript",
                "ui/ux",
                "web developer",
            ]
        ):
            return "Frontend"
        if any(
            x in title_lower
            for x in ["devops", "sre", "cloud", "aws", "azure", "gcp", "infrastructure", "kubernetes", "docker"]
        ):
            return "DevOps_Cloud"
        if any(x in title_lower for x in ["full stack", "fullstack"]):
            return "FullStack"

        return "General"


class JobDetailsExtractor:
    """Visits individual job URLs and extracts full details."""

    def __init__(
        self,
        browser_manager: Optional[BrowserManager],
        llm_client: Optional[LLMClient] = None,
    ):
        """
        Initialize the JobDetailsExtractor.

        Args:
            browser_manager: Initialized BrowserManager instance.
            llm_client: Optional LLMClient to refine extracted data.
        """
        self.browser = browser_manager
        self.llm = llm_client

        # Initialize Database Manager
        try:
            self.db = DatabaseManager()
        except Exception as e:
            logger.warning(f"Failed to initialize database: {e}")
            self.db = None

    def get_cached_job(self, job_id: str) -> Optional[JobDetails]:
        """Loads job details from database."""
        if self.db:
            try:
                job_data = self.db.get_job(job_id)
                if job_data:
                    # Parse raw_data if string
                    if job_data.get("raw_data") and isinstance(job_data["raw_data"], str):
                        try:
                            job_data["raw_data"] = json.loads(job_data["raw_data"])
                        except json.JSONDecodeError:
                            job_data["raw_data"] = {}

                    # Remove DB-specific fields that are not in JobDetails dataclass
                    valid_keys = {f.name for f in fields(JobDetails)}
                    filtered_data = {k: v for k, v in job_data.items() if k in valid_keys}

                    return JobDetails(**filtered_data)
            except Exception as e:
                logger.warning(f"Error retrieving job {job_id} from DB: {e}")
        return None

    def _save_to_cache(self, job: JobDetails):
        """Saves job details to database."""
        if self.db:
            try:
                self.db.save_job(asdict(job))
                logger.info(f"Saved job {job.id} to database.")
            except Exception as e:
                logger.error(f"Failed to save job {job.id} to database: {e}")

    def extract_job_details(
        self,
        job_id: str,
        job_url: str,
        fallback_data: Optional[Any] = None,
        force: bool = False,
    ) -> Optional[JobDetails]:
        """
        Visits a job URL and extracts its details.

        Args:
            job_id: The unique ID of the job.
            job_url: The full URL to the job listing.
            fallback_data: Optional JobSearchResult or dict with initial info.
            force: If True, ignore cache and re-scrape.

        Returns:
            JobDetails object if successful, None otherwise.
        """
        # Check cache first
        if not force:
            cached = self.get_cached_job(job_id)

            if cached:
                logger.info(f"Using cached details for job {job_id}")
                return cached

        # Try to pull company from fallback early to attach to placeholder models
        company_name_fallback = "Unknown Company"
        if fallback_data:
            company_name_fallback = getattr(fallback_data, "company", None)
            if company_name_fallback is None and isinstance(fallback_data, dict):
                company_name_fallback = fallback_data.get("company", "Unknown Company")

        logger.info(f"Extracting details for job {job_id}: {job_url}")
        try:
            self.browser.goto(job_url)
            # Give it a moment to settle even after goto returns, with random delay
            time.sleep(random.uniform(2.0, 5.0))
        except Exception as e:
            logger.error(f"Failed to navigate to {job_url}: {e}")
            return None

        page = self.browser.page

        try:
            # Short-circuit for external sites
            if job_id.startswith("ext-"):
                time.sleep(2.0)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(2.0)
                logger.info(f"Extracting external job {job_id} using LLM...")
                page_text = page.inner_text("body")
                job_details = self._extract_from_page_text(
                    JobDetails(job_id, "", company_name_fallback, "", "", "", "", "", "", "", job_url),
                    page_text[:15000],
                )
                if fallback_data:

                    def get_data(field):
                        val = getattr(fallback_data, field, None)
                        if val is None and isinstance(fallback_data, dict):
                            val = fallback_data.get(field)
                        return val or ""

                    if not job_details.title or job_details.title == "Unknown Title":
                        job_details.title = get_data("title") or "Unknown Title"

                if job_details.title != "Unknown Title" or job_details.id:
                    self._save_to_cache(job_details)
                    return job_details
                else:
                    logger.warning(f"Extracted completely empty details for external job {job_id}")
                    return None

            # Wait for any of the main job page elements to appear (shorter timeout)
            # We wait for the most common success selector
            try:
                page.wait_for_selector(", ".join(JOB_PAGE_WAIT_SELECTORS), timeout=5000)
            except Exception:
                # If success selectors don't show, check if an error state is already visible
                if not self._check_presence(page, JOB_ERROR_SELECTORS):
                    logger.warning(f"Wait for job details timed out for {job_id} after 5s. Using current state.")

            # Check for early exit/error states
            if self._check_presence(page, JOB_ERROR_SELECTORS):
                logger.info(f"Page error detected for {job_id}. Triggering LLM fallback extraction.")
                return self._extract_from_page_text(
                    JobDetails(job_id, "", "", "", "", "", "", "", "", "", job_url), page.inner_text("body")
                )

            # Check for login walls
            if self._check_presence(page, LOGIN_MODAL_SELECTORS):
                logger.debug(f"Login modal detected on job page {job_id}. Attempting to extract what's visible.")

            # Let's try to be smart about extracting them.
            title = self._get_text(page, JOB_TITLE_SELECTORS)
            company = self._get_text(page, JOB_COMPANY_SELECTORS)
            location = self._get_text(page, JOB_LOCATION_SELECTORS)
            description = self._get_text(page, JOB_DESCRIPTION_SELECTORS)
            posted_date = self._get_text(page, JOB_POSTED_DATE_SELECTORS)
            salary = self._get_text(page, JOB_SALARY_SELECTORS)

            # Try to find apply link
            apply_link = ""
            apply_elem = self._get_best_locator(page, JOB_APPLY_SELECTORS)
            if apply_elem:
                apply_link = apply_elem.get_attribute("href") or ""

            # Metadata extraction
            seniority = ""
            employment_type = ""
            job_function = ""
            industries = ""

            # Try to extract from job insights (unified view)
            insights = []
            for selector in JOB_INSIGHT_SELECTORS:
                found = page.locator(selector).all()
                if found:
                    insights = found
                    break

            for item in insights:
                text = item.inner_text()
                if any(x in text for x in ["Full-time", "Contract", "Part-time", "Temporary"]):
                    employment_type = text.split("·")[0].strip() if "·" in text else text.strip()
                if any(
                    x in text
                    for x in ["Entry level", "Mid-Senior level", "Associate", "Director", "Executive", "Internship"]
                ):
                    seniority = text.split("·")[0].strip() if "·" in text else text.strip()

            # Try to extract from job criteria list (direct view)
            criteria_items = []
            for selector in JOB_CRITERIA_ITEM_SELECTORS:
                found = page.locator(selector).all()
                if found:
                    criteria_items = found
                    break

            for item in criteria_items:
                header = self._get_text(item, JOB_CRITERIA_HEADER_SELECTORS)
                value = self._get_text(item, JOB_CRITERIA_VALUE_SELECTORS)

                if "Seniority level" in header:
                    seniority = value
                elif "Employment type" in header:
                    employment_type = value
                elif "Job function" in header:
                    job_function = value
                elif "Industries" in header:
                    industries = value

            # Fallback to search result data if we missed something critical
            if fallback_data:

                def get_data(field):
                    val = getattr(fallback_data, field, None)
                    if val is None and isinstance(fallback_data, dict):
                        val = fallback_data.get(field)
                    return val or ""

                if not title:
                    title = get_data("title")
                if not company or company == "Unknown":
                    company = get_data("company")
                if not location:
                    location = get_data("location")

            job_details = JobDetails(
                id=job_id,
                title=title or "Unknown Title",
                company=company or "Unknown Company",
                location=location or "",
                description=description or "No description extracted.",
                posted_date=posted_date,
                seniority_level=seniority,
                employment_type=employment_type,
                job_function=job_function,
                industries=industries,
                link=job_url,
                salary=salary,
                apply_link=apply_link,
            )
            job_details.specialization = job_details.determine_specialization()

            # Refine with LLM if available and extraction seems messy or incomplete
            if self.llm and (
                not job_details.description
                or len(job_details.description) < 100
                or job_details.company == "Unknown Company"
            ):
                # Full page text extraction as a powerful fallback
                page_text = page.locator("body").inner_text()
                job_details = self._extract_from_page_text(job_details, page_text[:10000])

            # Save the job details even if some information is missing
            # We only require a title OR an ID from the link to be somewhat valid
            if job_details.title != "Unknown Title" or job_details.id:
                self._save_to_cache(job_details)
                return job_details
            else:
                logger.warning(f"Extracted completely empty details for job {job_id}")
                return None

        except Exception as e:
            import traceback

            traceback.print_exc()
            logger.error(f"Error during job extraction for {job_id}: {e}")
            return None

    def _extract_from_page_text(self, job: JobDetails, page_text: str) -> JobDetails:
        """Uses LLM to extract structured data from raw page text when selectors fail."""
        logger.info(f"Using LLM fallback extraction for job {job.id}...")

        prompt = f"""
        Extract job details from the following web page text. 
        Focus on the Title, Company, Location, Description, Salary, and Seniority.

        Page Text:
        {page_text}

        Output the result ONLY as a JSON object with these keys:
        - "title": job title
        - "company": company name
        - "location": location
        - "description": full job description
        - "salary": salary range if mentioned
        - "seniority": seniority level
        - "employment_type": e.g. Full-time, Contract
        """

        try:
            extracted = self.llm.generate_json(prompt)
            if extracted:
                job.title = extracted.get("title") or job.title
                job.company = extracted.get("company") or job.company
                job.location = extracted.get("location") or job.location
                job.description = extracted.get("description") or job.description
                job.salary = extracted.get("salary") or job.salary
                job.seniority_level = extracted.get("seniority") or job.seniority_level
                job.employment_type = extracted.get("employment_type") or job.employment_type
                job.specialization = job.determine_specialization()
        except Exception as e:
            logger.warning(f"LLM extraction fallback failed for job {job.id}: {e}")

        return job

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

    def _get_text(self, root: Any, selectors: List[str]) -> str:
        """Helper to try multiple selectors and return the first found text."""
        for selector in selectors:
            try:
                elem = root.locator(selector)
                if elem.count() > 0:
                    return elem.first.inner_text().strip()
            except Exception:
                continue
        return ""

    def _check_presence(self, root: Any, selectors: List[str]) -> bool:
        """Checks if any of the selectors are present on the page."""
        for selector in selectors:
            try:
                if root.locator(selector).count() > 0:
                    return True
            except Exception:
                continue
        return False

    def extract_multiple_jobs(self, job_list: List[Any], delay: float = 2.0, force: bool = False) -> List[JobDetails]:
        """
        Extracts details for multiple jobs.

        Args:
            job_list: List of objects/dicts with 'id' and 'link'.
            delay: Delay in seconds between requests.
            force: If True, ignore cache and re-scrape.

        Returns:
            List of JobDetails.
        """
        results = []
        for job in job_list:
            jid = getattr(job, "id", None) or job.get("id")
            jlink = getattr(job, "link", None) or job.get("link")

            if not jid or not jlink:
                continue

            details = self.extract_job_details(jid, jlink, fallback_data=job, force=force)
            if details:
                results.append(details)

            if delay > 0:
                # Add randomness to avoid predictable intervals
                actual_delay = delay + random.uniform(1.0, 3.0)
                time.sleep(actual_delay)

        return results
