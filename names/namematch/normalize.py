"""Normalization + cross-script romanization folding.

Two jobs:

1. **In-script normalization** — make two spellings of the *same* name in the
   *same* script comparable (strip Arabic tashkeel, unify alef forms; strip
   Latin diacritics, lowercase).

2. **Romanization fold** — collapse a Latin string to a coarse phonetic
   skeleton so transliteration variants of one Arabic name converge:
   ``Salah al-Din`` / ``Salah ad-Deen`` / ``Saladin`` -> a near-common key.
   This is what lets a cross-script matcher align صلاح الدين with its Latin
   forms after the Arabic side is romanized.

Pure stdlib; the actual Arabic->Latin transliteration table lives in
``namesdb/done/transliteration_schemes.csv`` and is loaded by ``lexicon.py``
when a full transliteration (not just a fold) is needed.
"""
from __future__ import annotations

import re
import unicodedata

# --- Arabic ---------------------------------------------------------------

_AR_TASHKEEL = re.compile(
    "[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭ]"
)
_AR_TATWEEL = "ـ"

_AR_NORMALIZE_MAP = {
    "آ": "ا",  # آ alef madda -> ا
    "أ": "ا",  # أ alef hamza above -> ا
    "إ": "ا",  # إ alef hamza below -> ا
    "ٱ": "ا",  # ٱ alef wasla -> ا
    "ى": "ي",  # ى alef maqsura -> ي
    "ة": "ه",  # ة ta marbuta -> ه
    "ؤ": "و",  # ؤ waw hamza -> و
    "ئ": "ي",  # ئ ya hamza -> ي
}


def normalize_arabic(text: str) -> str:
    """Strip tashkeel/tatweel and unify alef/ya/hamza/ta-marbuta forms."""
    text = _AR_TASHKEEL.sub("", text)
    text = text.replace(_AR_TATWEEL, "")
    out = []
    for ch in text:
        out.append(_AR_NORMALIZE_MAP.get(ch, ch))
    return "".join(out)


# --- Latin ----------------------------------------------------------------

