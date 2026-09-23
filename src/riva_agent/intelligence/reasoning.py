import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import laya_mlx as laya
import numpy as np
import spacy


class ReasoningEffort(Enum):
    NONE = "none"
    LOW = "low"
    HIGH = "high"


@dataclass
class HybridDecision:
    query: str
    requires_thinking: bool
    effort_level: ReasoningEffort
    source: str
    latency_ms: float
    confidence: float = 1.0
    debug_info: Dict[str, Any] = field(default_factory=dict)


class ThinkingRouter:

    def __init__(self, spacy_model: str = "en_core_web_sm"):
        try:
            self.nlp = spacy.load(spacy_model, exclude=["ner"])
        except OSError:
            spacy.cli.download(spacy_model)
            self.nlp = spacy.load(spacy_model, exclude=["ner"])

        # Stage 1: Fast Regex Patterns
        self.social_openers = re.compile(
            r"^(hi|hello|hey|greetings|thanks|thank you|good (morning|afternoon|evening)|bye|goodbye)\b",
            re.IGNORECASE,
        )
        self.factoid_lookup_re = re.compile(
            r"^(what (is|are|was)|who (is|was|directed)|when (was|is)|where (is|are)) (the )?([a-zA-Z0-9\s]+)\?*$",
            re.IGNORECASE,
        )
        self.explanation_bypass_re = re.compile(
            r"^(give me a summary of|summarize|explain how|what is the formula to|can you explain)\b",
            re.IGNORECASE,
        )
        self.transform_re = re.compile(
            r"^(translate|rephrase|rewrite|paraphrase|convert to (formal|informal))\b",
            re.IGNORECASE,
        )

        # Mathematical expressions (isolated symbols or inequalities)
        # Avoid matching date patterns (e.g. 03/12/2022) as arithmetic division
        self.strict_math_re = re.compile(
            r"(\b[xyzabc]\s*[><=!]=?\s*\d+"                      # x > 5, y <= 2
            r"|\d+\s*[\+\*]\s*\d+"                               # 3 + 4, 2 * 5
            r"|\d+\s+\/\s+\d+"                                  # 10 / 2 (spaces required to avoid dates)
            r"|\b\d+[xyz]\b"                                     # 3x, 4y
            r"|\beigen(value|vector)\b|\bmatrix\b)",
            re.IGNORECASE
        )

        # Word problem heuristics (relational age/quantity patterns)
        self.word_problem_re = re.compile(
            r"(times (older|younger|more|as)|twice as|how (old|many|much) (are|is|will)|assuming integer|sum of|ratio of)",
            re.IGNORECASE,
        )

        # Stage 3: SLM Schema
        self.laya_schema = {
            "complexity": {
                "type": "choice",
                "instructions": (
                    "Rate the computational, algorithmic, or architectural difficulty of answering this query:\n"
                    "- 'none': Chit-chat, casual conversation, lookup questions, summaries, text rewrites, or open-ended ideas.\n"
                    "- 'low': Multi-step instruction following, formatted data extraction, or planning tasks.\n"
                    "- 'high': Mathematical proofs, quantitative word problems, code debugging, or system design trade-offs."
                ),
                "criteria": ["none", "low", "high"],
            }
        }

        self.agent = laya.load("aac6fef/laya-mlx")
        _ = self.agent.predict("warmup", self.laya_schema)

    def route(self, query: str) -> HybridDecision:
        t_start = time.perf_counter()
        clean = query.strip()

        # -------------------------------------------------------------
        # STAGE 1: Deterministic Zero-Cost Fast Paths (< 0.2 ms)
        # -------------------------------------------------------------
        # Greetings & Casual Conversation
        if self.social_openers.match(clean) and len(clean.split()) <= 8:
            return HybridDecision(
                query=query,
                requires_thinking=False,
                effort_level=ReasoningEffort.NONE,
                source="stage1_social_fast_path",
                latency_ms=(time.perf_counter() - t_start) * 1000,
            )

        # Lookups, Formula Recalls, and Explanations
        if self.factoid_lookup_re.match(
            clean
        ) or self.explanation_bypass_re.match(clean):
            return HybridDecision(
                query=query,
                requires_thinking=False,
                effort_level=ReasoningEffort.NONE,
                source="stage1_lookup_explanation_filter",
                latency_ms=(time.perf_counter() - t_start) * 1000,
            )

        # Text Transforms
        if self.transform_re.match(clean):
            return HybridDecision(
                query=query,
                requires_thinking=False,
                effort_level=ReasoningEffort.NONE,
                source="stage1_transform_filter",
                latency_ms=(time.perf_counter() - t_start) * 1000,
            )

        # STAGE 2: Deterministic Reasoning, Math & Logic Detector (< 1.5 ms)
        # -------------------------------------------------------------
        clean_lower = clean.lower()
        doc = self.nlp(clean)
        lemmas = {t.lemma_.lower() for t in doc}
        tokens_text = {t.text.lower() for t in doc}
    
        # 1. High Complexity Technical & Mathematical Keywords
        math_academic_terms = {
            "eigenvalue", "eigenvalues", "eigenvector", "eigenvectors", 
            "matrix", "matrices", "derivative", "integral", "polynomial", 
            "asymptotic", "np-hard", "np-complete", "stochastic"
        }
        has_math_terms = bool(tokens_text & math_academic_terms)
    
        # 2. Algebraic constraints & symbols (e.g. x > 5, y < 2, 3x - 4y)
        has_inequality_or_algebra = bool(
            re.search(r"(\b[a-z]\s*[><=!]=?\s*\d+|\b\d+[a-z]\b|\b[a-z]\s*[\+\-\*\/]\s*[a-z]\b)", clean_lower)
        )
    
        # 3. Quantitative Word Problems (age, ratios, relational math)
        has_word_problem = bool(
            re.search(r"(times\s+(as\s+)?(older|younger|more|as|greater)|twice\s+as|how\s+(old|many|much)\s+(is|are|will)|assuming\s+integer)", clean_lower)
        )
    
        # Combined HIGH reasoning trigger
        if has_math_terms or (has_inequality_or_algebra and "solve" in lemmas) or has_word_problem:
            return HybridDecision(
                query=query,
                requires_thinking=True,
                effort_level=ReasoningEffort.HIGH,
                source="stage2_math_logic_detector",
                latency_ms=(time.perf_counter() - t_start) * 1000
            )
    
        # 4. Structured & Constrained Tasks (LOW effort)
        is_extraction = bool(lemmas & {"extract", "parse", "convert", "format"})
        is_planning = bool(lemmas & {"plan", "schedule", "itinerary", "routine", "diet", "meal"})
        has_constraints = any(t in {"no", "without", "under", "limit", "only", "every"} for t in tokens_text)
    
        if is_extraction or (is_planning and has_constraints):
            return HybridDecision(
                query=query,
                requires_thinking=True,
                effort_level=ReasoningEffort.LOW,
                source="stage2_structured_task_detector",
                latency_ms=(time.perf_counter() - t_start) * 1000
            )

        # -------------------------------------------------------------
        # STAGE 3: Semantic Arbiter (Laya SLM) (~30-35 ms)
        # -------------------------------------------------------------
        laya_res = self.agent.predict(clean, self.laya_schema)
        probs = laya_res["answers"]["complexity"]["probabilities"]

        p_low = probs.get("low", 0.0)
        p_high = probs.get("high", 0.0)

        if p_high >= 0.35:
            effort = ReasoningEffort.HIGH
            requires_thinking = True
        elif (p_low + p_high) >= 0.40:
            effort = ReasoningEffort.LOW
            requires_thinking = True
        else:
            effort = ReasoningEffort.NONE
            requires_thinking = False

        return HybridDecision(
            query=query,
            requires_thinking=requires_thinking,
            effort_level=effort,
            source="stage3_laya_semantic",
            latency_ms=(time.perf_counter() - t_start) * 1000,
            confidence=max(probs.values()),
            debug_info={"probs": probs},
        )

    def route_messages(self, messages: list[dict[str, Any]]) -> HybridDecision:
        """Extract the most recent user prompt and route it."""
        user_query = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content")
                if isinstance(content, str):
                    user_query = content
                elif isinstance(content, list):
                    parts = [
                        p.get("text", "")
                        for p in content
                        if isinstance(p, dict) and p.get("type") == "text"
                    ]
                    user_query = "".join(parts)
                break

        if not user_query.strip():
            return HybridDecision(
                query="",
                requires_thinking=False,
                effort_level=ReasoningEffort.NONE,
                source="empty_user_query",
                latency_ms=0.0,
            )

        return self.route(user_query)


_router: Optional[ThinkingRouter] = None


def get_thinking_router() -> ThinkingRouter:
    """Get or lazily initialize the singleton ThinkingRouter instance."""
    global _router
    if _router is None:
        _router = ThinkingRouter()
    return _router


def decide_reasoning_effort(query: str | list[dict[str, Any]]) -> HybridDecision:
    """Evaluate query through the ThinkingRouter and return a HybridDecision."""
    router = get_thinking_router()
    if isinstance(query, str):
        return router.route(query)
    return router.route_messages(query)


def should_use_extended_thinking(query: str | list[dict[str, Any]]) -> bool:
    """Backward-compatible helper returning True if reasoning is needed."""
    decision = decide_reasoning_effort(query)
    return decision.requires_thinking

