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


def test_author_variants_match():
    assert match("Arthur Conan Doyle", "A. Conan Doyle").bucket == "match"
    assert match("Gabriel García Márquez", "Gabriel Garcia Marquez").bucket == "match"
    assert match("George R. R. Martin", "George R.R. Martin").bucket == "match"


def test_author_crossscript_match():
    # Naguib Mahfouz <-> نجيب محفوظ
    assert match("Naguib Mahfouz", "نجيب محفوظ").bucket in ("match", "review")


def test_author_different_no_match():
    assert match("Mary Higgins Clark", "Mary Roach").bucket == "no-match"
    assert match("George Orwell", "George Eliot").bucket == "no-match"


def test_calibre_profile_veto():
    # author->books profile vetoes a same-script coincidental name collision,
    # keeps a true variant, and skips cross-script pairs.
    from integrations.calibre import make_profile_compare
    cmp = make_profile_compare(min_profile=3)
    # homonyms: same name (name-match), book profiles disambiguate
    jw_film = {"name": "John Williams", "script": "Latin", "profile": {"film", "score", "orchestral"}}
    jw_guitar = {"name": "John Williams", "script": "Latin", "profile": {"guitar", "classical", "spanish"}}
    jw_film2 = {"name": "John Williams", "script": "Latin", "profile": {"film", "score", "movie"}}
    assert cmp(jw_film, jw_guitar).bucket == "review"   # disjoint profiles -> demoted from match
    assert cmp(jw_film, jw_film2).bucket == "match"      # overlapping profiles -> kept


def test_dedup_record_aware_with_profile_compare():
    from integrations.calibre import make_profile_compare
    from namematch import dedup
    recs = [  # three 'John Williams' homonyms; profiles disambiguate
        {"name": "John Williams", "script": "Latin", "profile": {"film", "score", "orchestral"}},
        {"name": "John Williams", "script": "Latin", "profile": {"film", "score", "movie"}},
        {"name": "John Williams", "script": "Latin", "profile": {"guitar", "classical", "spanish"}},
    ]
    res = dedup(recs, key=lambda r: r["name"], compare=make_profile_compare(min_profile=3))
    assert res.labels[0] == res.labels[1]      # the two film composers cluster (overlap)
    assert res.labels[2] != res.labels[0]      # the guitarist stays separate (vetoed)


def test_entity_type_plugin_wiring():
    # opt-in GLiNER plugin: importable + callable without loading the model.
    # (Real classification is validated by the spike, not the unit suite, since
    # it needs the model download.)
    from namematch.plugins import entity_type
    assert callable(entity_type.classify)
    assert entity_type._DEFAULT_MODEL and "gliner" in entity_type._DEFAULT_MODEL.lower()


def test_calibre_classify_author():
    from integrations.calibre import classify_author, refine_org
    titles = {"clubdead", "emanuellasker", "carrie"}  # normalized book titles
    assert classify_author("#!/bin/bash", titles)[0] == "junk"
    assert classify_author("Club Dead", titles) == ("title", "high")
    assert classify_author("A Course in Fluid Mechanics", titles)[0] != "person"
    # #1 Arabic surname،firstname (and period form) -> person
    assert classify_author("باختين، ميخائيل", titles) == ("person", "high")
    assert classify_author("المغازي، أحمد", titles) == ("person", "high")
    # #2 co-author / authority strings -> person; title|metadata is not a person
    assert classify_author("Grisham| John", titles) == ("person", "high")
    assert classify_author("Ali Emadi| John M. Miller", titles) == ("person", "high")
    assert classify_author("Chess Task-Manual| Vol. 5 (1999)", titles)[0] != "person"
    # #3 eponymous: a person-shaped title-match is NOT scrubbed to title;
    # a non-name title-match (Club Dead, Carrie) stays a title.
    assert classify_author("Carrie", titles) == ("title", "high")   # single-token title
    assert classify_author("Club Dead", titles) == ("title", "high")  # not name-shaped
    # #4 org anchor: real org keeps org; unanchored -> person; year -> title
    assert refine_org("Cisco Systems") == "org"
    assert refine_org("Spinoza") == "person"
    assert refine_org("Fishing (1916)") == "title"
    if HAS_CORPUS:  # eponymous veto needs the gazetteer to see the name
        assert classify_author("Charles Dickens", titles)[0] == "person"
        assert classify_author("Emanuel Lasker", titles)[0] == "person"


