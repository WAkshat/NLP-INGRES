"""Automatic sanity check of the authored Devanagari / Tamil name renderings.

Each rendering is romanised back (indic_transliteration, ISO 15919 -> ASCII) and compared with the English
display name after a coarse phonetic folding (aspiration, vowel length, voicing that Tamil script does not mark).
Renderings below the threshold are printed for correction. Exit code 1 if any fail.
"""
import json
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from indic_transliteration import sanscript

ROOT = Path(__file__).resolve().parents[1]
THRESHOLD = 0.55
# flagged by the heuristic, then checked by hand and kept (reason in comment)
REVIEWED_OK = {("South East", "hi"), ("South East", "ta"),  # English words transliterated sound-for-sound
               ("Lakshadweep", "ta")}                        # standard Tamil exonym இலட்சத்தீவு
# words people translate rather than transliterate (English, and romanised Hindi / Tamil forms) -> dropped before comparing
TRANSLATED_WORDS = ["east", "west", "north", "south", "and", "islands", "hills", "part", "pradesh",
                    "dakṣiṇa", "paścima", "pūrvī", "aura", "dvīpasamūha", "bhāga", "hilsa", "pradēśa",
                    "kiḻakku", "mēṟku", "teṟku", "teṉmēṟku", "maṟṟum", "tīvukaḷ", "malaikaḷ", "pakuti", "piratēcam"]
FOLDS = [("chh", "c"), ("kh", "k"), ("gh", "k"), ("ch", "c"), ("jh", "c"), ("th", "t"), ("dh", "t"), ("ph", "p"),
         ("bh", "p"), ("sh", "s"), ("ea", "i"), ("ee", "i"), ("oo", "u"), ("w", "v"), ("z", "j"), ("f", "p"),
         ("q", "k"), ("y", "i")]


def _word(w: str) -> str:
    w = unicodedata.normalize("NFKD", w).encode("ascii", "ignore").decode().lower()
    w = re.sub(r"[^a-z]", "", w)
    for a, b in FOLDS:
        w = w.replace(a, b)
    # Tamil script does not mark voicing; Devanagari romanisation adds an inherent final 'a'
    w = w.translate(str.maketrans("gdbj", "ktpc")).replace("h", "")
    w = re.sub(r"(.)\1+", r"\1", w)
    return w[:-1] if len(w) > 3 and w.endswith("a") else w


TRANSLATED = {_word(w) for w in TRANSLATED_WORDS}


def fold(s: str) -> str:
    return "".join(x for x in (_word(w) for w in re.split(r"[\s\-().,]+", s)) if x and x not in TRANSLATED)


def romanise(text: str, script: str) -> str:
    return sanscript.transliterate(text, script, sanscript.ISO)


def main() -> int:
    tr = json.loads((ROOT / "data/benchmark/transliterations.json").read_text(encoding="utf-8"))
    bad = []
    for name, v in tr.items():
        if name.startswith("_"):
            continue
        for lang, script in (("hi", sanscript.DEVANAGARI), ("ta", sanscript.TAMIL)):
            back = romanise(v[lang], script)
            a, b = fold(name), fold(back)
            sim = SequenceMatcher(None, a, b).ratio() if a and b else float(a == b)  # guard: never pass on empty folds
            if sim < THRESHOLD and (name, lang) not in REVIEWED_OK:
                bad.append((round(sim, 2), lang, name, v[lang], back))
    n = 2 * (len(tr) - 1)
    print(f"{n - len(bad) - len(REVIEWED_OK)}/{n} renderings pass (threshold {THRESHOLD}); "
          f"{len(REVIEWED_OK)} flagged but manually reviewed as correct; {len(bad)} failing")
    for b in sorted(bad):
        print("  ", b)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
