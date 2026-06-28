"""Core behavior tests — runnable without the namesdb corpus present.

Tests that need gazetteers are guarded so the suite passes on a bare checkout.
"""
from __future__ import annotations

from namematch import detect, match, parse
from namematch.lexicon import default_namesdb
from namematch.normalize import normalize_arabic, romanize_fold, transliterate_arabic
from namematch.script import detect_script

HAS_CORPUS = default_namesdb().exists()


# --- script detection -----------------------------------------------------

def test_script_arabic_vs_latin():
    assert detect_script("صلاح الدين").dominant == "Arabic"
    assert detect_script("George Washington").dominant == "Latin"
    assert detect_script("שלום").dominant == "Hebrew"


def test_script_mixed():
    p = detect_script("Salah صلاح")
    assert p.is_mixed


# --- normalization --------------------------------------------------------

def test_normalize_arabic_alef_and_tashkeel():
    assert normalize_arabic("إِبْتِسامة") == normalize_arabic("ابتسامة")
    assert normalize_arabic("أحمد") == normalize_arabic("احمد")


def test_romanize_fold_converges_transliterations():
    # Salah al-Din spelled multiple Latin ways should fold close together.
    a = " ".join(romanize_fold(t) for t in "Salah al-Din".split())
    b = " ".join(romanize_fold(t) for t in "Salah ad-Deen".split())
    assert a == b


def test_transliterate_arabic_runs():
    out = transliterate_arabic("صلاح")
    assert "s" in out and "l" in out


# --- parsing --------------------------------------------------------------

def test_parse_western():
    p = parse("George Washington")
    assert p.given == ["george"]
    assert p.family == ["washington"]


def test_parse_western_particle_surname():
    p = parse("Ludwig van Beethoven")
    assert p.family[-1] == "beethoven"
    assert "van" in p.particles


def test_parse_arabic_compound_given():
    p = parse("صلاح الدين الأيوبي")
    assert p.given[0] == normalize_arabic("صلاح الدين")  # kept as one unit
    assert p.family  # nisba/family present


def test_parse_spanish_two_surnames():
    p = parse("Maria de la Cruz Gonzalez", culture="Spanish")
    assert p.given == ["maria"]
    assert len(p.family) >= 2


# --- matching: the headline cases -----------------------------------------

def test_initials_match():
    r = match("G. Washington", "George Washington")
    assert r.bucket == "match", r.reasons


def test_arabic_subset_match():
    # صلاح (alone) should match صلاح الدين when family aligns:
    # given prefix-containment + identical family -> confident match.
    r = match("صلاح الأيوبي", "صلاح الدين الأيوبي")
    assert r.bucket == "match", (r.score, r.reasons)


def test_compound_head_not_overmerged():
    # صلاح must NOT swallow a following family name (الأيوبي) as a compound.
    p = parse("صلاح الأيوبي")
    assert p.given == [normalize_arabic("صلاح")]
    assert p.family == [normalize_arabic("الأيوبي")]


def test_different_people_no_match():
    r = match("George Washington", "Thomas Jefferson")
    assert r.bucket == "no-match", r.reasons


def test_cross_script_bridge_runs():
    # Should not crash and should produce a score in [0,1].
    r = match("صلاح الدين", "Salah al-Din")
    assert 0.0 <= r.score <= 1.0


# --- v0.2 B: culture inference + Iberian auto-match ------------------------

def test_infer_culture():
    from namematch import infer_culture
    assert infer_culture("صلاح الدين") == "Arabic"
    assert infer_culture("Maria de la Cruz") == "Spanish"
    assert infer_culture("George Washington") == "Western"


def test_iberian_two_surname_auto_match():
    # Was no-match before B (Western parse misread the two surnames).
    r = match("Maria de la Cruz", "María de la Cruz González")
    assert r.bucket == "match", (r.score, r.reasons)


# --- v0.2 C: scheme-accurate cross-script transliteration -----------------

def test_cross_script_caught_as_review_or_match():
    # Precision-first: a clean transliteration must at least reach review.
    r = match("صلاح الدين", "Salah al-Din")
    assert r.bucket in ("match", "review"), (r.score, r.reasons)


def test_transliteration_candidates_multi():
    from namematch import transliteration_candidates
    cands = transliteration_candidates("صلاح الدين")
    assert len(cands) >= 1 and all(c.strip() for c in cands)


def test_hebrew_normalization_keeps_letters():
    from namematch.normalize import normalize_token
    # bug was: Hebrew tokens run through normalize_latin -> '' -> never match
    out = normalize_token("דָּוִד", "Hebrew")  # vocalized David
    assert out and any("֐" <= c <= "׿" for c in out)  # Hebrew survives
    assert "ָ" not in out  # niqqud stripped


def test_mononym_partial_name_reaches_review():
    # 'Tolkien' vs 'J.R.R. Tolkien' was a false no-match; now at least review.
    r = match("Tolkien", "J.R.R. Tolkien")
    assert r.bucket in ("match", "review"), (r.score, r.reasons)


def test_lone_token_vs_fullname_not_auto_merged():
    # A bare given/surname token must NOT auto-merge with a full name sharing it
    # (this was the dedup hub bug: 'jan' matched every 'Jan ...' at 1.0 and
    # union-find chained hundreds of distinct people). Cap at review.
    assert match("Jan", "Jan Axelson").bucket != "match"
    assert match("Roy", "Arundhati Roy").bucket != "match"
    # but two single-token variants of each other may still match
    assert match("Akeela", "Akeelah").bucket in ("match", "review")