def test_calibre_clean_normalization():
    # residual fix #1: shared input normalization on every path
    from integrations.calibre import _clean
    assert _clean("‏John Smith‎​") == "John Smith"   # bidi/zero-width
    assert _clean("Modern Chess Openings.part1") == "Modern Chess Openings"
    assert _clean("Dumas (single pages)") == "Dumas"
    assert _clean("Tolstoy; Translated") == "Tolstoy"               # trailing role
    assert _clean("Hugo, Victor; Edited by") == "Hugo, Victor"
    assert _clean("By Charles Dickens") == "Charles Dickens"        # leading credit
    assert _clean("Dr. Watson") == "Watson"
    assert _clean("د. أحمد أمين") == "أحمد أمين"
    assert _clean("Marcus Wareing|") == "Marcus Wareing"    # dangling separator
    assert _clean("عقاد، عباس محمود،, 18891964") == "عقاد، عباس محمود"


def test_calibre_coauthor_split_rescue():
    # residual fix #2: `;`/`,` co-author lists -> person; title;subtitle guarded
    from integrations.calibre import classify_author
    titles = {"loverosie"}
    if HAS_CORPUS:
        assert classify_author("Stephen King; Peter Straub", titles) == ("person", "high")
        assert classify_author("Neil Gaiman, Terry Pratchett", titles) == ("person", "high")
    # subtitle segments carry title-words -> not a co-author list
    assert classify_author("Chess Openings; A Complete Guide", titles)[0] != "person"
    assert classify_author("Cooking Basics; An Introduction", titles)[0] != "person"
    # a comma'd string matching a real book title is still that title
    assert classify_author("Love, Rosie", titles)[0] == "title"


def test_calibre_author_separated_tightened():
    # residual fixes #3/#4/#9: particles pass, lists/affiliations + raw `|` fail
    from integrations.calibre import _author_separated, classify_author
    if HAS_CORPUS:
        assert classify_author(
            "Curt von Bardeleben| Emil Schallopp und der Lasa", set()) == ("person", "high")
        assert classify_author("Grisham| John", set()) == ("person", "high")
        # de-duped repeated segments still pass
        assert classify_author("Grisham| John| Grisham", set()) == ("person", "high")
        # suffix segments are ignorable; long all-multi-token lists pass
        assert classify_author("Johnson| Spencer| M.D.", set()) == ("person", "high")
        assert classify_author(
            "Philippe Hampikian| Jean-Marie Cannoni| Vincent Daniau| "
            "Patrice Delage| Christophe Delaitre", set()) == ("person", "high")
        # a list that de-dupes to one real name is that name
        assert classify_author("A. Borovik| A. Borovik", set()) == ("person", "high")
        # alternating surname|given sort-form pairs
        assert classify_author(
            "Gater| Will.| Vamplew| Anton.| Mitton| Jacqueline.", set()) == ("person", "high")
        # year-range and lone-initial segments are ignorable
        assert classify_author("Strunk| William| 1869-1946", set()) == ("person", "high")
        assert classify_author("Erdos| P.", set()) == ("person", "high")
        # sort forms repeat the surname — pairing runs before de-duping
        assert classify_author(
            "Strawbridge| Dick.|Strawbridge| James.", set()) == ("person", "high")
        # a short all-given-names list is a co-author list
        assert classify_author("Ivan |Peter| Jan", set()) == ("person", "high")
        # partial pair evidence -> review, not junk
        assert _author_separated("Terplan| Kornel| Morreale| Patricia") == "soft"
    # name-shaped but lexicon-less separated forms go to review (model decides)
    assert _author_separated("Etoh| Minoru.") == "soft"
    assert classify_author("Etoh| Minoru.", set()) == ("review", "low")
    assert _author_separated("Air Conditioning| Heating") == "soft"
    # library lists / affiliations / tech terms are never person-high...
    assert _author_separated("Struts| Tapestry| JSF| Spring") != "high"
    assert _author_separated(
        "Struts| Tapestry| Commons| Velocity| JUnit| Axis| Cocoon") is None
    assert _author_separated("A| B") is None                # bare initials
    # ...and any raw `|` that survives is field-merge corruption -> junk
    assert classify_author("Struts| Tapestry| JSF| Spring", set())[0] != "person"
    assert classify_author("The Finite Element Method| V", set()) == ("junk", "high")
    # shouty affiliation lists are at most review, never person
    assert classify_author("THERMODYNAMICS| HEAT TRANSFER| A", set())[0] != "person"


