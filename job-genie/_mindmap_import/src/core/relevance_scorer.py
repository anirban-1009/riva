import re
from dataclasses import dataclass
from typing import List, Optional

from src.core.ai import LLMClient
from src.ingest.job_details_extractor import JobDetails
from src.ingest.job_searcher import JobSearchResult
from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ScoringResult:
    """Result of the relevance scoring analysis."""

    score: int
    matching_skills: List[str]
    missing_skills: List[str]
    reasoning: str
    required_experience_years: Optional[int] = None


class RelevanceScorer:
    """Scores job listings against a user resume using AI."""

    def __init__(
        self,
        llm_client: LLMClient,
        user_experience_years: Optional[int] = None,
        experience_tolerance_years: int = 0,
    ):
        """
        Initialize the RelevanceScorer.

        Args:
            llm_client: An instance of LLMClient to use for analysis.
            user_experience_years: Maximum years of experience candidate has.
            experience_tolerance_years: How many years above user_experience_years
                a posting's stated requirement may still exceed before the regex
                pre-filter auto-rejects it. Postings within this buffer are passed
                to the LLM instead, which can judge a plausible stretch fit rather
                than a blunt cutoff killing every near-miss (e.g. "3 years"
                required listings when the candidate has 2, which are common
                padding/aspirational requirements rather than hard requirements).
        """
        self.llm = llm_client
        self.user_experience_years = user_experience_years
        self.experience_tolerance_years = experience_tolerance_years

    def _extract_experience_regex(self, text: Optional[str]) -> tuple[Optional[int], bool]:
        """
        Attempt to extract required years of experience using regex.

        Returns a tuple of (years, is_plus_syntax) where:
        - years: The extracted requirement (upper bound for ranges), or None
        - is_plus_syntax: True if the requirement was specified as "X+ years"

        For ranges like "3-5 years", returns (5, False) as a conservative estimate.
        For "5+ years", returns (5, True).
        Returns (None, False) for phrases like "equivalent experience" where no
        specific years are stated.
        """
        if not text:
            return None, False

        # "Equivalent experience" phrasing (e.g. "Bachelor's degree or equivalent
        # experience") is common boilerplate for education requirements and is
        # unrelated to any years-of-experience number stated elsewhere in the
        # description. Only suppress a match when "equivalent" appears near that
        # specific match, not anywhere in the whole text - otherwise a single
        # unrelated "or equivalent experience" mention would disable the filter
        # for the entire posting, even when a clear "5+ years" requirement is
        # stated elsewhere.
        equivalent_pattern = r"\bequivalent\b"
        sentence_boundary = re.compile(r"[.!?\n;]")

        def has_nearby_equivalent(match: re.Match) -> bool:
            # Look for "equivalent" within the same sentence as the years match,
            # rather than the whole text, so unrelated mentions elsewhere in the
            # description don't suppress an unambiguous years requirement.
            preceding = sentence_boundary.finditer(text, 0, match.start())
            start = max((m.end() for m in preceding), default=0)
            following = sentence_boundary.search(text, match.end())
            end = following.start() if following else len(text)
            return bool(re.search(equivalent_pattern, text[start:end], re.IGNORECASE))

        # Pattern captures: primary number, optional + indicator, optional range upper
        pattern = r"(\d{1,2})(\+)?\s*(?:(?:to|-)\s*(\d{1,2}))?\s*(?:years?|yrs?)\s*(?:of\s*)?(?:[\w\s]{0,20})?(?:experience|exp)"
        for match in re.finditer(pattern, text, re.IGNORECASE):
            if has_nearby_equivalent(match):
                continue
            primary = int(match.group(1))
            has_plus = match.group(2) is not None
            upper = match.group(3)
            if upper is not None:
                # For ranges like "3-5 years", use the upper bound as conservative estimate
                return int(upper), False
            return primary, has_plus

        # Fallback: check for just a number followed by years/exp at end (no "experience" keyword)
        simple_pattern = r"(\d{1,2})(\+)?\s*(?:years?|yrs?)\b"
        for simple_match in re.finditer(simple_pattern, text, re.IGNORECASE):
            if has_nearby_equivalent(simple_match):
                continue
            return int(simple_match.group(1)), simple_match.group(2) is not None

        return None, False

    def score_job(self, resume_text: str, job_details: JobDetails) -> Optional[ScoringResult]:
        """
        Analyzes the relevance of a job to the user's resume.

        Args:
            resume_text: Raw text extracted from the user's resume.
            job_details: Detailed information about the job.

        Returns:
            ScoringResult if successful, None otherwise.
        """
        extracted_exp, is_plus_syntax = self._extract_experience_regex(job_details.description)

        # 1. Regex pre-filtering for experience. A tolerance buffer lets postings
        # asking for a modest stretch above the candidate's years still reach the
        # LLM (aspirational/padded requirements are common), while a bigger gap
        # is auto-rejected without spending an LLM call.
        if extracted_exp is not None and self.user_experience_years is not None:
            effective_limit = self.user_experience_years + self.experience_tolerance_years
            if is_plus_syntax:
                # "5+ years" means 5 or more, so a candidate with exactly 5 years
                # still qualifies - only reject when they fall short of the floor.
                if effective_limit < extracted_exp:
                    logger.info(
                        f"Regex filter caught job '{job_details.title}': requires {extracted_exp}+ years, candidate has {self.user_experience_years} (+{self.experience_tolerance_years} tolerance)."
                    )
                    return ScoringResult(
                        score=0,
                        matching_skills=[],
                        missing_skills=["Required Experience"],
                        reasoning=f"Regex filter: Job requires {extracted_exp}+ years of experience, but candidate has a maximum of {self.user_experience_years} years.",
                        required_experience_years=extracted_exp,
                    )
            elif extracted_exp > effective_limit:
                # For ranges like "3-5 years", upper bound > candidate experience
                logger.info(
                    f"Regex filter caught job '{job_details.title}': requires {extracted_exp} years, candidate has {self.user_experience_years} (+{self.experience_tolerance_years} tolerance)."
                )
                return ScoringResult(
                    score=0,
                    matching_skills=[],
                    missing_skills=["Required Experience"],
                    reasoning=f"Regex filter: Job requires {extracted_exp} years of experience, but candidate has a maximum of {self.user_experience_years} years.",
                    required_experience_years=extracted_exp,
                )

        prompt = self._construct_prompt(resume_text, job_details)
        system_instruction = (
            "You are an expert career coach and technical recruiter. "
            "Analyze the job description against the resume provided. "
            "Be objective and critical. Provide high-quality feedback."
        )

        try:
            logger.info(f"Scoring job '{job_details.title}' at '{job_details.company}'")
            json_response = self.llm.generate_json(prompt, system_instruction=system_instruction)

            if not json_response:
                logger.error("Empty JSON response from LLM during scoring.")
                return None

            return ScoringResult(
                score=int(json_response.get("score", 0)),
                matching_skills=json_response.get("matching_skills", []),
                missing_skills=json_response.get("missing_skills", []),
                reasoning=json_response.get("reasoning", ""),
                required_experience_years=json_response.get("required_experience_years", extracted_exp),
            )
        except Exception as e:
            logger.error(f"Error during relevance scoring: {e}")
            return None

    def _construct_prompt(self, resume_text: str, job_details: JobDetails) -> str:
        """Constructs the prompt for the LLM."""
        prompt = f"""
Analyze the suitability of this candidate for the following job.

### Resume Content:
{resume_text}

### Job Title:
{job_details.title}

### Company:
{job_details.company}

### Job Description:
{job_details.description}
"""
        if self.user_experience_years is not None:
            tolerance = self.experience_tolerance_years
            stretch_note = (
                f" A requirement up to {tolerance} year(s) above this is a plausible stretch - "
                "weigh it against skill match rather than auto-penalizing."
                if tolerance
                else ""
            )
            prompt += (
                f"\n### Candidate Experience Context:\nIMPORTANT: The candidate has **{self.user_experience_years} years** "
                f"of professional experience.{stretch_note} If the job requires meaningfully more overall experience than "
                f"the candidate has (accounting for the stretch above), the candidate is unqualified. Heavily penalize the "
                "score (score < 30).\n"
            )

        prompt += """
### Evaluation Criteria:
1. **Score (0-100)**: How well do the candidate's skills and experience align with the job requirements?
2. **Matching Skills**: List 3-7 key technical or soft skills found in both the resume and the job.
3. **Missing Skills**: List 3-7 key requirements from the job that are missing or weak in the resume.
4. **Reasoning**: Provide a 2-3 sentence explanation for the score.
5. **Required Experience (Years)**: The minimum years of experience categorically strictly required by the job (integer). Return 0 if not explicitly mentioned.

### Output Format:
Provide the result ONLY as a raw JSON object with these keys:
- "score": integer
- "matching_skills": list of strings
- "missing_skills": list of strings
- "reasoning": string
- "required_experience_years": integer
"""
        return prompt


class FastScorer:
    """Performs rapid keyword-based scoring without LLM calls."""

    def __init__(self, keywords: List[str]):
        """
        Initialize with a list of target keywords.

        Args:
            keywords: List of skills or technologies to match.
        """
        self.keywords = [k.lower() for k in keywords]

    def score_result(self, result: JobSearchResult) -> int:
        """
        Calculates a simple overlap score for a search result.

        Args:
            result: The JobSearchResult to score.

        Returns:
            int: A score from 0-100 based on keyword density in title.
        """
        if not self.keywords:
            return 0

        title = result.title.lower()
        matches = sum(1 for kw in self.keywords if kw in title)

        # Title matches are weighted heavily
        score = (matches / len(self.keywords)) * 100
        # Boost if title contains exact matches for key skills
        if matches > 0:
            score = min(100, score + 20)

        return int(score)
