"""Tokenizer fertility and code-mixing measures.

Per question and tokenizer:
  words           whitespace tokens with surrounding punctuation stripped (Python's \\w would split Indic words at vowel signs)
  fertility       subword tokens / words   (Rust et al., ACL 2021)
  tokens_per_char subword tokens / non-space characters
  frag_rate       share of words split into >= 2 subword tokens ("proportion of continued words")
Code-Mixing Index (Gambäck & Das, LREC 2016): CMI = 100 * (1 - max_i w_i / (n - u)), u = language-independent tokens.
Word-level language tags: Devanagari -> hi, Tamil script -> ta; Latin words -> en / hi (romanised) via lexicons built
from TRAIN questions + a char n-gram classifier for unseen words; place names and numbers are language-independent;
words that are both English and romanised Hindi ("the" = थे, "me", "do", "par") take the sentence's majority tag.
"""
from __future__ import annotations

import re
import string
from collections import Counter

from sklearn.feature_extraction.text import CountVectorizer
from sklearn.naive_bayes import MultinomialNB

from src.evaluation.report import HINGLISH_HI

PUNCT = string.punctuation + "।॥“”‘’…–—"
DEVANAGARI = re.compile(r"[ऀ-ॿ]")
TAMIL = re.compile(r"[஀-௿]")
AMBIGUOUS = {"the", "me", "do", "to", "par", "pe", "ki", "hai", "a", "in", "is", "se", "bhi"}


def words(text: str) -> list[str]:
    return [w for w in (t.strip(PUNCT) for t in text.split()) if w]


def tokenizer_stats(tok, text: str) -> dict:
    ws = words(text)
    n_tok = len(tok(text, add_special_tokens=False)["input_ids"])
    pieces = [len(tok(w, add_special_tokens=False)["input_ids"]) for w in ws]
    chars = len(re.sub(r"\s", "", text))
    return {"n_words": len(ws), "n_tokens": n_tok, "fertility": n_tok / max(1, len(ws)),
            "tokens_per_char": n_tok / max(1, chars), "frag_rate": sum(p > 1 for p in pieces) / max(1, len(ws))}


def template_lexicons() -> tuple[set, set]:
    """English / romanised-Hindi word lists from the benchmark's phrasing templates and lexicon (slots removed, so
    no place names leak in). Words used in both English and Hinglish templates are English."""
    from src.benchmark import lexicon as L
    from src.benchmark.intents import INTENTS

    def ws(texts):
        return {w.lower() for t in texts for w in words(re.sub(r"\{\w+\}", " ", t)) if re.fullmatch(r"[a-zA-Z]+", w)}
    en_txt = [t for i in INTENTS for t in i["templates"]["english"]]
    en_txt += [s for m in L.METRICS.values() for s, _ in m["english"]] + [f for c in L.CATEGORIES.values() for f in c["english"]]
    en_txt += [v[0] + " " + v[1] for v in (L.UNIT_TYPES[k]["english"] for k in L.UNIT_TYPES)] + ["assessment district state"]
    hing_txt = [t for i in INTENTS for t in i["templates"]["hinglish"]]
    hing_txt += [s for m in L.METRICS.values() for s, _ in m["hinglish"]] + ["ke assessment mein me"]
    en = ws(en_txt)
    return en, (ws(hing_txt) - en) | HINGLISH_HI


class LanguageTagger:
    def __init__(self, entity_tokens: set[str]):
        self.en, self.hi = template_lexicons()
        self.en -= HINGLISH_HI - AMBIGUOUS
        self.entity = entity_tokens - self.en - self.hi
        X = sorted(self.en - self.hi) + sorted(self.hi - self.en)
        y = ["en"] * len(self.en - self.hi) + ["hi"] * len(self.hi - self.en)
        self.vec = CountVectorizer(analyzer="char_wb", ngram_range=(2, 4))
        self.nb = MultinomialNB().fit(self.vec.fit_transform(X), y)

    def tag(self, text: str) -> list[str]:
        tags = []
        for w in words(text):
            lw = w.lower()
            if DEVANAGARI.search(w):
                tags.append("hi")
            elif TAMIL.search(w):
                tags.append("ta")
            elif re.fullmatch(r"[\d.,%\-/]+", w) or lw in self.entity or not re.search(r"[a-z]", lw):
                tags.append("u")
            elif lw in AMBIGUOUS:
                tags.append("?")
            elif lw in self.hi and lw not in self.en:
                tags.append("hi")
            elif lw in self.en:
                tags.append("en")
            else:
                tags.append(self.nb.predict(self.vec.transform([lw]))[0])
        majority = Counter(t for t in tags if t not in ("u", "?")).most_common(1)
        return [majority[0][0] if t == "?" and majority else ("u" if t == "?" else t) for t in tags]

    def cmi(self, text: str) -> float:
        tags = [t for t in self.tag(text) if t != "u"]
        if not tags:
            return 0.0
        return 100.0 * (1 - Counter(tags).most_common(1)[0][1] / len(tags))
