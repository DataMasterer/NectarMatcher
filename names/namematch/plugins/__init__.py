"""Optional ML/LLM refinements — OFF by default.

Importing this package does not import heavy deps; each plugin lazy-imports its
own (``transformers``, ``anthropic`` ...) only when first used, and degrades to
a clear error if the extra isn't installed. The deterministic core never
depends on anything here, preserving DataMasterer's 100%-local default.
"""
from __future__ import annotations

__all__ = ["origin_ml", "llm_judge", "entity_type"]
