"""Unicode-script detection for name strings.

Pure stdlib. Classifies each letter into a writing system by Unicode block
so callers can answer "is this Arabic / Latin / Hebrew / Cyrillic ...?"
before any lexicon work. This is the first, cheapest, fully-deterministic
signal in the detection waterfall.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

# Block ranges we care about for human names. Order matters only for the
# first match; ranges are disjoint.
_BLOCKS: list[tuple[int, int, str]] = [
    (0x0600, 0x06FF, "Arabic"),
    (0x0750, 0x077F, "Arabic"),          # Arabic Supplement
    (0x08A0, 0x08FF, "Arabic"),          # Arabic Extended-A
    (0xFB50, 0xFDFF, "Arabic"),          # Presentation Forms-A
    (0xFE70, 0xFEFF, "Arabic"),          # Presentation Forms-B
    (0x0590, 0x05FF, "Hebrew"),
    (0x0400, 0x04FF, "Cyrillic"),
    (0x0370, 0x03FF, "Greek"),
    (0x0900, 0x097F, "Devanagari"),
    (0x4E00, 0x9FFF, "Han"),
    (0x3040, 0x30FF, "Kana"),
    (0xAC00, 0xD7AF, "Hangul"),
    (0x0000, 0x024F, "Latin"),           # Basic + Latin-1 + Extended-A/B
    (0x1E00, 0x1EFF, "Latin"),           # Latin Extended Additional (ḥ, ṣ ...)
    (0x2C60, 0x2C7F, "Latin"),
]


def _script_of_char(ch: str) -> str | None:
    cp = ord(ch)
    for lo, hi, name in _BLOCKS:
        if lo <= cp <= hi:
            return name
    return None


@dataclass
class ScriptProfile:
    """Distribution of writing systems across the letters of a string."""

    counts: dict[str, int] = field(default_factory=dict)
    total_letters: int = 0

    @property
    def dominant(self) -> str | None:
        if not self.counts:
            return None
        return max(self.counts, key=self.counts.get)

    def share(self, script: str) -> float:
        if not self.total_letters:
            return 0.0
        return self.counts.get(script, 0) / self.total_letters

    @property
    def is_mixed(self) -> bool:
        """True when no single script holds >=90% of the letters."""
        d = self.dominant
        return d is not None and self.share(d) < 0.90


def detect_script(text: str) -> ScriptProfile:
    """Return a :class:`ScriptProfile` for *text* (letters only counted)."""
    counts: dict[str, int] = {}
    total = 0
    for ch in text:
        if not (ch.isalpha() or unicodedata.combining(ch)):
            continue
        s = _script_of_char(ch)
        if s is None:
            continue
        # Combining marks inherit the run's script and shouldn't sway counts.
        if unicodedata.combining(ch):
            continue
        counts[s] = counts.get(s, 0) + 1
        total += 1
    return ScriptProfile(counts=counts, total_letters=total)
