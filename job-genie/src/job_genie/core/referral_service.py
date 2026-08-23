import pathlib
from typing import Any

from job_genie.core.ai import LLMClient
from job_genie.core.network_graph import Connection, NetworkGraphBuilder
from job_genie.ingest.job_details_extractor import JobDetails, JobDetailsExtractor
from job_genie.utils.logger import get_logger

logger = get_logger(__name__)


class ReferralService:
    """Manages the generation and storage of referral messages."""

    def __init__(self, llm_client: LLMClient, config: dict[str, Any]):
        """
        Initialize the ReferralService.

        Args:
            llm_client: LLM client for message generation.
            config: Application configuration.
        """
        self.llm = llm_client
        self.config = config
        self.db = JobDetailsExtractor(None).db  # Shared DB connection

    def find_potential_connections(self, job: JobDetails) -> list[Connection]:
        """Finds connections at the job's company."""
        user_cfg = self.config.get("user", {})
        conn_path = user_cfg.get("linkedin_connections_path") or self.config.get("network", {}).get("connections_path")
        connections_path = pathlib.Path(conn_path or "data/Connections.csv")

        if not connections_path.exists():
            return []

        builder = NetworkGraphBuilder(connections_path, metadata_path=user_cfg.get("linkedin_metadata_path"))
        return builder.find_matches(job)

    def generate_message(
        self, job: JobDetails, connection: Any, resume_data: dict[str, Any], max_chars: int = 250
    ) -> str:
        """
        Generates a personalized referral request message.

        The message is limited to the specified max_chars to fit within
        the target platform's (e.g. LinkedIn) constraints.
        Enriches the message with experience details and ensures diversity.
        """
        # 1. Format skills nicely
        skills_str = "None identified"
        if isinstance(resume_data.get("skills"), dict):
            all_skills = []
            for items in resume_data["skills"].values():
                if isinstance(items, list):
                    all_skills.extend(items)
            skills_str = ", ".join(all_skills[:8])

        # 2. Extract Experience info (config.yaml takes precedence over resume.json)
        user_cfg = self.config.get("user", {})
        experience_list = resume_data.get("experience", [])
        total_exp_years = user_cfg.get("total_experience_years") or resume_data.get(
            "total_experience_years", len(experience_list) * 2
        )
        current_role = user_cfg.get("current_role") or resume_data.get("job_title", "Software Engineer")

        if experience_list and not user_cfg.get("current_role") and not resume_data.get("job_title"):
            current_role = experience_list[0].get("title", current_role)

        connection_name = getattr(connection, "full_name", "Professional")
        first_name = connection_name.split()[0] if " " in connection_name else connection_name
        candidate_first_name = resume_data.get("first_name", "Anirban")
        candidate_full_name = f"{candidate_first_name} {resume_data.get('last_name', 'Sikdar')}"

        prompt = f"""
        Generate a highly personalized, natural, and polite LinkedIn message to ask for a job referral.
        
        CONTEXT:
        - Target: {job.title} at {job.company}
        - To: {connection_name}
        - From: {candidate_full_name}
        - Current Role: {current_role}
        - Total Experience: ~{total_exp_years}+ years
        - Key Skills: {skills_str}

        CRITICAL GUIDELINES:
        1. LENGTH: Must be under {max_chars} characters.
        2. NO ROBOTIC TEMPLATES: Avoid "I am writing to express interest". Use natural spoken English.
        3. TONE: Pick ONE natural opening — a compliment on their work/profile, a shared-company reference, or a direct but warm approach. Do not mix styles.
        4. EXPERIENCE: Briefly mention {total_exp_years}+ years of experience or the current role {current_role} if it adds value.
        5. CALL TO ACTION: Ask if they'd be open to sharing my profile/referring me, or if they have advice for the {job.title} role.
        6. NO placeholders [like this], NO subject lines.

        OUTPUT FORMAT (STRICT):
        Reply with ONLY the final message text, ready to send as-is.
        Do NOT include multiple options, labels (e.g. "Option 1", "Style A"), headers, bullet points, markdown, explanations, or any text other than the message itself.

        Example (format only, write your own content):
        Hi {first_name}, I'm {candidate_first_name}...
        """
        # Cap output tokens as a hard backstop against verbose/multi-option generations,
        # independent of whether the model follows the prompt's formatting instructions.
        max_tokens = max(60, max_chars // 2)
        raw_message = self.llm.generate(prompt, max_tokens=max_tokens).strip()
        message = self._extract_single_message(raw_message)

        if len(message) > max_chars:
            logger.warning(
                f"Generated message exceeds {max_chars} chars ({len(message)}). Keeping full message as requested."
            )

        return message

    @staticmethod
    def _extract_single_message(text: str) -> str:
        """
        Safety net for models that ignore the single-message instruction and emit
        preamble, multiple labeled options, or markdown formatting anyway.
        Picks the first paragraph that looks like an actual message.
        """
        text = text.strip().strip('"').strip("'")

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        label_markers = ("option", "style", "approach", "**", "###", "here are", "here's")

        for paragraph in paragraphs:
            # Drop label/preamble lines (e.g. "**Option 1: ...**") but keep the
            # actual message line(s) that follow within the same paragraph.
            lines = [line for line in paragraph.split("\n") if line.strip()]
            lines = [line for line in lines if not any(line.strip().lower().startswith(m) for m in label_markers)]
            if lines:
                return "\n".join(lines).strip().strip('"').strip("'")

        return text

    def save_referral(self, job_id: str, connection_name: str, message: str, profile_url: str = "https://linkedin.com"):
        """Saves the referral request to the database."""
        if self.db:
            self.db.save_request(
                job_id=job_id, connection_name=connection_name, profile_url=profile_url, message=message
            )
            return True
        return False
