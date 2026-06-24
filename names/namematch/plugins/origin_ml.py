"""Name-origin / nationality classifier plugin (opt-in).

State-of-the-art approaches this wraps (install one to enable):

- **name2nat** (``pip install name2nat``) — bi-GRU over Wikipedia names, 170+
  countries. Lightweight, local once downloaded.
- **NameBERT / mBERT fine-tune** (``transformers``) — current SOTA accuracy;
  larger, needs a model checkpoint.
- **ethnicolr** — US-census-trained race/ethnicity (narrow label space).

Contract: ``classify(name) -> dict[origin, prob]``, same shape as the
deterministic ``detect().origins`` so callers can blend or override. This is a
stub until a backend is wired; it raises a clear, actionable error.
"""
from __future__ import annotations

_BACKEND = None


def classify(name: str) -> dict[str, float]:
    """Return origin->probability. Raises if no ML backend is installed."""
    raise NotImplementedError(
        "origin_ml backend not installed. Enable one of: "
        "`pip install name2nat` (bi-GRU, 170+ countries) or wire a NameBERT "
        "checkpoint via transformers. The deterministic detect() works without it."
    )


def blend(deterministic: dict[str, float], name: str, ml_weight: float = 0.5) -> dict[str, float]:
    """Blend deterministic origins with ML output (when a backend exists)."""
    try:
        ml = classify(name)
    except NotImplementedError:
        return deterministic
    out: dict[str, float] = {}
    for o in set(deterministic) | set(ml):
        out[o] = (1 - ml_weight) * deterministic.get(o, 0.0) + ml_weight * ml.get(o, 0.0)
    total = sum(out.values()) or 1.0
    return {o: round(v / total, 3) for o, v in sorted(out.items(), key=lambda kv: -kv[1])}
