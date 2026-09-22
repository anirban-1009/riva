import time
import re
from dataclasses import dataclass
from typing import Optional, Dict, Any
import spacy
import laya_mlx as laya

@dataclass
class AgentMemoryEvent:
    query: str
    should_extract_memory: bool
    is_explicit: bool
    latency_ms: float

class MemoryRouter:
    """
    Pragmatic Memory Router for Riva.

    This class handles high-recall triage to determine if a user's query
    contains durable personal information worth extracting into memory.
    """
    def __init__(self, spacy_model: str = "en_core_web_sm", durable_threshold: float = 0.55):
        self.durable_threshold = durable_threshold

        # 1. Fast Directives & Inquiries (< 0.1 ms)
        self.explicit_memory_re = re.compile(
            r"^(please\s+)?(remember|keep in mind|take note|don't forget|forget)\b",
            re.IGNORECASE,
        )
        self.question_and_command_re = re.compile(
            r"^(what|how|why|when|where|who|which|can|could|would|should|give|show|tell|help|explain)\b",
            re.IGNORECASE,
        )

        # 2. Fast spaCy: Only morphologizer/tagger (disable heavy parser/ner)
        try:
            self.nlp = spacy.load(spacy_model, disable=["ner", "parser", "textcat"])
        except OSError:
            spacy.cli.download(spacy_model)
            self.nlp = spacy.load(spacy_model, disable=["ner", "parser", "textcat"])

        # Only subject/possessive pronouns that signal the speaker is asserting personal status
        self.personal_subjects = {"i", "my", "we", "our"}

        # 3. Laya MLX Binary Contrast
        self.laya_schema = {
            "memory_category": {
                "type": "choice",
                "instructions": (
                    "Determine what kind of information the speaker is sharing about themselves:\n"
                    "- 'durable_profile': Permanent life facts (job, employer, home location, family members, pets, medical conditions, allergies, long-term habits/preferences).\n"
                    "- 'momentary_state': Ephemeral actions (meals eaten today, current physical fatigue, immediate errands, temporary chores, acute headache)."
                ),
                "criteria": ["durable_profile", "momentary_state"],
            }
        }

        # Initialize MLX engine with graph caching
        self.agent = laya.load("aac6fef/laya-mlx", compile=True)
        # Priming warm-up run
        _ = self.agent.predict("I work at Apple", self.laya_schema)

    def route(self, query: str) -> AgentMemoryEvent:
        t0 = time.perf_counter()
        clean = query.strip()

        if not clean:
            return AgentMemoryEvent(query, False, False, 0.0)

        # Stage 1: Explicit Directives ("Remember that...")
        if self.explicit_memory_re.match(clean):
            return AgentMemoryEvent(
                query=query,
                should_extract_memory=True,
                is_explicit=True,
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        # Stage 2: Question / Command Filter
        # If it starts with question words/verbs (e.g. "Can you give me...", "How do I optimize...")
        # and ends with '?' OR doesn't start with a personal assertion, bypass immediately!
        if self.question_and_command_re.match(clean):
            if clean.endswith("?") or not clean.lower().startswith(("i ", "my ", "we ", "our ")):
                return AgentMemoryEvent(
                    query=query,
                    should_extract_memory=False,
                    is_explicit=False,
                    latency_ms=(time.perf_counter() - t0) * 1000,
                )

        # Stage 3: Linguistic check for 1st-person subject
        doc = self.nlp(clean)
        has_personal_subject = any(t.lemma_.lower() in self.personal_subjects for t in doc)

        if not has_personal_subject:
            return AgentMemoryEvent(
                query=query,
                should_extract_memory=False,
                is_explicit=False,
                latency_ms=(time.perf_counter() - t0) * 1000,
            )

        # Stage 4: Semantic Arbiter (Laya MLX) (~28 ms)
        laya_out = self.agent.predict(clean, self.laya_schema)
        intent = laya_out.get("answers", {}).get("memory_category", {})

        choice = intent.get("choice")
        probs = intent.get("probabilities", {})

        p_durable = probs.get("durable_profile", 0.0)
        p_momentary = probs.get("momentary_state", 0.0)

        # Calibrated decision: durable must win AND beat momentary by a positive margin
        should_store = (choice == "durable_profile") and (p_durable > p_momentary) and (p_durable >= self.durable_threshold)

        return AgentMemoryEvent(
            query=query,
            should_extract_memory=should_store,
            is_explicit=False,
            latency_ms=(time.perf_counter() - t0) * 1000,
        )


_memory_router: Optional[MemoryRouter] = None


def get_memory_router() -> MemoryRouter:
    """Get or lazily initialize the singleton MemoryRouter instance."""
    global _memory_router
    if _memory_router is None:
        _memory_router = MemoryRouter()
    return _memory_router


def route_memory(query: str) -> AgentMemoryEvent:
    """Evaluate query through the MemoryRouter and return an AgentMemoryEvent."""
    return get_memory_router().route(query)
