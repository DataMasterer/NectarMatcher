"""Entity-type classification (person / book title / organization) — opt-in.

Wraps **GLiNER**, a lightweight, local, zero-shot NER model. Given custom labels
at runtime it classifies a short string by linguistic *structure*, so it
generalizes to names absent from any gazetteer — Arabic, classical (e.g.
عبد الرحمن بن خلدون), and brand-new authors alike. Fully local (CPU, no API), but
a downloaded model + torch, so it is opt-in: ``pip install 'namematch[entity-type]'``.
The deterministic core never depends on it.

Layer it AFTER the cheap deterministic signals (junk regex, book-title match),
which handle the cases GLiNER is weakest on (noisy code/filename strings). It
resolves the fuzzy person↔title boundary the heuristics can't.
"""
from __future__ import annotations

import functools

_LABELS = ["person", "book title", "organization"]
_DEFAULT_MODEL = "urchade/gliner_multi-v2.1"   # multilingual (handles Arabic)


@functools.lru_cache(maxsize=2)
def _load(model_name: str):
    try:
        from gliner import GLiNER
    except ImportError as exc:  # pragma: no cover
        raise NotImplementedError(
            "entity-type classification needs GLiNER: "
            "pip install 'namematch[entity-type]' (installs gliner + CPU torch). "
            "It runs locally, no API; the deterministic core works without it."
        ) from exc
    return GLiNER.from_pretrained(model_name)


def classify(text: str, model: str = _DEFAULT_MODEL, threshold: float = 0.45) -> str:
    """Return ``'person' | 'title' | 'organization' | 'none'`` for a short string.

    The dominant label among spans covering >=50% of the string; ``'none'`` when
    nothing fires. Raises ``NotImplementedError`` if GLiNER isn't installed.
    """
    m = _load(model)
    best, best_score = "none", 0.0
    for e in m.predict_entities(text, _LABELS, threshold=threshold):
        cover = (e["end"] - e["start"]) / max(len(text), 1)
        if cover >= 0.5 and e["score"] > best_score:
            best, best_score = e["label"], e["score"]
    return "title" if best == "book title" else best
