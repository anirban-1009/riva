import re

_REASONING_KEYWORDS = re.compile(
    r"\b("
    r"step[- ]by[- ]step|explain (your |the )?reasoning|think (it )?through|"
    r"prove|derive|solve|calculate|compute|equation|algorithm|optimi[sz]e|"
    r"debug|trade-?offs?|design (a|an|the)|architecture|strategy|plan (a|an|out)|"
    r"compare and contrast|pros and cons|why (does|is|are|do)|analy[sz]e|"
    r"multi-?step|reason about"
    r")\b",
    re.IGNORECASE,
)

_MATH_EXPRESSION_PATTERN = re.compile(r"\d+\s*[+\-*/^%]\s*\d+")

_LONG_PROMPT_WORD_THRESHOLD = 80


def should_use_extended_thinking(messages: list[dict[str, str]]) -> bool:
    """Heuristically decide whether a prompt warrants extended thinking.

    Keeps simple prompts fast by only asking for the model's reasoning mode
    when the conversation shows signs of needing multi-step reasoning:
    explicit reasoning language, math expressions, or a long/complex ask.
    Everything else runs without thinking, which responds faster.
    """
    user_text = " ".join(
        msg.get("content", "") for msg in messages if msg.get("role") == "user"
    )
    if not user_text.strip():
        return False

    if _REASONING_KEYWORDS.search(user_text):
        return True
    if _MATH_EXPRESSION_PATTERN.search(user_text):
        return True
    if len(user_text.split()) > _LONG_PROMPT_WORD_THRESHOLD:
        return True

    return False
