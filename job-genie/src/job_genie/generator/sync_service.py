import json
import pathlib
import re
from typing import Any

import yaml

from job_genie.core.network_graph import NetworkGraphBuilder
from job_genie.core.referral_service import ReferralService
from job_genie.core.relevance_scorer import ScoringResult
from job_genie.core.resume_service import ResumeService
from job_genie.generator.dashboard_generator import DashboardGenerator
from job_genie.generator.template_manager import TemplateManager
from job_genie.generator.vault_indexer import VaultIndexer
from job_genie.generator.vault_manager import VaultManager
from job_genie.ingest.job_details_extractor import JobDetailsExtractor
from job_genie.utils.logger import get_logger

logger = get_logger(__name__)

# Maps the DB's internal job status to the display value written into a job note's
# frontmatter `status` property (and back, when read from Obsidian).
STATUS_DB_TO_DISPLAY = {
    "new": "ToApply",
    "discovered": "ToApply",
    "to_apply": "ToApply",
    "applied": "Applied",
    "interviewing": "Interviewing",
    "rejected": "Rejected",
    "offered": "Offered",
    "wishlist": "Wishlist",
}
STATUS_DISPLAY_TO_DB = {
    "ToApply": "to_apply",
    "Applied": "applied",
    "Interviewing": "interviewing",
    "Rejected": "rejected",
    "Offered": "offered",
    "Wishlist": "wishlist",
}


def _read_frontmatter(content: str) -> dict[str, Any]:
    """Parses the leading YAML frontmatter block of a note, returning {} if absent/invalid."""
    if not content.startswith("---"):
        return {}
    end = content.find("\n---", 3)
    if end == -1:
        return {}
    try:
        data = yaml.safe_load(content[3:end])
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


_LEGACY_JOB_ID_RE = re.compile(r"- \*\*Job ID:\*\* (\S+)")


def _extract_job_id(content: str, frontmatter: dict[str, Any]) -> str | None:
    """Gets a note's job_id, falling back to the pre-frontmatter `- **Job ID:**` bullet format
    for notes written before the frontmatter migration and never regenerated since."""
    job_id = frontmatter.get("job_id")
    if job_id is not None:
        return str(job_id)
    match = _LEGACY_JOB_ID_RE.search(content)
    return match.group(1) if match else None


def _is_auto_rejected(job_data: dict[str, Any]) -> bool:
    """True for jobs the pipeline auto-rejected with a 0 score (usually the experience regex
    pre-filter in RelevanceScorer) - these were never real candidates and shouldn't be synced.
    A job manually marked "Rejected" after actually being considered has a real (non-zero)
    score, so it's unaffected and still syncs normally."""
    return job_data.get("status") == "rejected" and job_data.get("relevance_score") == 0


