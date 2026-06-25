"""namematch — culture-aware human-name detection & matching.

Deterministic, fully local core (no network, no models) built on the existing
``DataMasterer/namesdb`` corpus. Optional ML/LLM refinements live in
``namematch.plugins`` and are off by default.

Public API::

    from namematch import detect, match, parse

    detect("صلاح الدين")          -> Detection(script="Arabic", origins=...)
    parse("Maria de la Cruz", culture="Spanish")
    match("صلاح", "صلاح الدين")    -> MatchResult(bucket="match", ...)
"""
from __future__ import annotations

from .culture import infer_culture
from .dedup import DedupResult, dedup
from .detect import Detection, detect
from .match import MatchResult, match, token_sim
from .parse import ParsedName, parse
from .script import ScriptProfile, detect_script
from .translit import candidates as transliteration_candidates
from .translit import transliterate

__all__ = [
    "detect", "Detection",
    "match", "MatchResult", "token_sim",
    "dedup", "DedupResult",
    "parse", "ParsedName",
    "detect_script", "ScriptProfile",
    "infer_culture",
    "transliterate", "transliteration_candidates",
]

__version__ = "0.1.0"
