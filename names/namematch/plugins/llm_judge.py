"""LLM adjudication of hard name-match cases (opt-in, off by default).

Use only for the **review** bucket the deterministic matcher can't resolve
(rare transliterations, nicknames, honorific-laden author strings). Keeps the
core fully local; this plugin is the single place network/LLM use is allowed,
behind an explicit flag.

Default provider is Claude (Anthropic). Model ids per the project's claude-api
reference; ``claude-haiku-*`` is the cost-appropriate extractor/judge tier.
The function builds a strict JSON prompt and returns a normalized verdict.
"""
from __future__ import annotations

from dataclasses import dataclass

_PROMPT = """You are adjudicating whether two name strings refer to the SAME person.
Consider transliteration variants, nicknames/diminutives, initials, honorifics,
and culture-specific structure (Arabic nasab/forefather chains, Spanish two
surnames, Portuguese/Brazilian multi-surnames). Be precision-oriented: only say
"same" when genuinely confident.

Name A: {a}
Name B: {b}
Context: {context}

Reply ONLY with JSON: {{"same": true|false, "confidence": 0.0-1.0, "reason": "..."}}"""


@dataclass
class Verdict:
    same: bool
    confidence: float
    reason: str


def judge(a: str, b: str, context: str = "", model: str = "claude-haiku-4-5-20251001") -> Verdict:
    """Ask an LLM to adjudicate. Raises if the provider SDK isn't installed."""
    try:
        import anthropic  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise NotImplementedError(
            "llm_judge needs `pip install anthropic` and ANTHROPIC_API_KEY. "
            "This is the only component that makes a network call; it stays off "
            "unless explicitly invoked."
        ) from exc
    import json

    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model,
        max_tokens=256,
        messages=[{"role": "user", "content": _PROMPT.format(a=a, b=b, context=context or "none")}],
    )
    data = json.loads(msg.content[0].text)
    return Verdict(bool(data["same"]), float(data["confidence"]), str(data.get("reason", "")))
