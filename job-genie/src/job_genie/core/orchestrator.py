import json
import pathlib
import sys
from types import SimpleNamespace
from typing import Any

import yaml

from job_genie.core.ai import get_llm_client
from job_genie.core.analysis_service import AnalysisService
from job_genie.core.database import DatabaseManager
from job_genie.core.referral_service import ReferralService
from job_genie.core.relevance_scorer import FastScorer
from job_genie.core.resume_service import ResumeService
from job_genie.generator.resume_tailorer import ResumeTailorer
from job_genie.generator.sync_service import SyncService
from job_genie.generator.vault_indexer import VaultIndexer
from job_genie.ingest.browser_manager import BrowserManager
from job_genie.ingest.job_details_extractor import JobDetailsExtractor
from job_genie.ingest.job_searcher import JobSearcher
from job_genie.ingest.resume_parser import PDFResumeParser
from job_genie.notification.email_service import EmailService
from job_genie.utils.logger import get_logger

logger = get_logger(__name__)


class MindMapApp:
    """Orchestrates services for the Job Hunt Mindmap application."""

    def __init__(self, config_path: str) -> None:
        """Initialize services and load configuration."""
        self.project_root = pathlib.Path(__file__).parents[2]
        self.config_path = pathlib.Path(config_path)

        self.config = self._load_config()
        self.session_path = self.project_root / "data" / "session.json"
        self.llm = get_llm_client(self.config.get("ai", {}))

        # Service Initialization
        self.resume_service = ResumeService(self.llm, resume_path=self.config.get("user", {}).get("resume_path"))
        self.referral_service = ReferralService(self.llm, self.config)

        # Extract candidate experience for scoring
        resume_data = self.resume_service.get_resume_data()
        user_experience_years = self.config.get("user", {}).get("total_experience_years") or resume_data.get(
            "total_experience_years"
        )
        if user_experience_years:
            logger.info(f"Candidate experience: {user_experience_years} years")
        experience_tolerance_years = (
            self.config.get("search", {}).get("filters", {}).get("experience_tolerance_years", 0)
        )
        self.analysis_service = AnalysisService(
            self.llm,
            user_experience_years=user_experience_years,
            experience_tolerance_years=experience_tolerance_years,
        )
        self.user_experience_years = user_experience_years

    def _load_config(self) -> dict[str, Any]:
        """Load and parse the YAML configuration file."""
        if not self.config_path.exists():
            logger.error(f"Config file not found: {self.config_path}")
            sys.exit(1)
        with open(self.config_path, "r", encoding="utf-8") as config_file:
            try:
                return yaml.safe_load(config_file)
            except yaml.YAMLError as error:
                logger.error(f"Error parsing YAML: {error}")
                sys.exit(1)

    def check_env(self) -> None:
        """Check if the environment and configuration are valid."""
        logger.info("Checking environment...")
        logger.info("Config file valid.")
        logger.info("Mindmap is ready to run!")

    def login(self) -> None:
        """Launch browser for manual platform authentication."""
        logger.info("Starting browser for manual login...")
        try:
            with BrowserManager(headless=False, session_path=self.session_path) as browser:
                browser.login_manual()
        except Exception as error:
            logger.error(f"Login failed: {error}")
            sys.exit(1)

    def _get_locations(self) -> list[str]:
        """Get flattened list of target locations from config."""
        loc_cfg = self.config.get("search", {}).get("location", "United States")
        if isinstance(loc_cfg, str):
            return [location.strip() for location in loc_cfg.split(",") if location.strip()]
        return loc_cfg

    def _run_searches(self, browser: Any, external_only: bool = False, db: Any | None = None) -> list[Any]:
        """Execute searches across configured platforms and external sites."""
        search_cfg = self.config.get("search", {})
        all_results = []

        searcher = JobSearcher(browser)
        seen_searches = set()

        # 1. LinkedIn Search
        if not external_only:
            for kw in search_cfg.get("keywords", []):
                for loc in self._get_locations():
                    search_key = f"{kw}|{loc}"
                    if search_key in seen_searches:
                        continue
                    logger.info(f"Searching for '{kw}' in {loc}...")
                    results = searcher.search(
                        kw, loc, search_cfg.get("filters", {}), search_cfg.get("location_type", "Any")
                    )
                    all_results.extend(results)
                    seen_searches.add(search_key)
                    if len(results) >= 15:
                        logger.debug(f"Found {len(results)} jobs for '{kw}' in {loc}.")

        # 2. External Career Sites
        external_sites = search_cfg.get("external_sites", [])
        if external_sites:
            from job_genie.ingest.external_searcher import ExternalSiteSearcher

            ext_searcher = ExternalSiteSearcher(browser, self.llm, max_experience_years=self.user_experience_years)
            for site in external_sites:
                try:
                    url = site.get("url") if isinstance(site, dict) else site
                    company = site.get("company", "Unknown") if isinstance(site, dict) else "Unknown"
                    if url:
                        all_results.extend(ext_searcher.search_site(url, company_name=company))
                except Exception as e:
                    logger.error(f"Error searching external site {site}: {e}")

        unique = list({job.id: job for job in all_results if job.id}.values())

        # Filter out jobs already in cache
        if db:
            before_count = len(unique)
            unique = [j for j in unique if not db.job_exists(j.id)]
            if len(unique) < before_count:
                logger.info(f"Skipped {before_count - len(unique)} jobs already in cache.")

        return self._filter_jobs(unique)

    def search(self, headless: bool, external_only: bool = False) -> None:
        """Search for new job postings across defined keywords/locations."""
        logger.info(f"Starting job search (headless={headless}, external_only={external_only})...")
        try:
            with BrowserManager(headless=headless, session_path=self.session_path) as browser:
                extractor = JobDetailsExtractor(browser, llm_client=self.llm)
                filtered = self._run_searches(browser, external_only=external_only, db=extractor.db)

                logger.info(f"Total unique jobs found: {len(filtered)} (after filtering)")

            # Save search results to DB as discovery cache
            for job in filtered:
                # We save minimal info; status 'discovered' means JD not yet scraped
                extractor.db.save_job(
                    {
                        "id": job.id,
                        "title": job.title,
                        "company": job.company,
                        "location": job.location,
                        "link": job.link,
                        "status": "discovered",
                    }
                )

            for job in filtered[:10]:
                logger.info(f"- {job.title} @ {job.company}")
        except Exception as error:
            logger.error(f"Search failed: {error}")
            sys.exit(1)

    def scrape(
        self,
        headless: bool,
        limit: int | None,
        force: bool,
        min_fast_score: int = 0,
        do_score: bool = False,
        external_only: bool = False,
        job_id: str | None = None,
    ) -> None:
        """Extract full details for found jobs and cache them."""
        logger.info(f"Starting extraction (headless={headless}, external_only={external_only})...")
        try:
            with BrowserManager(headless=headless, session_path=self.session_path) as browser:
                extractor = JobDetailsExtractor(browser, llm_client=self.llm)

                if job_id:
                    # Specific job requested
                    logger.info(f"Scraping specific job ID: {job_id}")
                    # Create a dummy object with ID and Link so extractor can process it
                    # We assume standard LinkedIn URL format
                    dummy_link = f"https://www.linkedin.com/jobs/view/{job_id}/"
                    dummy_job = SimpleNamespace(id=job_id, link=dummy_link, title=f"Job {job_id}")
                    filtered = [dummy_job]
                else:
                    # Run full search across platforms, filtering out already-cached jobs
                    filtered = self._run_searches(browser, external_only=external_only, db=extractor.db)

                # Add previously discovered jobs from DB that haven't been scraped yet
                discovered_jobs = extractor.db.get_jobs_by_status("discovered")
                if discovered_jobs:
                    logger.info(f"Adding {len(discovered_jobs)} previously discovered jobs from cache.")
                    for dj in discovered_jobs:
                        # Skip LinkedIn jobs if we only want external jobs
                        if external_only and not str(dj["id"]).startswith("ext-"):
                            continue

                        if dj["id"] not in {j.id for j in filtered}:
                            # Convert DB dict to object compatible with extractor
                            filtered.append(
                                SimpleNamespace(
                                    id=dj["id"],
                                    title=dj["title"],
                                    company=dj["company"],
                                    location=dj["location"],
                                    link=dj["link"],
                                )
                            )

                # Fast Scoring (skip if specific job requested as we don't have details yet)
                if not job_id:
                    resume_data = self.resume_service.get_resume_data()
                    skills = []
                    if isinstance(resume_data.get("skills"), dict):
                        for cat_skills in resume_data["skills"].values():
                            if isinstance(cat_skills, list):
                                skills.extend(cat_skills)

                    fast_scorer = FastScorer(skills)
                    scored_jobs = []
                    for job in filtered:
                        f_score = fast_scorer.score_result(job)
                        if f_score >= min_fast_score:
                            scored_jobs.append((f_score, job))

                    # Sort by score descending
                    scored_jobs.sort(key=lambda x: x[0], reverse=True)
                    final_jobs = [j[1] for j in scored_jobs]
                else:
                    final_jobs = filtered
                if limit:
                    final_jobs = final_jobs[:limit]

                if not final_jobs:
                    logger.info(f"No jobs met the minimum fast score of {min_fast_score}.")
                    return

                logger.info(f"Extracting details for {len(final_jobs)} prioritized jobs...")
                # Only pass force to extraction, scoring handles its own force
                details = extractor.extract_multiple_jobs(final_jobs, force=force)
                logger.info(f"Scraped {len(details)} / {len(final_jobs)} jobs.")

                if do_score and details:
                    logger.info("Performing LLM scoring on scraped jobs...")
                    resume_path = pathlib.Path(self.config.get("user", {}).get("resume_path", "data/resume.pdf"))
                    resume_text = PDFResumeParser().extract_text(resume_path)
                    for job in details:
                        # Skip if already scored, unless force is used
                        res = self.analysis_service.score_job(job, resume_text, force=force)
                        if res:
                            logger.info(f"[{job.id}] Score {res.score} - {job.title} @ {job.company}")

        except Exception as error:
            logger.error(f"Scrape failed: {error}")
            sys.exit(1)

    def refresh_existing_jobs(
        self, headless: bool, limit: int | None, do_score: bool = False, unknown_only: bool = False
    ) -> None:
        """Re-scrape details for jobs already present in the database."""
        logger.info(f"Refreshing existing records (headless={headless})...")
        try:
            extractor = JobDetailsExtractor(None)
            if not extractor.db:
                logger.error("Database not available.")
                return

            all_jobs = extractor.db.get_all_jobs(limit=1000)
            if not all_jobs:
                logger.info("No jobs found in database to refresh.")
                return

            if unknown_only:
                all_jobs = [
                    j
                    for j in all_jobs
                    if "Unknown" in j.get("title")
                    or "Unknown" in j.get("company")
                    or not j.get("title")
                    or not j.get("company")
                ]
                if not all_jobs:
                    logger.info("No unknown jobs found to refresh.")
                    return

            if limit:
                all_jobs = all_jobs[:limit]

            logger.info(f"Found {len(all_jobs)} jobs to refresh.")

            with BrowserManager(headless=headless, session_path=self.session_path) as browser:
                extractor.browser = browser
                extractor.llm = self.llm

                details = extractor.extract_multiple_jobs(all_jobs, force=True)
                logger.info(f"Successfully refreshed {len(details)} / {len(all_jobs)} jobs.")

                if do_score and details:
                    logger.info("Performing LLM re-scoring...")
                    resume_path = pathlib.Path(self.config.get("user", {}).get("resume_path", "data/resume.pdf"))
                    resume_text = PDFResumeParser().extract_text(resume_path)
                    for job in details:
                        self.analysis_service.score_job(job, resume_text)
        except Exception as error:
            logger.error(f"Refresh failed: {error}")
            sys.exit(1)

    def score_jobs(self, score_all: bool, job_id: str | None) -> None:
        """Analyze job requirements against resume and assign scores."""
        try:
            resume_path = pathlib.Path(self.config.get("user", {}).get("resume_path", "data/resume.pdf"))
            resume_text = PDFResumeParser().extract_text(resume_path)

            if job_id:
                job = JobDetailsExtractor(None).get_cached_job(job_id)
                if job:
                    logger.info(f"Scoring job '{job.title}' at '{job.company}'...")
                    res = self.analysis_service.score_job(job, resume_text, force=True)
                    if res:
                        logger.info(f"Job {job_id}: Score {res.score}")
                        logger.info(f"{res.reasoning}")
                else:
                    logger.error(f"Job ID {job_id} not found in database cache. Run 'scrape' first.")
            elif score_all:
                logger.info("Scoring all cached jobs against resume...")
                results = self.analysis_service.score_all_cached_jobs(resume_text)
                if not results:
                    logger.warning("No jobs found in database to score. Run 'search' or 'scrape' first.")
                else:
                    logger.info(f"Finished scoring {len(results)} jobs.")
                    for job, res in results:
                        logger.info(f"[{job.id}] Score {res.score} - {job.title} @ {job.company}")
        except Exception as error:
            logger.error(f"Scoring failed: {error}")
            sys.exit(1)

    def analyze_gaps(self, min_score: int, tag: str | None = None) -> None:
        """Identify missing skills across highly-rated job postings."""
        filter_msg = f" (tag: {tag})" if tag else ""
        logger.info(f"Analyzing gaps across jobs scored >= {min_score}{filter_msg}...")
        report = self.analysis_service.run_gap_analysis(min_score, tag=tag)
        if report:
            logger.info("\n=== Top Missing Skills ===")
            for skill, count in report.skill_frequency.items():
                logger.info(f"- {skill}: {count} jobs")
            logger.info(f"\n=== Improvement Plan ===\n{report.improvement_plan}")

            # Also Sync to Obsidian
            from job_genie.generator.sync_service import SyncService

            sync = SyncService(self.config, llm_client=self.llm)
            content = sync.template_manager.render_gap_analysis(report, min_score, tag)
            filename = f"Gap Analysis - {tag if tag else 'All'}.md"
            file_path = sync.vault_manager.write_file(content, filename, "analysis")
            logger.info(f"Gap analysis report saved to Obsidian: {file_path}")
        else:
            logger.warning(f"No jobs found with a score of {min_score} or higher{filter_msg}.")
            logger.info("Try running 'uv run mindmap score --all' first, or lowering the threshold.")

    def notify(self, min_score: int) -> None:
        """Send job digest emails for jobs meeting the score threshold."""
        logger.info("Preparing notifications...")
        extractor = JobDetailsExtractor(None)
        if not extractor.db:
            return

        analyses = extractor.db.get_all_analyses(min_score=min_score)
        scored_jobs = []
        for row in analyses:
            try:
                data = json.loads(row["analysis_data"])
                job = extractor.get_cached_job(row["id"])
                if job:
                    scored_jobs.append({"job": job, "score": SimpleNamespace(**data)})
            except Exception as e:
                logger.warning(f"Failed to process analysis for {row['id']}: {e}")

        if scored_jobs:
            EmailService(self.config).send_job_digest(scored_jobs)
            logger.info("Notifications sent.")

    def sync(self) -> None:
        """Export processed job data to external knowledge base."""
        logger.info("Syncing to Obsidian...")
        SyncService(self.config, llm_client=self.llm).sync()
        logger.info("Sync complete.")

    def sync_back(self) -> None:
        """Sync status and changes from Obsidian back to the database."""
        logger.info("Syncing back from Obsidian...")
        SyncService(self.config, llm_client=self.llm).sync_from_obsidian()
        logger.info("Sync-back complete.")

    def find(self, query: str, semantic: bool = False, limit: int = 10, reindex: bool = False) -> list[dict[str, Any]]:
        """
        Searches the Obsidian vault: BM25 keyword search by default, or embedding-based
        semantic search when `semantic` is True.
        """
        db = DatabaseManager()
        # Only hand the indexer an LLM client when embeddings are actually needed, so a plain
        # keyword `--reindex` never triggers billable embedding calls.
        indexer = VaultIndexer(self.config, db, llm_client=self.llm if semantic else None)

        if reindex or semantic:
            # Semantic search needs freshly embedded docs to be useful; keyword search can
            # tolerate a stale index since it's usually refreshed right after 'sync'.
            indexer.reindex_changed()

        if semantic:
            return indexer.search_semantic(query, limit=limit)
        return indexer.search_text(query, limit=limit)

    def referral(self, job_id: str, connection_name: str | None, max_chars: int = 300) -> dict[str, str] | None:
        """Generate personalized referral message for a job and contact."""
        job = JobDetailsExtractor(None).get_cached_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found.")
            return

        matches = self.referral_service.find_potential_connections(job)
        target = None
        if connection_name:
            target = SimpleNamespace(full_name=connection_name, position="Professional")
        elif matches:
            target = matches[0]
            logger.info(f"Using existing connection: {target.full_name}")

        # Handled manual input in CLI side or here?
        # If we keep this class as the core, it might need to return a "needs_input" status
        # but for this specific tool, let's allow input in the Orchestrator for simplicity
        # if it's strictly a CLI tool.
        if not target:
            logger.warning("No connections found.")
            return None  # Signal to CLI that it needs input

        resume_data = self.resume_service.get_resume_data()
        msg = self.referral_service.generate_message(job, target, resume_data, max_chars=max_chars)
        self.referral_service.save_referral(job_id, target.full_name, msg)
        return {"to": target.full_name, "message": msg}

    def tailor_resume(self, job_id: str) -> pathlib.Path | None:
        """Create a job-optimized resume PDF based on JD analysis."""
        job = JobDetailsExtractor(None).get_cached_job(job_id)
        if not job:
            return None

        resume_data = self.resume_service.get_resume_data()
        tailorer = ResumeTailorer(self.config)

        logger.info(f"Tailoring for {job.title} at {job.company}...")
        job_desc = f"Title: {job.title}\nCompany: {job.company}\n\n{job.description}"
        tailored_data = tailorer.tailor_resume(resume_data, job_desc)

        latex = tailorer.generate_latex(tailored_data)
        output_dir = pathlib.Path("output/resumes")
        output_dir.mkdir(parents=True, exist_ok=True)

        safe_company = (
            "".join(char for char in job.company if char.isalnum() or char in (" ", "_", "-")).strip().replace(" ", "_")
        )
        output_path = output_dir / f"Resume_{safe_company}_{job_id}.pdf"

        tailorer.compile_pdf(latex, output_path)
        return output_path

    def test_ai(self, prompt: str) -> None:
        """Test AI client connectivity with a simple prompt."""
        ai_cfg = self.config.get("ai", {})
        provider = ai_cfg.get("provider", "gemini")
        logger.info(f"Initializing {provider} client and sending test prompt...")
        try:
            response = self.llm.generate(prompt)
            if response:
                logger.info(f"\nAI Response ({provider}):")
                logger.info(f"{response.strip()}")
            else:
                logger.error("AI returned empty response. Check API key/Ollama.")
        except Exception as error:
            logger.error(f"AI Check failed: {error}")
            sys.exit(1)

    def find_network(self, job_id: str) -> None:
        """Search for professional contacts at the job's company."""
        extractor = JobDetailsExtractor(None)
        job = extractor.get_cached_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found.")
            return

        matches = self.referral_service.find_potential_connections(job)
        logger.info(f"Found {len(matches)} connections at {job.company}:")
        for conn in matches:
            logger.info(f"- {conn.full_name} ({conn.position})")

    def map_all_networks(self) -> None:
        """Map professional connections to all cached jobs."""
        logger.info("Mapping connections across all available jobs...")

        extractor = JobDetailsExtractor(None)
        if not extractor.db:
            logger.error("Database not available.")
            return

        all_jobs_data = extractor.db.get_all_jobs(limit=1000)
        jobs_with_connections = 0
        total_connections = 0

        for job_data in all_jobs_data:
            job = extractor.get_cached_job(job_data["id"])
            if not job:
                continue

            matches = self.referral_service.find_potential_connections(job)
            if matches:
                jobs_with_connections += 1
                total_connections += len(matches)
                logger.info(f"[{job.id}] {job.title} @ {job.company}")
                for conn in matches:
                    logger.info(f"  - {conn.full_name} ({conn.position})")

        logger.info(f"\n{'=' * 40}")
        logger.info(f"Summary: Found {total_connections} connections across {jobs_with_connections} jobs.")
        logger.info(f"{'=' * 40}")

    def prune(self) -> None:
        """Prune orphaned records from Obsidian."""
        from job_genie.generator.sync_service import SyncService

        SyncService(self.config, llm_client=self.llm).prune_vault()

    def _filter_jobs(self, jobs: list[Any]) -> list[Any]:
        """Filters jobs based on exclude_keywords in configuration."""
        exclude = self.config.get("search", {}).get("exclude_keywords", [])
        if not exclude:
            return jobs

        filtered = []
        for job in jobs:
            raw_title = job.get("title") if isinstance(job, dict) else getattr(job, "title", "")
            title = (raw_title or "").lower()
            if not any(word.lower() in title for word in exclude):
                filtered.append(job)
            else:
                logger.debug(f"Filtering out job due to keyword match: {title}")

        return filtered