def test_calibre_initials_forms():
    # surname+initials shapes are persons; the gliner-junk override backs them
    from integrations.calibre import _gliner_person_override, classify_author
    assert classify_author("Shafarevich I.R", set()) == ("person", "med")
    assert classify_author("S.Sivalingam", set()) == ("person", "med")
    assert classify_author("J. ECONOMETRICS", set())[0] != "person"
    assert _gliner_person_override("Shafarevich I.R")
    if HAS_CORPUS:  # Arabic gazetteer names the model junks are kept
        assert _gliner_person_override("سهام مرضي")
        assert not _gliner_person_override("Key of Valor")
        assert not _gliner_person_override("Chess Strategies")


def test_calibre_structural_junk():
    # residual fix #5: boilerplate rows are junk, never accepted as titles
    from integrations.calibre import classify_author
    for s in ("Chap-01", "Chapter 7", "Volume 12", "ISBN 9780262033848",
              "AB-CD-123", "Appendices", "Study Guide", "Poem", "Introduction"):
        assert classify_author(s, {"chap01", "volume12", "poem"}) == ("junk", "high"), s


def test_calibre_gliner_person_postfilters():
    # residual fix #6: role words -> junk, collectives -> org, truncation -> junk
    from integrations.calibre import refine_person
    assert refine_person("Administrador") == "junk"
    assert refine_person("Owner") == "junk"
    assert refine_person("Editors") == "junk"               # bare role word
    assert refine_person("Anonymous") == "junk"
    assert refine_person("Oxford University Press") == "org"
    assert refine_person("The Economist Editorial") == "org"
    assert refine_person("دار الشروق") == "org"
    assert refine_person("Christopher Hitc-") == "junk"     # visibly truncated
    assert refine_person("James (Editor of") == "junk"      # unbalanced paren
    assert refine_person("John Smith") == "person"


def test_calibre_genre_author_gazetteer():
    # residual fix #7: genre authors + credit/citation/camelcase person forms
    from integrations.calibre import classify_author
    assert classify_author("C.J. Cherryh", {"cjcherryh"})[0] == "person"
    assert classify_author("Cherryh", {"cherryh"})[0] == "person"
    assert classify_author("ValeriBeim", set())[0] == "person"
    # genre surname counts as lexicon evidence in separated/authority forms
    assert classify_author("Cherryh| C J", set()) == ("person", "high")
    from integrations.calibre import _genre_author
    assert _genre_author("Cassandra Clare")            # gliner title-override hook
    assert not _genre_author("Club Dead")
    if HAS_CORPUS:
        assert classify_author("Cassandra Clare", {"cassandraclare"})[0] == "person"
        assert classify_author("(With Emanuel Lasker)", set())[0] == "person"
        assert classify_author("Grisham 2003", set())[0] == "person"