def test_dedup_clusters_and_blocks():
    from namematch import dedup
    from namematch.dedup import candidate_pairs

    names = [
        "George Washington", "G. Washington", "Geo. Washington",
        "Thomas Jefferson", "T. Jefferson",
        "Mohammed Ali", "Muhammad Ali",
    ]
    res = dedup(names)
    assert res.n_input == len(names)
    # the two Washington-initials variants land with George Washington
    assert res.labels[0] == res.labels[1] == res.labels[2]
    # Jefferson is a different entity than Washington
    assert res.labels[3] != res.labels[0]
    # the two Jeffersons cluster together
    assert res.labels[3] == res.labels[4]
    # blocking yields fewer candidate pairs than all-pairs
    allpairs = len(names) * (len(names) - 1) // 2
    assert len(candidate_pairs(names)) < allpairs


def test_consonant_skeleton_drops_vowels():
    from namematch.normalize import consonant_skeleton
    assert consonant_skeleton("Rudolf") == "rdlf"
    # v/p phonology fold + vowel drop -> Victor and a faktur-style translit meet
    assert consonant_skeleton("Victor") == consonant_skeleton("Fiktor")


def test_hebrew_cross_script_bridge():
    from namematch.normalize import transliterate_hebrew
    assert "d" in transliterate_hebrew("דוד")  # David
    r = match("דוד", "David")
    assert r.score > 0.6, (r.score, r.reasons)


def test_chinese_pinyin_bridge():
    from namematch.translit import transliterate_chinese
    if not transliterate_chinese("习"):  # data file absent on a bare checkout
        return
    assert transliterate_chinese("习近平") == "xijinping"
    assert match("习近平", "Xi Jinping").bucket == "match"


def test_hindi_devanagari_bridge():
    from namematch.normalize import transliterate_devanagari
    assert "n" in transliterate_devanagari("नरेंद्र")
    r = match("नरेंद्र मोदी", "Narendra Modi")
    assert r.bucket in ("match", "review"), (r.score, r.reasons)


def _paranames_precision(lang: str, floor_recall: float):
    import pathlib

    f = pathlib.Path(__file__).resolve().parents[1] / "eval" / f"paranames_en_{lang}.tsv"
    if not f.exists():
        return
    from eval.bench import evaluate, load_pairs

    res = evaluate(load_pairs(f)[:300])["ALL"]
    assert res["strict"]["precision"] >= 0.85, (lang, res["strict"])
    assert res["lenient"]["recall"] > floor_recall, (lang, res["lenient"])


def test_paranames_zh_hi_bridges_active():
    _paranames_precision("zh", 0.30)
    _paranames_precision("hi", 0.50)


def test_paranames_he_bridge_precision():
    import pathlib

    f = pathlib.Path(__file__).resolve().parents[1] / "eval" / "paranames_en_he.tsv"
    if not f.exists():
        return
    from eval.bench import evaluate, load_pairs

    res = evaluate(load_pairs(f)[:300])["ALL"]
    assert res["strict"]["precision"] >= 0.85, res["strict"]
    assert res["lenient"]["recall"] > 0.20, res["lenient"]  # bridge is active


def test_paranames_cross_script_regression():
    """Lock the ParaNames EN<->AR baseline: precision-first across scripts.

    Runs a capped subset for speed; skips if the benchmark isn't present.
    """
    import pathlib

    f = pathlib.Path(__file__).resolve().parents[1] / "eval" / "paranames_en_ar.tsv"
    if not f.exists():
        return
    from eval.bench import evaluate, load_pairs

    pairs = load_pairs(f)[:300]
    res = evaluate(pairs)["ALL"]
    # Baseline strict P 0.95 / lenient R 0.79 (2026-06-18); guard precision.
    assert res["strict"]["precision"] >= 0.88, res["strict"]


# --- detection (needs corpus) ---------------------------------------------

def test_detect_origin_arabic():
    d = detect("صلاح الدين")
    assert d.script == "Arabic"
    if HAS_CORPUS:
        assert d.top_origin == "Arabic"


def test_detect_rejects_nonname():
    d = detect("invoice #4471 total $99")
    assert d.is_person_name < 0.3


# --- eval-harness regression gate -----------------------------------------

def test_eval_regression():
    """Lock the synthetic-harness baseline: precision-first, high triage recall.

    Skips cleanly if the dataset hasn't been generated (bare checkout).
    """
    import pathlib

    pairs_file = pathlib.Path(__file__).resolve().parents[1] / "eval" / "pairs.tsv"
    if not pairs_file.exists():
        return  # generate with: python eval/build_dataset.py
    from eval.bench import evaluate, load_pairs

    res = evaluate(load_pairs(pairs_file))
    allr = res["ALL"]
    # Baselines captured 2026-06-18 (strict P 0.90 / lenient R 0.96); guard
    # against regressions while leaving room for B/C to improve recall.
    assert allr["strict"]["precision"] >= 0.85, allr["strict"]
    assert allr["lenient"]["recall"] >= 0.90, allr["lenient"]