class SyncService:
    """Orchestrates the synchronization of data to Obsidian."""

    def __init__(self, config: dict[str, Any], llm_client: Any | None = None):
        self.config = config
        self.vault_manager = VaultManager(config)
        self.template_manager = TemplateManager()
        self.dashboard_generator = DashboardGenerator(config)
        self.extractor = JobDetailsExtractor(None, llm_client=llm_client)
        self.referral_service = ReferralService(llm_client, config)
        self.resume_service = ResumeService(llm_client, config.get("user", {}).get("resume_path"))
        self.resume_data = self.resume_service.get_resume_data()

    def sync(self) -> None:
        """Syncs jobs, companies, and analysis to the Obsidian Vault.

        Pulls in edits made directly in Obsidian (the `applied` checkbox, `status`) before
        regenerating notes - otherwise a checkbox ticked in the vault would never reach the DB,
        and the very next sync would overwrite it back to whatever the DB still had.
        """
        logger.info("Starting Obsidian sync...")

        # 1. Ensure Vault Folders Exist
        self.vault_manager.ensure_folders_exist()

        # 2. Pull status/applied edits made in Obsidian into the DB first
        self.sync_from_obsidian()

        # 3. Sync Jobs and Companies
        self._sync_all()

        # 4. Generate the applications-by-month/week dashboard
        self.dashboard_generator.generate(self.extractor.db)

        # 5. Refresh vault search index (job/person/company notes just changed above)
        self._reindex_vault()

        logger.info("Obsidian sync complete.")

    def _reindex_vault(self) -> None:
        """Updates the vault search index after notes have been written/removed."""
        if not self.extractor.db:
            return
        try:
            VaultIndexer(self.config, self.extractor.db).reindex_changed()
        except Exception as e:
            logger.warning(f"Vault search reindex failed: {e}")

    def _sync_all(self) -> None:
        """Reads jobs and connections and writes them to the Vault with links."""
        if not self.extractor.db:
            logger.warning("Database not available. Nothing to sync.")
            return

        all_jobs_data = self.extractor.db.get_all_jobs(limit=10000)
        jobs: list[dict[str, Any]] = []
        skipped_unscraped = 0
        skipped_auto_rejected = 0
        for jd in all_jobs_data:
            if jd.get("status") == "discovered":
                # Not yet scraped - skip until 'scrape' has populated full details
                skipped_unscraped += 1
                continue
            if _is_auto_rejected(jd):
                # Experience regex filter (or the LLM) scored it 0 and it was never a real
                # candidate - don't clutter the vault with these.
                skipped_auto_rejected += 1
                continue
            job_obj = self.extractor.get_cached_job(jd["id"])
            if job_obj:
                score = self._load_analysis(jd)
                jobs.append(
                    {
                        "details": job_obj,
                        "score": score,
                        "status": jd.get("status"),
                        "applied_at": jd.get("applied_at"),
                    }
                )

        if skipped_unscraped:
            logger.info(f"Skipped {skipped_unscraped} unscraped ('discovered') jobs during sync.")
        if skipped_auto_rejected:
            logger.info(f"Skipped {skipped_auto_rejected} auto-rejected (score 0) jobs during sync.")

        # Sort jobs by score ascending for deterministic ordering
        bucket_size = int(self.config.get("sync", {}).get("score_bucket_size", 10))

        # Frontmatter fields (like the POC name/link) that are authored in Obsidian, not the DB,
        # must be read back before each note is regenerated or they'd be lost on every sync.
        existing_job_notes = self._index_existing_job_notes()

        # Prepare paths for NetworkGraphBuilder
        user_cfg = self.config.get("user", {})
        conn_path = user_cfg.get("linkedin_connections_path") or self.config.get("network", {}).get("connections_path")
        connections_path = pathlib.Path(conn_path or "data/Connections.csv")

        builder = NetworkGraphBuilder(connections_path, metadata_path=user_cfg.get("linkedin_metadata_path"))
        all_connections = builder.connections

        # Prepare Lookups
        company_to_jobs = {}
        company_to_people = {}
        job_to_requests = {}
        person_to_requests = {}

        # 1. Fetch Requests (Referrals)
        all_requests = self.extractor.db.get_all_requests()
        for req in all_requests:
            jid = req["job_id"]
            pname = req["connection_name"]

            if jid not in job_to_requests:
                job_to_requests[jid] = []
            job_to_requests[jid].append(req)

            if pname not in person_to_requests:
                person_to_requests[pname] = []
            person_to_requests[pname].append(req)

        for j in jobs:
            co = j["details"].company
            if co:
                if co not in company_to_jobs:
                    company_to_jobs[co] = []
                company_to_jobs[co].append(j)

        for p in all_connections:
            co = p.company
            if co:
                if co not in company_to_people:
                    company_to_people[co] = []
                company_to_people[co].append(p)

        # 1. Sync People
        for person in all_connections:
            # Jobs at their company
            p_company = person.company
            associated_jobs = []
            if p_company in company_to_jobs:
                for j in company_to_jobs[p_company]:
                    associated_jobs.append(
                        {
                            "title": j["details"].title,
                            "filename": f"{j['details'].title} - {j['details'].company}",
                            "status": "To Apply",  # Optional: get from DB
                        }
                    )

            if not associated_jobs:
                continue

            person_reqs = person_to_requests.get(person.full_name, [])
            content = self.template_manager.render_person(
                person, jobs=associated_jobs, referrals=person_reqs, resume_data=self.resume_data
            )
            self.vault_manager.write_file(content, f"{person.full_name}.md", "people")

        # 2. Sync Jobs
        for j in jobs:
            job = j["details"]
            score = j["score"]

            # People at this company
            people_at_co = []
            if job.company in company_to_people:
                for p in company_to_people[job.company]:
                    people_at_co.append({"name": p.full_name, "filename": f"{p.full_name}", "title": p.position})

            # specialization = self._determine_specialization(job)
            specialization = job.specialization
            job_reqs = job_to_requests.get(job.id, [])
            status_display = STATUS_DB_TO_DISPLAY.get(j.get("status"), "ToApply")
            existing_note = existing_job_notes.get(str(job.id), {})
            existing_fm = existing_note.get("frontmatter", {})
            poc_name = existing_fm.get("poc_name") or ""
            poc_link = existing_fm.get("poc_link") or ""
            content = self.template_manager.render_job(
                job,
                score,
                specialization=specialization,
                people=people_at_co,
                referrals=job_reqs,
                resume_data=self.resume_data,
                status=status_display,
                applied_at=j.get("applied_at"),
                poc_name=poc_name,
                poc_link=poc_link,
            )
            filename = f"{job.title} - {job.company}.md"
            # Determine subfolder based on score bucket
            start = (score.score // bucket_size) * bucket_size
            end = start + bucket_size - 1
            new_path = self.vault_manager.write_file(content, filename, "jobs", subfolder=f"Score_{start}-{end}")

            # If the job's score bucket changed since the last sync, its old subfolder copy is
            # now stale - remove it so the job doesn't end up duplicated across two subfolders.
            for old_path in existing_note.get("paths", []):
                if old_path != new_path:
                    try:
                        old_path.unlink()
                        logger.info(f"Removed stale duplicate job note: {old_path}")
                    except Exception as e:
                        logger.warning(f"Could not remove stale duplicate {old_path}: {e}")

        # 3. Sync Companies
        all_companies = set(list(company_to_jobs.keys()) + list(company_to_people.keys()))
        for co in all_companies:
            co_jobs = []
            if co in company_to_jobs:
                for j in company_to_jobs[co]:
                    co_jobs.append(
                        {
                            "title": j["details"].title,
                            "filename": f"{j['details'].title} - {j['details'].company}",
                            "status": "Active",
                        }
                    )

            if not co_jobs:
                continue

            co_people = []
            if co in company_to_people:
                for p in company_to_people[co]:
                    co_people.append({"name": p.full_name, "filename": f"{p.full_name}", "title": p.position})

            content = self.template_manager.render_company(name=co, jobs=co_jobs, people=co_people)
            self.vault_manager.write_file(content, f"{co}.md", "companies")

    def _index_existing_job_notes(self) -> dict[str, dict[str, Any]]:
        """Maps job_id -> {"frontmatter": dict, "paths": [Path, ...]} for job notes already in
        the vault. A job_id can have multiple paths if it has a stale duplicate left behind in
        an old Score_X-Y subfolder from before its score last changed."""
        jobs_folder = self.vault_manager.vault_path / self.vault_manager.folders.get("jobs", "Jobs")
        index: dict[str, dict[str, Any]] = {}
        if not jobs_folder.exists():
            return index

        for file_path in jobs_folder.rglob("*.md"):
            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning(f"Could not read {file_path} while indexing existing job notes: {e}")
                continue
            frontmatter = _read_frontmatter(content)
            job_id = _extract_job_id(content, frontmatter)
            if job_id is None:
                continue
            entry = index.setdefault(job_id, {"frontmatter": {}, "paths": [], "_mtime": -1.0})
            entry["paths"].append(file_path)
            # Prefer the most recently modified copy's frontmatter for preserved fields.
            mtime = file_path.stat().st_mtime
            if mtime > entry["_mtime"]:
                entry["frontmatter"] = frontmatter
                entry["_mtime"] = mtime
        return index

    def _load_analysis(self, job_data: dict[str, Any]) -> ScoringResult:
        """Loads analysis for a job from DB record, returning a default if not found."""
        analysis_json = job_data.get("analysis_data")
        if analysis_json:
            try:
                data = json.loads(analysis_json)
                return ScoringResult(**data)
            except Exception as e:
                logger.warning(f"Failed to load analysis for job {job_data.get('id')}: {e}")

        # Default "Unscored" Result
        return ScoringResult(
            score=0,
            reasoning="Job has not been scored yet. Run 'score' command.",
            matching_skills=[],
            missing_skills=[],
        )

    def prune_vault(self) -> None:
        """Removes job files from the vault that are no longer in the database."""
        logger.info("Pruning Obsidian vault...")

        if not self.extractor.db:
            logger.error("Database not available for pruning.")
            return

        db_jobs = self.extractor.db.get_all_jobs(limit=10000)
        db_ids: set[str] = {str(job["id"]) for job in db_jobs}
        unscraped_ids: set[str] = {str(job["id"]) for job in db_jobs if job.get("status") == "discovered"}
        auto_rejected_ids: set[str] = {str(job["id"]) for job in db_jobs if _is_auto_rejected(job)}

        jobs_folder = self.vault_manager.vault_path / self.vault_manager.folders.get("jobs", "Jobs")
        if not jobs_folder.exists():
            logger.warning(f"Jobs folder not found at {jobs_folder}")
            return

        removed_count = 0
        for file_path in jobs_folder.rglob("*.md"):
            try:
                content = file_path.read_text(encoding="utf-8")
                job_id = _extract_job_id(content, _read_frontmatter(content))
                if job_id is not None:
                    if job_id not in db_ids:
                        logger.info(f"Removing orphaned job note: {file_path.name} (ID: {job_id})")
                        file_path.unlink()
                        removed_count += 1
                    elif job_id in unscraped_ids:
                        logger.info(f"Removing unscraped job note: {file_path.name} (ID: {job_id})")
                        file_path.unlink()
                        removed_count += 1
                    elif job_id in auto_rejected_ids:
                        logger.info(f"Removing auto-rejected (score 0) job note: {file_path.name} (ID: {job_id})")
                        file_path.unlink()
                        removed_count += 1
            except Exception as e:
                logger.warning(f"Could not process {file_path}: {e}")

        # 2. Prune People and Companies (ones with no jobs)
        for folder_key in ["people", "companies"]:
            folder = self.vault_manager.vault_path / self.vault_manager.folders.get(folder_key)
            if not folder.exists():
                continue

            for file_path in folder.glob("*.md"):
                try:
                    content = file_path.read_text(encoding="utf-8")
                    if "No jobs found at this company." in content or "jobs: []" in content:
                        logger.info(f"Removing unlinked note from {folder_key}: {file_path.name}")
                        file_path.unlink()
                        removed_count += 1
                except Exception as e:
                    logger.warning(f"Error pruning {file_path}: {e}")

        logger.info(f"Pruning complete. Removed {removed_count} Orphaned notes.")

    def sync_from_obsidian(self) -> None:
        """Parses Obsidian job notes to update status and other metadata in the database."""
        logger.info("Syncing back from Obsidian to database...")

        if not self.extractor.db:
            logger.error("Database not available for sync-back.")
            return

        jobs_folder = self.vault_manager.vault_path / self.vault_manager.folders.get("jobs", "Jobs")
        if not jobs_folder.exists():
            logger.warning(f"Jobs folder not found at {jobs_folder}")
            return

        updated_count = 0
        for file_path in jobs_folder.rglob("*.md"):
            try:
                content = file_path.read_text(encoding="utf-8")
                frontmatter = _read_frontmatter(content)

                job_id = frontmatter.get("job_id")
                if job_id is None:
                    continue
                job_id = str(job_id)

                status_text = frontmatter.get("status")
                found_status = STATUS_DISPLAY_TO_DB.get(status_text)

                # The "applied" checkbox is a quick toggle for the common ToApply <-> Applied
                # transition. It only takes effect at that boundary; finer states (Interviewing,
                # Rejected, Offered, Wishlist) are set via the `status` property directly.
                applied_checkbox = frontmatter.get("applied")
                if applied_checkbox is True and status_text == "ToApply":
                    found_status = "applied"
                elif applied_checkbox is False and status_text == "Applied":
                    found_status = "to_apply"

                if found_status:
                    if self.extractor.db.job_exists(job_id):
                        self.extractor.db.update_job_status(job_id, found_status)
                        updated_count += 1
                    else:
                        logger.warning(
                            f"Job ID {job_id} found in Obsidian ({file_path.name}) but not in database. Skipping."
                        )

            except Exception as e:
                logger.warning(f"Error processing {file_path} for sync-back: {e}")

        logger.info(f"Sync-back complete. Updated {updated_count} jobs.")