def test_calibre_org_weak_anchors():
    # residual fix #8: weak anchors need context; publisher stoplist; person glue
    from integrations.calibre import refine_org
    assert refine_org("Second Foundation", {"secondfoundation"}) == "title"
    assert refine_org("Second Foundation") == "title"       # ordinal + weak anchor
    assert refine_org("The Society") == "junk"
    assert refine_org("American Chess Foundation") == "org"
    assert refine_org("Royal Society") == "org"
    assert refine_org("Wiley") == "org"
    assert refine_org("M University") == "junk"             # truncated
    # an anchored string with a parenthesized year is a book, not an org
    assert refine_org("Feedback Control of Computing Systems (2004)") == "title"
    if HAS_CORPUS:
        assert refine_org("Wenbo Mao Hewlett-Packard Company") == "person"


def test_calibre_read_person_filter():
    import tempfile
    from integrations.calibre import read_person_filter
    with tempfile.NamedTemporaryFile("w", suffix=".tsv", delete=False,
                                     encoding="utf-8") as fh:
        fh.write("category\tconfidence\tname\n"
                 "person\thigh\tGrisham| John\n"
                 "title\thigh\tClub Dead\n"
                 "junk\thigh\tChap-01\n"
                 "person\tgliner\tنجيب محفوظ\n")
        path = fh.name
    assert read_person_filter(path) == {"Grisham| John", "نجيب محفوظ"}


def test_calibre_integration_read_and_dedup(tmp_path=None):
    import sqlite3
    import tempfile
    from integrations.calibre import read_authors
    from namematch import dedup

    d = tempfile.mkdtemp()
    db = f"{d}/metadata.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT NOT NULL, "
                "sort TEXT, link TEXT NOT NULL DEFAULT '')")
    for nm in ["Arthur Conan Doyle", "A. Conan Doyle", "Isaac Asimov", "Mary Roach"]:
        con.execute("INSERT INTO authors (name) VALUES (?)", (nm,))
    con.commit(); con.close()

    authors = read_authors(db)
    assert len(authors) == 4
    res = dedup(authors)
    # the two Conan Doyle spellings cluster; Asimov/Roach stay separate
    ai = authors.index("Arthur Conan Doyle")
    bi = authors.index("A. Conan Doyle")
    assert res.labels[ai] == res.labels[bi]
    assert len({res.labels[authors.index(n)] for n in ("Isaac Asimov", "Mary Roach", "Arthur Conan Doyle")}) == 3


def test_multisignal_disambiguates_homonyms():
    from namematch import Signal, cmp_fuzzy, cmp_name, match, match_records
    # two different 'John Williams' (composer vs guitarist): the NAME genuinely
    # matches (homonyms), so a second signal must do the disambiguation.
    assert match("John Williams", "John Williams").bucket == "match"
    sigs = [Signal("name", 0.6, cmp_name), Signal("subject", 0.4, cmp_fuzzy)]
    a = {"name": "John Williams", "subject": "film score composer orchestral"}
    b = {"name": "John Williams", "subject": "classical guitar transcriptions"}
    assert match_records(a, b, sigs).bucket != "match"


def test_multisignal_confirms_true_match():
    from namematch import Signal, cmp_fuzzy, cmp_name, cmp_year, match_records
    sigs = [Signal("name", 0.5, cmp_name), Signal("title", 0.3, cmp_fuzzy),
            Signal("year", 0.2, cmp_year(1))]
    a = {"name": "J.K. Rowling", "title": "Harry Potter and the Philosopher's Stone", "year": 1997}
    b = {"name": "J. K. Rowling", "title": "Harry Potter & the Philosopher's Stone", "year": 1998}
    assert match_records(a, b, sigs).bucket == "match"


def test_multisignal_degrades_to_name_only():
    # with only the name field present, the record score == the name score
    from namematch import Signal, cmp_name, match, match_records
    sigs = [Signal("name", 0.6, cmp_name), Signal("title", 0.4)]
    a = {"name": "George Washington"}
    b = {"name": "G. Washington"}
    r = match_records(a, b, sigs)
    assert r.bucket == match("George Washington", "G. Washington").bucket == "match"


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
