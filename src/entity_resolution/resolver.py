"""Hierarchical geographic entity resolver: mention (+ context) -> ranked INGRES locations.

Candidate generation: char 2-4-gram TF-IDF over phonetically folded aliases (+ exact folded matches).
Ranking: logistic regression over string features (TF-IDF cosine, edit ratio on folded form, consonant-skeleton ratio,
exact match), a learned multilingual embedding similarity (multilingual-e5-small, mention vs alias), and hierarchy
context (does a state / district mentioned elsewhere in the question contain the candidate?).

Two comparison spaces are indexed: the folded form, and a voicing-neutral ("devoiced") form used when the mention is
written in Tamil script, which does not distinguish k/g, t/d, p/b, c/j/s.
"""
from __future__ import annotations

import hashlib
import random
import re
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from indic_transliteration import sanscript

from src.entity_resolution.gazetteer import TAMIL, Entity, devoice, fold, romanise, skeleton

FEATURES = ["tfidf", "edit", "skeleton", "exact", "embed", "ctx_state", "ctx_district", "ctx_conflict",
            "lvl_state", "lvl_district", "lvl_unit", "len_diff"]
_VOWELS = re.compile(r"[aeiou ]")


class Resolver:
    def __init__(self, gaz: list[Entity], embedder=None, seed: int = 0, emb_cache: Path | None = None):
        self.gaz = gaz
        self.alias_ent, self.alias_text = [], []
        for i, e in enumerate(gaz):
            for a in sorted(e.aliases):
                self.alias_ent.append(i)
                self.alias_text.append(a)
        folded = [fold(a) for a in self.alias_text]
        self.alias_fold = folded
        self.spaces = {False: self._index(folded), True: self._index([devoice(f) for f in folded])}   # key: Tamil-script mention?
        self.embedder = embedder
        self.E = None
        if embedder is not None:
            texts = [f"passage: {a}" for a in self.alias_text]
            path = Path(emb_cache) / (hashlib.sha1("\n".join(texts).encode()).hexdigest()[:16] + ".npy") if emb_cache else None
            if path is not None and path.exists():
                self.E = np.load(path)
            else:
                self.E = embedder.encode(texts, normalize_embeddings=True, batch_size=128, show_progress_bar=False)
                if path is not None:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    np.save(path, self.E)
        self.ranker: LogisticRegression | None = None
        self.seed = seed

    @staticmethod
    def _index(forms: list[str]) -> dict:
        vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True)
        X = vec.fit_transform(forms)
        exact = {}
        for j, f in enumerate(forms):
            exact.setdefault(f, []).append(j)
        return {"form": forms, "skel": [_VOWELS.sub("", f) for f in forms], "vec": vec, "X": X, "exact": exact}

    def _forms(self, mention: str):
        """(index of the comparison space, mention form, mention skeleton)."""
        ta = bool(TAMIL.search(mention))
        f = devoice(fold(mention)) if ta else fold(mention)
        return self.spaces[ta], f, _VOWELS.sub("", f)

    # ---------------------------------------------------------------- candidates + features
    def _cands(self, sp: dict, f: str, k: int = 30):
        sims = (sp["X"] @ sp["vec"].transform([f]).T).toarray().ravel()
        top = list(np.argsort(-sims)[:k])
        top += [j for j in sp["exact"].get(f, []) if j not in top]
        return top, sims[top]

    def candidates(self, mention: str, k: int = 30) -> list[int]:
        sp, f, _ = self._forms(mention)
        return self._cands(sp, f, k)[0]

    def features(self, mention: str, js: list[int], context: dict | None, m_emb=None, tf=None) -> np.ndarray:
        sp, f, sk = self._forms(mention)
        if tf is None:
            tf = (sp["X"][js] @ sp["vec"].transform([f]).T).toarray().ravel()
        ctx_states = (context or {}).get("states", set())
        ctx_districts = (context or {}).get("districts", set())
        rows = []
        for n, j in enumerate(js):
            e = self.gaz[self.alias_ent[j]]
            af = sp["form"][j]
            emb = float(self.E[j] @ m_emb) if m_emb is not None else 0.0
            rows.append([
                tf[n],
                SequenceMatcher(None, f, af).ratio(),
                SequenceMatcher(None, sk, sp["skel"][j]).ratio(),
                float(f == af),
                emb,
                float(bool(ctx_states) and e.state in ctx_states),
                float(bool(ctx_districts) and e.district in ctx_districts),
                float(bool(ctx_states) and e.level != "state" and e.state not in ctx_states),
                float(e.level == "state"), float(e.level == "district"), float(e.level == "unit"),
                abs(len(f) - len(af)) / max(1, len(f)),
            ])
        return np.asarray(rows, dtype=float)

    def embed(self, mentions: list[str]):
        """Embeddings of several mentions in one batched forward pass (None without an embedder)."""
        if self.embedder is None:
            return [None] * len(mentions)
        return self.embedder.encode([f"query: {m}" for m in mentions], normalize_embeddings=True, batch_size=64,
                                    show_progress_bar=False)

    def resolve(self, mention: str, context: dict | None = None, level: str | None = None, k: int = 5,
                m_emb=None) -> list[tuple[Entity, float]]:
        sp, f, _ = self._forms(mention)
        js, tf = self._cands(sp, f)
        if level:
            keep = [n for n, j in enumerate(js) if self.gaz[self.alias_ent[j]].level == level]
            if keep:
                js, tf = [js[n] for n in keep], tf[keep]
        if m_emb is None:
            m_emb = self.embed([mention])[0]
        F = self.features(mention, js, context, m_emb, tf)
        scores = self.ranker.predict_proba(F)[:, 1] if self.ranker is not None else F[:, 1] + F[:, 0]
        best = {}
        for j, s in zip(js, scores):                     # several aliases of one entity -> keep the best
            ei = self.alias_ent[j]
            if s > best.get(ei, -1):
                best[ei] = s
        ranked = sorted(best.items(), key=lambda x: -x[1])[:k]
        return [(self.gaz[i], float(s)) for i, s in ranked]

    # ---------------------------------------------------------------- learning
    def fit(self, mentions: list[tuple[str, int, dict | None]]):
        """mentions: (mention text, gold entity index, context). Pointwise LR over candidate features."""
        Xs, ys = [], []
        embs = self.embed([m[0] for m in mentions])
        for (text, gold, ctx), m_emb in zip(mentions, embs):
            sp, f, _ = self._forms(text)
            js, tf = self._cands(sp, f)
            if not any(self.alias_ent[j] == gold for j in js):
                continue                                  # candidate generation miss: nothing to learn from
            Xs.append(self.features(text, js, ctx, m_emb, tf))
            ys.append(np.array([self.alias_ent[j] == gold for j in js], dtype=int))
        self.ranker = LogisticRegression(max_iter=2000, class_weight="balanced", random_state=self.seed)
        self.ranker.fit(np.vstack(Xs), np.concatenate(ys))
        return dict(zip(FEATURES, np.round(self.ranker.coef_[0], 3)))


