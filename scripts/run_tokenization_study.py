"""Tokenizer fertility & code-mixing study (Phase 7, descriptive + correlational part).

    python scripts/run_tokenization_study.py

Writes experiments/tokenization/{per_instance.csv, fertility_by_language.csv, correlations.json, cmi.json, fig/*.png}.
All analyses are pre-declared (every tokenizer x language, every outcome); nothing is selected post hoc.
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.benchmark.pool import display  # noqa: E402
from src.evaluation.report import bootstrap_ci  # noqa: E402
from src.tokenization.metrics import LanguageTagger, tokenizer_stats, words  # noqa: E402
from src.utils.safe_sql import connect_ro, execute  # noqa: E402

OUT = ROOT / "experiments/tokenization"
FIG = OUT / "fig"
TOKENIZERS = {"XLM-R (schema linker)": "intfloat/multilingual-e5-small", "Qwen3 (LLM)": "Qwen/Qwen3-8B",
              "mBERT": "bert-base-multilingual-cased", "MuRIL (Indic)": "google/muril-base-cased", "GPT-4o o200k": "Xenova/gpt-4o"}
LANGS = ["english", "hindi", "hinglish", "tamil"]
SEED = 0


def within_item_corr(df, x, y, n_boot=2000):
    """Pearson correlation after removing each item's mean (same question across its 4 language versions)."""
    d = df[["item_id", x, y]].dropna()
    d = d.assign(xd=d[x] - d.groupby("item_id")[x].transform("mean"), yd=d[y] - d.groupby("item_id")[y].transform("mean"))
    r = float(np.corrcoef(d.xd, d.yd)[0, 1]) if d.xd.std() > 0 and d.yd.std() > 0 else float("nan")
    items = d.item_id.unique()
    rng = np.random.default_rng(SEED)
    g = {i: v for i, v in d.groupby("item_id")}
    boots = []
    for _ in range(n_boot):
        s = pd.concat([g[i] for i in rng.choice(items, len(items))])
        if s.xd.std() > 0 and s.yd.std() > 0:
            boots.append(np.corrcoef(s.xd, s.yd)[0, 1])
    return {"r": round(r, 4), "ci95": [round(float(np.percentile(boots, 2.5)), 4), round(float(np.percentile(boots, 97.5)), 4)],
            "n_items": int(len(items))}


def spearman_ci(x, y, n_boot=2000):
    x, y = np.asarray(x, float), np.asarray(y, float)
    rho = spearmanr(x, y).statistic
    rng = np.random.default_rng(SEED)
    bs = [spearmanr(x[i], y[i]).statistic for i in (rng.integers(0, len(x), len(x)) for _ in range(n_boot))]
    return {"rho": round(float(rho), 4), "ci95": [round(float(np.nanpercentile(bs, 2.5)), 4), round(float(np.nanpercentile(bs, 97.5)), 4)], "n": len(x)}