def strip_diacritics(text: str) -> str:
    """Remove combining marks (é->e, ḥ->h, ñ->n) via NFKD decomposition."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def normalize_latin(text: str) -> str:
    text = strip_diacritics(text).lower()
    text = re.sub(r"[^a-z\s'-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# --- Romanization fold (cross-script bridge) ------------------------------

# Ordered longest-first so digraphs win over single letters.
_FOLD_RULES: list[tuple[str, str]] = [
    ("aa", "a"), ("ee", "i"), ("oo", "u"), ("ou", "u"), ("ii", "i"),
    ("kh", "x"), ("gh", "g"), ("dh", "d"), ("th", "t"), ("sh", "c"),
    ("ph", "f"), ("ck", "k"), ("dj", "j"), ("tch", "c"),
    (" q", "k"), ("q", "k"), ("c", "k"),  # qaf/kaf collapse
    ("y", "i"), ("w", "u"),
]

# Definite-article prefixes that should not block alignment of the head word.
_ARTICLES = ("al-", "el-", "ad-", "as-", "ash-", "ar-", "an-", "ed-", "ud-")


def romanize_fold(text: str) -> str:
    """Collapse a Latin name token to a coarse consonant-vowel skeleton.

    Designed so transliteration variants converge, not to be reversible.
    Drops doubled letters, folds common digraphs, removes the definite
    article and apostrophes/hamza marks, and squeezes vowels.
    """
    t = normalize_latin(text)
    t = t.replace("'", "").replace("`", "")
    for art in _ARTICLES:
        t = re.sub(rf"\b{art}", "", t)
    for src, dst in _FOLD_RULES:
        t = t.replace(src, dst)
    # squeeze repeated chars
    t = re.sub(r"(.)\1+", r"\1", t)
    # collapse vowels to a single placeholder to absorb a/e/i/o/u variance
    t = re.sub(r"[aeiou]+", "a", t)
    return t.strip()


def fold_tokens(text: str) -> list[str]:
    """Normalize -> split -> romanize_fold each token (drops empties)."""
    return [f for f in (romanize_fold(tok) for tok in normalize_latin(text).split()) if f]


# --- Basic Arabic -> Latin transliteration (default scheme) ---------------
# A pragmatic single-char romanization to bridge scripts before folding.
# For exact ALA-LC/BGN-PCGN output, load namesdb/done/transliteration_schemes.csv.
_AR2LAT = {
    "ا": "a", "ب": "b", "ت": "t", "ث": "th", "ج": "j", "ح": "h", "خ": "kh",
    "د": "d", "ذ": "dh", "ر": "r", "ز": "z", "س": "s", "ش": "sh", "ص": "s",
    "ض": "d", "ط": "t", "ظ": "z", "ع": "", "غ": "gh", "ف": "f", "ق": "q",
    "ك": "k", "ل": "l", "م": "m", "ن": "n", "ه": "h", "و": "w", "ي": "y",
    "ء": "", "ة": "a", "ى": "a",
}


def transliterate_arabic(text: str) -> str:
    """Romanize Arabic to a default Latin form (after Arabic normalization)."""
    text = normalize_arabic(text)
    return "".join(_AR2LAT.get(ch, ch if ch.isspace() else "") for ch in text)


# --- cross-script consonant skeleton --------------------------------------

_SKEL_DIGRAPHS = [
    ("tch", "c"), ("sch", "c"),
    ("kh", "x"), ("gh", "g"), ("dh", "d"), ("th", "t"), ("sh", "c"),
    ("ph", "f"), ("ch", "c"), ("ck", "k"), ("sch", "c"),
]
# Arabic phonology: no v/p (-> f/b); q/c -> k; s/z blur; ج is j or g (Egyptian)
# so j -> g. Keep k and g distinct (kaf vs gaf/jim) to avoid over-merging.
_SKEL_MAP = str.maketrans({"v": "f", "p": "b", "q": "k", "c": "k", "z": "s", "j": "g"})
_SKEL_DROP = set("aeiouwy")


# --- Basic Hebrew -> Latin transliteration --------------------------------
_HE_NIQQUD = re.compile("[֑-ׇ]")
_HE2LAT = {
    "א": "", "ב": "b", "ג": "g", "ד": "d", "ה": "h", "ו": "v", "ז": "z",
    "ח": "h", "ט": "t", "י": "y", "כ": "k", "ך": "k", "ל": "l", "מ": "m",
    "ם": "m", "נ": "n", "ן": "n", "ס": "s", "ע": "", "פ": "f", "ף": "f",
    "צ": "ts", "ץ": "ts", "ק": "k", "ר": "r", "ש": "sh", "ת": "t",
}


def transliterate_hebrew(text: str) -> str:
    """Romanize Hebrew to a default Latin form (niqqud stripped)."""
    text = _HE_NIQQUD.sub("", text)
    return "".join(_HE2LAT.get(ch, ch if ch.isspace() else "") for ch in text)


# A "hard" reading for the multi-valued letters (bet/pe/kaf/shin/het), used to
# generate a second Hebrew romanization candidate (the soft one is the default).
_HE2LAT_HARD = {**_HE2LAT, "ב": "b", "פ": "p", "ף": "p", "כ": "k", "ך": "k",
                "ש": "s", "ח": "ch"}


def transliterate_hebrew_hard(text: str) -> str:
    text = _HE_NIQQUD.sub("", text)
    return "".join(_HE2LAT_HARD.get(ch, ch if ch.isspace() else "") for ch in text)


# --- Basic Devanagari (Hindi) -> Latin transliteration --------------------
# Flat char map; inherent/short vowels are approximate but the consonant
# skeleton (which drops vowels) carries the cross-script match.
_DEVA_NUKTA = {
    "क़": "q", "ख़": "kh", "ग़": "gh", "ज़": "z", "ड़": "r", "ढ़": "rh", "फ़": "f", "य़": "y",
}
_DEVA = {
    "अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ऋ": "ri",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऍ": "e", "ऑ": "o", "ॐ": "om",
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "ch",
    "ज": "j", "झ": "jh", "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh",
    "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n", "प": "p",
    "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l",
    "ळ": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    # matras (vowel signs)
    "ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "ृ": "ri", "े": "e",
    "ै": "ai", "ो": "o", "ौ": "au", "ॅ": "e", "ॉ": "o",
    # signs
    "ं": "n", "ँ": "n", "ः": "h", "्": "", "़": "",
}


def transliterate_devanagari(text: str) -> str:
    """Romanize Devanagari (Hindi) to Latin (approximate, skeleton-friendly)."""
    for seq, lat in _DEVA_NUKTA.items():
        text = text.replace(seq, lat)
    out = []
    for ch in text:
        if ch in _DEVA:
            out.append(_DEVA[ch])
        elif ch.isspace():
            out.append(" ")
        elif ch.isascii() and ch.isalpha():
            out.append(ch)  # latin from the nukta pre-pass
    return "".join(out)


def consonant_skeleton(token: str) -> str:
    """Arabic-aware consonant skeleton for cross-script comparison.

    Drops the short vowels Arabic doesn't write (and semivowels w/y), folds the
    digraphs and the v/p/q/g/j/z phonology blur, and squeezes doubles. So
    ``Rudolf`` (``rdlf``) meets the transliteration of رودلف, and ``Victor``
    meets فيكتور. Lossy by design; used only when bridging two scripts.
    """
    t = strip_diacritics(token).lower()
    for a, b in _SKEL_DIGRAPHS:
        t = t.replace(a, b)
    t = t.translate(_SKEL_MAP)
    out: list[str] = []
    for ch in t:
        if not ch.isalpha() or ch in _SKEL_DROP:
            continue
        if not out or out[-1] != ch:
            out.append(ch)
    return "".join(out)