# -------------------------------------------------------------------- noise generators (training + synthetic eval)
def typo(name: str, rng: random.Random) -> str:
    """One keyboard slip; guaranteed to change the string (a no-op 'typo' would silently be an exact mention)."""
    for _ in range(20):
        s = name
        i = rng.randrange(1, max(2, len(s) - 1))
        op = rng.choice(["drop", "swap", "double", "replace"])
        if op == "drop" and len(s) > 4:
            out = s[:i] + s[i + 1:]
        elif op == "swap" and i < len(s) - 1:
            out = s[:i] + s[i + 1] + s[i] + s[i + 2:]
        elif op == "double":
            out = s[:i] + s[i] + s[i:]
        else:
            out = s[:i] + rng.choice("aeiourn") + s[i + 1:]
        if out != name:
            return out
    return name + name[-1]


def translit_variant(name: str, rng: random.Random) -> str:
    """Romanisation alternatives people actually use (aa/a, sh/s, v/w, ee/i, u/oo, dh/d, extra 'h')."""
    subs = [("aa", "a"), ("a", "aa"), ("sh", "s"), ("s", "sh"), ("v", "w"), ("w", "v"), ("ee", "i"), ("i", "ee"),
            ("oo", "u"), ("u", "oo"), ("dh", "d"), ("d", "dh"), ("th", "t"), ("t", "th"), ("ph", "f"), ("j", "z")]
    low = name.lower()
    opts = [(a, b) for a, b in subs if a in low]
    if not opts:
        return name + "h"
    a, b = rng.choice(opts)
    idx = [m.start() for m in re.finditer(re.escape(a), low)]
    i = rng.choice(idx)
    return name[:i] + b + name[i + len(a):]


def punct_space(name: str, rng: random.Random) -> str:
    if " " in name and rng.random() < 0.5:
        return name.replace(" ", "", 1)
    if "-" in name or "_" in name:
        return name.replace("-", " ").replace("_", " ")
    i = rng.randrange(1, max(2, len(name) - 1))
    return name[:i] + rng.choice([" ", "-", "."]) + name[i:]


def to_devanagari(name: str) -> str:
    """Rough automatic Devanagari rendering (ITRANS-style input); used only to create TRAINING noise."""
    return sanscript.transliterate(re.sub(r"[^a-z ]", "", name.lower()), sanscript.ITRANS, sanscript.DEVANAGARI)


def to_tamil(name: str) -> str:
    return sanscript.transliterate(re.sub(r"[^a-z ]", "", name.lower()), sanscript.ITRANS, sanscript.TAMIL)


NOISE = {"exact": lambda s, r: s, "lowercase": lambda s, r: s.lower(), "typo": typo, "translit_variant": translit_variant,
         "punct_space": punct_space, "auto_devanagari": lambda s, r: to_devanagari(s), "auto_tamil": lambda s, r: to_tamil(s)}

__all__ = ["Resolver", "NOISE", "romanise"]
