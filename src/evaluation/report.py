"""Breakdowns + bootstrap confidence intervals for per-instance evaluation records."""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

# Romanised-Hindi function / question words (Hinglish). Proxy only; Phase 7 defines the full code-mixing measure.
HINGLISH_HI = set("""ka ki ke mein me mei se tak aur ya hai hain tha thi the kya kitna kitni kitne kaunsa kaunse kaun kis
kab ko ne bhi par pe liye wale wala wali ke hisaab batao do karo hua hui huye bane bana sabse zyada kam jyada beech
saare saara poore poora dono har pehli baar saalana nikalne layak sinchai gharelu baarish zile zila aadhe unka unke
jinka jinki jo jis wahi bhai hisaab badla badli badha ghati rahe rahi aaye""".split())


def code_mix_proxy(question: str, language: str) -> float:
    """Share (0..1) of tokens in the minority 'language' of the sentence; names/numbers excluded roughly."""
    toks = re.findall(r"[^\W\d_]+", question.lower())
    if not toks:
        return 0.0
    if language in ("hindi", "tamil"):
        latin = sum(bool(re.fullmatch(r"[a-z]+", t)) for t in toks)
        return min(latin, len(toks) - latin) / len(toks) if latin else 0.0
    if language == "hinglish":
        hi = sum(t in HINGLISH_HI for t in toks)
        return min(hi, len(toks) - hi) / len(toks)
    return 0.0


def cm_bin(x: float) -> str:
    return "none" if x == 0 else "low(<0.25)" if x < 0.25 else "high(>=0.25)"


def bootstrap_ci(values, n: int = 2000, seed: int = 0) -> tuple[float, float]:
    v = np.asarray(values, dtype=float)
    if len(v) == 0:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    means = rng.choice(v, size=(n, len(v)), replace=True).mean(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def breakdown(df: pd.DataFrame, by: str, metric: str = "correct") -> pd.DataFrame:
    rows = []
    for k, g in df.groupby(by, dropna=False):
        lo, hi = bootstrap_ci(g[metric])
        rows.append({by: k, "n": len(g), metric: round(g[metric].mean(), 4), "ci95_lo": round(lo, 4), "ci95_hi": round(hi, 4)})
    return pd.DataFrame(rows)


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """Add grouping columns used by all baseline/experiment reports."""
    df = df.copy()
    df["n_words"] = df.question.str.split().str.len()
    df["length_bin"] = pd.cut(df.n_words, [0, 10, 15, 20, 1000], labels=["<=10", "11-15", "16-20", ">20"]).astype(str)
    df["code_mix"] = [code_mix_proxy(q, lang) for q, lang in zip(df.question, df.language)]
    df["code_mix_bin"] = df.code_mix.map(cm_bin)
    df["ambiguous_entity"] = df.entities.apply(lambda es: any(e.get("ambiguous_name") for e in es))
    df["noisy"] = df.noise.str.len() > 0
    return df