def main():
    from transformers import AutoTokenizer
    OUT.mkdir(parents=True, exist_ok=True)
    FIG.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(x) for x in (ROOT / "data/benchmark/ingres_bench_v1.jsonl").read_text(encoding="utf-8").splitlines()]
    con = connect_ro(ROOT / "data/processed/ingres.db")
    names = [r[0] for r in execute(con, "SELECT unit_name FROM assessment_units UNION SELECT district_name FROM districts "
                                        "UNION SELECT state_name FROM states").rows]
    ent = {w.lower() for n in names for w in words(re.sub(r"[-()_]", " ", display(n))) if re.fullmatch(r"[A-Za-z]+", w)}
    tagger = LanguageTagger(ent)
    toks = {k: AutoTokenizer.from_pretrained(v) for k, v in TOKENIZERS.items()}

    recs = []
    for r in rows:
        tags = tagger.tag(r["question"])
        rec = {"id": r["id"], "item_id": r["item_id"], "language": r["language"], "split": r["split"],
               "difficulty": r["difficulty"], "noisy": bool(r["noise"]), "cmi": tagger.cmi(r["question"]),
               "latin_share": sum(t in ("en",) for t in tags) / max(1, len(tags))}
        for name, tok in toks.items():
            st = tokenizer_stats(tok, r["question"])
            rec.update({f"{name}|{k}": v for k, v in st.items()})
        recs.append(rec)
    df = pd.DataFrame(recs)
    df.to_csv(OUT / "per_instance.csv", index=False)

    # ---------------- fertility by language x tokenizer
    tab = []
    for name in toks:
        for lang in LANGS:
            g = df[df.language == lang]
            tab.append({"tokenizer": name, "language": lang, "n": len(g),
                        "fertility": round(g[f"{name}|fertility"].mean(), 3),
                        "fertility_ci95": [round(v, 3) for v in bootstrap_ci(g[f"{name}|fertility"])],
                        "tokens_per_char": round(g[f"{name}|tokens_per_char"].mean(), 3),
                        "frag_rate": round(g[f"{name}|frag_rate"].mean(), 3),
                        "tokens_per_question": round(g[f"{name}|n_tokens"].mean(), 1)})
    tab = pd.DataFrame(tab)
    tab.to_csv(OUT / "fertility_by_language.csv", index=False)

    # ---------------- code-mixing
    cmi = {"cmi_by_language": df.groupby("language").cmi.agg(["mean", "median", lambda s: (s > 0).mean()]).round(3)
           .rename(columns={"<lambda_0>": "share_mixed"}).to_dict(orient="index"),
           "fertility_vs_cmi_spearman": {}}
    for lang in ("hinglish", "hindi", "tamil"):
        g = df[df.language == lang]
        for name in toks:
            if g.cmi.std() > 0:
                cmi["fertility_vs_cmi_spearman"][f"{lang}|{name}"] = spearman_ci(g.cmi, g[f"{name}|fertility"])
    (OUT / "cmi.json").write_text(json.dumps(cmi, indent=1), encoding="utf-8")

    # ---------------- fertility vs downstream outcomes (eval splits only)
    sl = pd.read_csv(ROOT / "experiments/schema_linking/per_question.csv")
    off = sl[sl.method.str.startswith("3")][["id", "R@3"]].rename(columns={"R@3": "sl_offshelf_R3"})
    ft = sl[sl.method.str.startswith("4")][["id", "R@3"]].rename(columns={"R@3": "sl_finetuned_R3"})
    pred = lambda p: pd.DataFrame([json.loads(x) for x in (ROOT / p).read_text(encoding="utf-8").splitlines()])[["id", "correct"]]  # noqa: E731
    exd = pred("experiments/baselines/D_qwen3_8b_zeroshot/predictions.jsonl").rename(columns={"correct": "ex_qwen3"})
    exa = pred("experiments/baselines/A_keyword_template/predictions.jsonl").rename(columns={"correct": "ex_keywordA"})
    ev = df[df.split.isin(["dev", "test", "hard_test"])].merge(off, how="left").merge(ft, how="left").merge(exd, how="left").merge(exa, how="left")
    pairs = [("sl_offshelf_R3", "XLM-R (schema linker)"), ("sl_finetuned_R3", "XLM-R (schema linker)"),
             ("ex_qwen3", "Qwen3 (LLM)"), ("ex_keywordA", "Qwen3 (LLM)")]   # last = placebo (A uses no subword tokenizer)
    corr = {}
    for outcome, name in pairs:
        x = f"{name}|fertility"
        d = ev.dropna(subset=[outcome])
        corr[f"{outcome} ~ {name} fertility"] = {
            "pooled_spearman": spearman_ci(d[x], d[outcome]),
            "within_language_spearman": {lang: spearman_ci(g[x], g[outcome]) for lang, g in d.groupby("language")},
            "within_item_pearson": within_item_corr(d, x, outcome),
            "outcome_by_language": d.groupby("language")[outcome].mean().round(4).to_dict(),
            "fertility_by_language": d.groupby("language")[x].mean().round(3).to_dict(),
            "placebo": outcome == "ex_keywordA"}
    (OUT / "correlations.json").write_text(json.dumps(corr, indent=1), encoding="utf-8")
    ev.to_csv(OUT / "per_instance_eval.csv", index=False)

    # ---------------- figures
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "Times New Roman", "font.size": 11})
    colors = ["#2E3A59", "#E0703A", "#8B2A2A", "#8A8F99", "#5B8C5A"]
    for metric, ylabel, fname in (("fertility", "Subword tokens per word", "fertility_by_language.png"),
                                  ("frag_rate", "Share of words split into >1 token", "fragmentation_by_language.png")):
        fig, ax = plt.subplots(figsize=(9, 4))
        w = 0.16
        for j, name in enumerate(toks):
            v = [tab[(tab.tokenizer == name) & (tab.language == lang)][metric].iloc[0] for lang in LANGS]
            ax.bar([i + (j - 2) * w for i in range(4)], v, w, label=name, color=colors[j])
        ax.set_xticks(range(4))
        ax.set_xticklabels([lang.capitalize() for lang in LANGS])
        ax.set_ylabel(ylabel)
        ax.legend(fontsize=9, ncol=3)
        fig.tight_layout()
        fig.savefig(FIG / fname, dpi=200)
        plt.close(fig)
    fig, axs = plt.subplots(1, 3, figsize=(12, 3.6), sharey=False)
    for ax, (outcome, name) in zip(axs, pairs[1:]):
        x = f"{name}|fertility"
        for lang, c in zip(LANGS, colors):
            g = ev[ev.language == lang].dropna(subset=[outcome])
            if len(g) < 20:
                continue
            bins = pd.qcut(g[x], 3, duplicates="drop")
            m = g.groupby(bins, observed=True).agg(f=(x, "mean"), y=(outcome, "mean"))
            ax.plot(m.f, m.y, "o-", color=c, label=lang.capitalize())
        ax.set_xlabel(f"{name.split(' (')[0]} fertility (tertiles within language)")
        ax.set_title({"sl_finetuned_R3": "Schema linking R@3 (fine-tuned)", "ex_qwen3": "EX, qwen3:8b zero-shot",
                      "ex_keywordA": "EX, keyword baseline (placebo)"}[outcome], fontsize=11)
    axs[0].legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG / "outcome_vs_fertility.png", dpi=200)
    plt.close(fig)

    print(tab.pivot(index="tokenizer", columns="language", values="fertility").to_string())
    print(tab.pivot(index="tokenizer", columns="language", values="frag_rate").to_string())
    print(json.dumps(cmi["cmi_by_language"], indent=1))
    for k, v in corr.items():
        print(k, "| pooled", v["pooled_spearman"]["rho"], v["pooled_spearman"]["ci95"], "| within-item", v["within_item_pearson"],
              "| within-lang", {lg: s["rho"] for lg, s in v["within_language_spearman"].items()})


if __name__ == "__main__":
    main()
