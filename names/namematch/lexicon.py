"""Gazetteers loaded from the existing ``DataMasterer/namesdb`` corpus.

The corpus already on disk (no download needed):

- ``KDBAGIV.txt``         25k+ Arabic given names, TAB: id, unvocalized,
                          vocalized, gender (M/F/U), country (ISO-2).
- ``done/ar_*.csv``       Arabic given names (various sources).
- ``done/he_*.csv``       Hebrew given names.
- ``done/isl_*.csv``      Islamic given names.
- first/last-name zip     Western (US census) first + last names.

Everything is lazy + cached. The corpus lives outside this module (it is
large and shared), so the path is configurable; the default walks up to
``DataMasterer/namesdb``.

This module is the local, deterministic backbone of origin detection: a name
token's *membership* in these sets, weighted by how exclusive the set is, is
the primary origin signal. The optional ML plugin only refines hard cases.
"""
from __future__ import annotations

import csv
import functools
import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .normalize import normalize_arabic, normalize_latin


def default_namesdb() -> Path:
    """Resolve ``DataMasterer/namesdb`` relative to this file, env-overridable."""
    import os

    env = os.environ.get("NAMEMATCH_NAMESDB")
    if env:
        return Path(env)
    # names/namematch/lexicon.py -> names -> NectarMatcher -> DataMasterer
    here = Path(__file__).resolve()
    cand = here.parents[3] / "namesdb"
    return cand


@dataclass
class Gazetteers:
    """Normalized name sets keyed by origin, plus gender/country side-tables."""

    given: dict[str, set[str]] = field(default_factory=dict)   # origin -> {norm names}
    surname: dict[str, set[str]] = field(default_factory=dict)
    gender: dict[str, str] = field(default_factory=dict)        # norm name -> M/F/U
    country: dict[str, set[str]] = field(default_factory=dict)  # norm name -> {ISO2}

    def origins_of(self, token_norm: str, kind: str = "given") -> set[str]:
        table = self.given if kind == "given" else self.surname
        return {origin for origin, names in table.items() if token_norm in names}

    def all_origins(self) -> set[str]:
        return set(self.given) | set(self.surname)


def _add(table: dict[str, set[str]], origin: str, value: str) -> None:
    if value:
        table.setdefault(origin, set()).add(value)


@functools.lru_cache(maxsize=4)
def load(namesdb: str | Path | None = None) -> Gazetteers:
    """Load and cache all gazetteers. Missing files are skipped silently."""
    root = Path(namesdb) if namesdb else default_namesdb()
    g = Gazetteers()
    if not root.exists():
        return g

    _load_kalmasoft(root / "KDBAGIV.txt", g)
    done = root / "done"
    if done.is_dir():
        for csv_path in done.glob("*.csv"):
            _load_done_csv(csv_path, g)
    _load_western_zip(root / "CSV_Database_Of_First_And_Last_Names.zip", g)
    return g


def _load_kalmasoft(path: Path, g: Gazetteers) -> None:
    if not path.exists():
        return
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 4 or not parts[0].startswith("AGN"):
                continue
            unvoc = normalize_arabic(parts[1].strip())
            gender = parts[3].strip() if len(parts) > 3 else ""
            country = parts[4].strip() if len(parts) > 4 else ""
            if not unvoc:
                continue
            _add(g.given, "Arabic", unvoc)
            if gender in ("M", "F", "U"):
                g.gender.setdefault(unvoc, gender)
            if country:
                g.country.setdefault(unvoc, set()).add(country)


def _origin_from_filename(name: str) -> str:
    if name.startswith("ar") or name.startswith("isl"):
        return "Arabic"
    if name.startswith("he"):
        return "Hebrew"
    return "Other"


def _load_done_csv(path: Path, g: Gazetteers) -> None:
    origin = _origin_from_filename(path.stem)
    arabic = origin in ("Arabic", "Hebrew")
    try:
        with path.open(encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader, None)
            name_col = 0
            if header:
                for i, col in enumerate(header):
                    if col.strip().lower() in ("name", "names", "firstname", "given"):
                        name_col = i
                        break
            for row in reader:
                if not row or name_col >= len(row):
                    continue
                raw = row[name_col].strip()
                if not raw:
                    continue
                norm = normalize_arabic(raw) if arabic else normalize_latin(raw)
                _add(g.given, origin, norm)
    except (csv.Error, UnicodeError):
        return


def _load_western_zip(path: Path, g: Gazetteers) -> None:
    if not path.exists():
        return
    try:
        with zipfile.ZipFile(path) as zf:
            for member, table in (
                ("CSV_Database_of_First_Names.csv", g.given),
                ("CSV_Database_of_Last_Names.csv", g.surname),
            ):
                try:
                    raw = zf.read(member).decode("utf-8", "replace")
                except KeyError:
                    continue
                # old-Mac CR line endings in this dataset
                for tok in raw.replace("\r", "\n").split("\n"):
                    tok = tok.strip().strip(",")
                    if not tok or tok.lower() in ("firstname", "lastname"):
                        continue
                    _add(table, "Western", normalize_latin(tok))
    except zipfile.BadZipFile:
        return
