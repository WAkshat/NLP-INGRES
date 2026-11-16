"""Gazetteer of INGRES locations: canonical entries + aliases + normalised forms.

Entry: (entity_id, level state|district|unit, db_name, display, state, district, aliases). Aliases come from
display normalisation, Himachal district codes, curated colloquial names (optional) and historical INGRES
spellings from the cross-year crosswalk (optional; excluded when those spellings are themselves evaluated).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from indic_transliteration import sanscript

from src.benchmark.pool import display
from src.utils.safe_sql import execute

# Well-known official renames / colloquial names (old or common form -> INGRES district name). Only used when
# include_colloquial=True; evaluated separately because string similarity cannot recover them.
COLLOQUIAL = {
    "Gurgaon": "GURUGRAM", "Mewat": "NUH", "Allahabad": "PRAYAGRAJ", "Faizabad": "AYODHYA", "Bangalore": "Bengaluru (Urban)",
    "Mysore": "Mysuru", "Belgaum": "Belagavi", "Gulbarga": "Kalburgi", "Bellary": "Ballari", "Bijapur": "Vijayapura",
    "Shimoga": "Shivamogga", "Tumkur": "Tumakuru", "Ahmednagar": "Ahilyanagar", "Aurangabad": "Ch.Sambhajinagar",
    "Osmanabad": "Dharashiv", "Pondicherry": "PUDUCHERRY", "Orissa": "ODISHA", "Calcutta": "KOLKATTA",
}


# Tamil script -> Latin. indic_transliteration's TAMIL scheme maps the stops to voiced aspirates (க -> "gha",
# so கர்நாடகா came out as "gharnadhagha"); Tamil writes k/g, t/d, p/b, c/j/s with one letter each, so the
# neutral reading is the unvoiced one and voicing is ignored when comparing (see devoice()).
_TA_CONS = {"க": "k", "ங": "ng", "ச": "s", "ஞ": "nj", "ட": "t", "ண": "n", "த": "t", "ந": "n", "ப": "p", "ம": "m",
            "ய": "y", "ர": "r", "ல": "l", "வ": "v", "ழ": "l", "ள": "l", "ற": "r", "ன": "n", "ஜ": "j", "ஷ": "sh",
            "ஸ": "s", "ஹ": "h"}
_TA_VOWEL = {"அ": "a", "ஆ": "aa", "இ": "i", "ஈ": "ee", "உ": "u", "ஊ": "oo", "எ": "e", "ஏ": "e", "ஐ": "ai", "ஒ": "o",
             "ஓ": "o", "ஔ": "au"}
_TA_SIGN = {"ா": "aa", "ி": "i", "ீ": "ee", "ு": "u", "ூ": "oo", "ெ": "e", "ே": "e", "ை": "ai", "ொ": "o", "ோ": "o",
            "ௌ": "au", "்": ""}
TAMIL = re.compile(r"[஀-௿]")


def romanise_tamil(text: str) -> str:
    out, i = [], 0
    while i < len(text):
        ch = text[i]
        if ch in _TA_CONS:
            nxt = text[i + 1] if i + 1 < len(text) else ""
            out.append(_TA_CONS[ch] + (_TA_SIGN[nxt] if nxt in _TA_SIGN else "a"))
            i += 2 if nxt in _TA_SIGN else 1
        else:
            out.append(_TA_VOWEL.get(ch, "" if ch == "ஃ" else ch))
            i += 1
    return "".join(out)


def romanise(text: str) -> str:
    out = text
    if re.search(r"[ऀ-ॿ]", out):
        out = sanscript.transliterate(out, sanscript.DEVANAGARI, sanscript.ISO)
        # anusvara is a homorganic nasal: 'm' only before labials (बंगाल -> bangala, not bamgala)
        out = re.sub("ṁ(?=[pbm])", "m", unicodedata.normalize("NFC", out)).replace("ṁ", "n")
    if TAMIL.search(out):
        out = romanise_tamil(out)
    return unicodedata.normalize("NFKD", out).encode("ascii", "ignore").decode()


_FOLDS = (("aa", "a"), ("ee", "i"), ("oo", "u"), ("ou", "u"), ("w", "v"), ("z", "j"), ("ph", "f"), ("q", "k"),
          ("chh", "c"), ("ch", "c"), ("kh", "k"), ("gh", "g"), ("jh", "j"), ("th", "t"), ("dh", "d"), ("bh", "b"),
          ("sh", "s"), ("y", "i"))


def fold(s: str) -> str:
    """Phonetic folding robust to transliteration choices and Indic inherent vowels."""
    s = re.sub(r"[^a-z0-9 ]", " ", romanise(s).lower())
    out = []
    for w in s.split():
        for a, b in _FOLDS:
            w = w.replace(a, b)
        w = re.sub(r"(.)\1+", r"\1", w)
        if len(w) > 3 and w.endswith("a") and not w.endswith("ia"):
            w = w[:-1]                        # 'pamjaba' (Devanagari inherent a) ~ 'punjab'
        out.append(w)
    return " ".join(out)


_DEVOICE = str.maketrans({"g": "k", "d": "t", "b": "p", "j": "c", "s": "c", "f": "p", "h": None})


def devoice(folded: str) -> str:
    """Voicing-neutral form of a folded name; used on both sides when the mention is in Tamil script."""
    return re.sub(r"(.)\1+", r"\1", folded.translate(_DEVOICE))


def skeleton(s: str) -> str:
    """Consonant skeleton of the folded form (vowel choices vary most across transliterations)."""
    return re.sub(r"[aeiou ]", "", fold(s))


@dataclass
class Entity:
    entity_id: str
    level: str
    db_name: str
    display: str
    state: str
    district: str | None
    aliases: set = field(default_factory=set)


def build_gazetteer(con, include_colloquial: bool = True) -> list[Entity]:
    q = lambda s: execute(con, s).rows  # noqa: E731
    ents: dict[tuple, Entity] = {}
    for sid, s in q("SELECT state_id, state_name FROM states"):
        ents[("state", sid)] = Entity(sid, "state", s, display(s), s, None)
    for did, d, s in q("SELECT d.district_id, d.district_name, s.state_name FROM districts d JOIN states s USING(state_id)"):
        ents[("district", did)] = Entity(did, "district", d, display(d), s, d)
    for uid, u, d, s in q("SELECT u.unit_id, u.unit_name, d.district_name, s.state_name FROM assessment_units u "
                          "JOIN districts d ON d.district_id = u.district_id JOIN states s ON s.state_id = u.state_id"):
        ents[("unit", uid)] = Entity(uid, "unit", u, display(u), s, d)
    for e in ents.values():
        e.aliases |= {e.db_name, e.display}
    if include_colloquial:
        by_name = {e.db_name: e for e in ents.values() if e.level in ("district", "state")}
        for alias, target in COLLOQUIAL.items():
            if target in by_name:
                by_name[target].aliases.add(alias)
    return list(ents.values())


def add_history_aliases(gaz: list[Entity], renames: list[tuple[str, str]]):
    """renames: (canonical_id, historical name) pairs, e.g. from reports/crosswalk_renames.csv."""
    idx = {e.entity_id: e for e in gaz}
    for cid, old in renames:
        if cid in idx:
            idx[cid].aliases.add(str(old).replace("_", " "))
