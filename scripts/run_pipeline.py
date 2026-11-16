"""Full pipeline evaluation, ablations and error analysis.

    python scripts/run_pipeline.py --stage places                                   # tune the place linker on DEV (no LLM)
    python scripts/run_pipeline.py --stage run --config v2 --splits dev             # then test hard_test
    python scripts/run_pipeline.py --stage run --config full --splits test          # v2 code without year hints
    python scripts/run_pipeline.py --stage run --config v2_loio --splits test       # examples of the question's own type hidden
    python scripts/run_pipeline.py --stage summary

Outputs go to experiments/pipeline_v2/ (--out). The original system's runs (git tag baseline-v1) are frozen in
experiments/pipeline/ and are only read here, for paired comparisons.

Configs: v2 = schema hints + place hints + retrieved examples + year hints + repair.  full / no_fewshot / no_places /
no_schema = the baseline-v1 configurations (no year hints) under the current code.  v2_loio = v2 with every TRAIN
example of the question's own intent hidden from retrieval ("leave own intent out").
First-attempt (no-repair) accuracy needs no run: it is recorded for every question.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.evaluation.execution import execution_match  # noqa: E402
from src.evaluation.report import bootstrap_ci  # noqa: E402
from src.utils.safe_sql import connect_ro  # noqa: E402

BASELINE = ROOT / "experiments/pipeline"            # frozen baseline-v1 outputs
OUT = ROOT / "experiments/pipeline_v2"
V1 = {"year_hints": False}
CONFIGS = {"v2": {}, "v2_loio": {}, "full": V1, "no_fewshot": {**V1, "fewshot": False}, "no_places": {**V1, "places": False},
           "no_schema": {**V1, "schema_hints": False}}
BENCH = ROOT / "data/benchmark/ingres_bench_v1.jsonl"


def load():
    rows = [json.loads(x) for x in BENCH.read_text(encoding="utf-8").splitlines()]
    return rows, [r for r in rows if r["split"] == "train"]


def load_jsonl(p):
    return pd.DataFrame([json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines()])


def stage_places():
    from sentence_transformers import SentenceTransformer
    from src.pipeline.agent import PlaceLinker
    rows, train = load()
    dev = [r for r in rows if r["split"] == "dev"]
    con = connect_ro(ROOT / "data/processed/ingres.db")
    pl = PlaceLinker(con, SentenceTransformer("intfloat/multilingual-e5-small", device="cpu"), train)
    res = {}
    for tau in (0.5, 0.7, 0.8, 0.9, 0.95, 0.98):
        pl.tau = tau
        tp = fp = fn = 0
        by_lang = {}
        t0 = time.perf_counter()
        for r in dev:
            pred = {(p["level"], p["db_name"].lower()) for p in pl.link(r["question"])}
            gold = {(e["type"], e["db_name"].lower()) for e in r["entities"]}
            a, b, c = len(pred & gold), len(pred - gold), len(gold - pred)
            tp, fp, fn = tp + a, fp + b, fn + c
            s = by_lang.setdefault(r["language"], [0, 0, 0])
            s[0], s[1], s[2] = s[0] + a, s[1] + b, s[2] + c
        f1 = lambda a, b, c: round(2 * a / max(1, 2 * a + b + c), 4)  # noqa: E731
        res[tau] = {"precision": round(tp / max(1, tp + fp), 4), "recall": round(tp / max(1, tp + fn), 4), "f1": f1(tp, fp, fn),
                    "f1_by_language": {k: f1(*v) for k, v in by_lang.items()},
                    "recall_by_language": {k: round(v[0] / max(1, v[0] + v[2]), 4) for k, v in by_lang.items()},
                    "s_per_question": round((time.perf_counter() - t0) / len(dev), 3)}
        print(tau, res[tau], flush=True)
    best = max(res, key=lambda t: res[t]["f1"])
    (OUT / "places_dev.json").write_text(json.dumps({"by_tau": res, "chosen_tau": best}, indent=1), encoding="utf-8")


def stage_run(config, splits):
    from src.pipeline.agent import Pipeline
    rows, train = load()
    ev = [r for sp in splits for r in rows if r["split"] == sp]
    con = connect_ro(ROOT / "data/processed/ingres.db")
    tau = json.loads((OUT / "places_dev.json").read_text())["chosen_tau"]
    pipe = Pipeline(con, train, **CONFIGS[config])
    if pipe.places:
        pipe.places.tau = float(tau)
    path = OUT / f"{config}.jsonl"
    done = {json.loads(x)["id"] for x in path.read_text(encoding="utf-8").splitlines()} if path.exists() else set()
    with open(path, "a", encoding="utf-8") as f:
        for i, r in enumerate(ev, 1):
            if r["id"] in done:
                continue
            o = pipe.sql(r["question"], exclude_intent=r["intent"] if config.endswith("_loio") else None)
            o.pop("result")
            ex = execution_match(con, o["sql"], r["sql"], r["gold_result"])
            ex0 = execution_match(con, o["first_sql"], r["sql"], r["gold_result"])
            gold_places = {e["db_name"].lower() for e in r["entities"]}
            f.write(json.dumps({"id": r["id"], "language": r["language"], "split": r["split"], "difficulty": r["difficulty"],
                                "intent": r["intent"], "noisy": bool(r["noise"]), "correct": int(ex.correct),
                                "correct_first_attempt": int(ex0.correct), "exec_error": ex.error,
                                "n_attempts": len(o["attempts"]), "places_ok": int(gold_places <= {p["db_name"].lower() for p in o["places"]}),
                                **{k: o[k] for k in ("sql", "first_sql", "hints", "places", "years", "latency_s", "prompt_tokens", "output_tokens")}},
                               ensure_ascii=False) + "\n")
            f.flush()
            if i % 50 == 0:
                print(f"  {config} {i}/{len(ev)}", flush=True)


AGG = re.compile(r"\b(AVG|SUM|COUNT|MAX|MIN)\s*\(", re.I)
YEARS = re.compile(r"'(\d{4}-\d{4})'")
METRIC = re.compile(r"\b(?:ua|da|sa|a|b|ua2)\.(\w+)")


def sql_has_places(sql, entities) -> bool:
    s = (sql or "").lower()
    return all(e["db_name"].lower().replace("'", "''") in s for e in entities)


def error_category(r, gold):
    """Rule-based, first match wins; every rule looks at the predicted SQL itself (the baseline-v1 version used the
    place linker's output for the place category, which over-counted place errors)."""
    pred = r["sql"] or ""
    if r["exec_error"]:
        return "no SQL / execution error"
    if not sql_has_places(pred, gold["entities"]):
        return "gold place literal missing from SQL"
    if set(YEARS.findall(pred)) != set(YEARS.findall(gold["sql"])):
        return "wrong assessment year"
    if set(METRIC.findall(pred)) - {"unit_id", "assessment_year"} != set(METRIC.findall(gold["sql"])) - {"unit_id", "assessment_year"}:
        return "wrong metric / column"
    if sorted(m.upper() for m in AGG.findall(pred)) != sorted(m.upper() for m in AGG.findall(gold["sql"])):
        return "wrong aggregation"
    return "other (filters, joins, output shape)"


def error_analysis(df, gold, out_csv=None):
    err = df[df.correct == 0].copy()
    err["category"] = [error_category(r, gold[r["id"]]) for r in err.to_dict("records")]
    if out_csv:
        err.to_csv(out_csv, index=False)
    return {"n_errors": len(err), "counts": err.category.value_counts().to_dict(),
            "share_of_errors": err.category.value_counts(normalize=True).round(4).to_dict(),
            "by_language": err.groupby(["language", "category"]).size().unstack(fill_value=0).to_dict(orient="index")}


def mcnemar(a, b):
    """Paired exact test on the instances both runs share. Returns wins of a, wins of b, two-sided p."""
    from scipy.stats import binomtest
    m = a[["id", "correct"]].merge(b[["id", "correct"]], on="id", suffixes=("_a", "_b"))
    w = int(((m.correct_a == 1) & (m.correct_b == 0)).sum())
    l = int(((m.correct_a == 0) & (m.correct_b == 1)).sum())
    return {"n": len(m), "wins": w, "losses": l, "p": float(binomtest(w, w + l).pvalue) if w + l else 1.0}


def stage_summary():
    gold = {json.loads(x)["id"]: json.loads(x) for x in BENCH.read_text(encoding="utf-8").splitlines()}

    def summ(df, col="correct"):
        lo, hi = bootstrap_ci(df[col])
        return {"n": len(df), "EX": round(df[col].mean(), 4), "EX_ci95": [round(lo, 4), round(hi, 4)],
                "by_language": df.groupby("language")[col].mean().round(4).to_dict(),
                "by_difficulty": df.groupby("difficulty")[col].mean().round(4).to_dict()}
    runs = {"baseline-v1 full": load_jsonl(BASELINE / "full.jsonl")}
    for cfg in CONFIGS:
        if (OUT / f"{cfg}.jsonl").exists():
            runs[cfg] = load_jsonl(OUT / f"{cfg}.jsonl")
    out = {}
    for split in ("dev", "test", "hard_test"):
        res = {}
        for name, df in runs.items():
            d = df[df.split == split]
            if not len(d):
                continue
            yr_ok = [set(YEARS.findall(s or "")) == set(YEARS.findall(gold[i]["sql"])) for i, s in zip(d.id, d.sql)]
            res[name] = {**summ(d), "first_attempt_EX": round(d.correct_first_attempt.mean(), 4),
                         "llm_latency_mean_s": round(d.latency_s.mean(), 3), "prompt_tokens_mean": round(d.prompt_tokens.mean(), 1),
                         "repair_turns_mean": round(d.n_attempts.mean() - 1, 3),
                         "linker_found_all_places": round(d.places_ok.mean(), 4),
                         "sql_has_all_gold_places": round(sum(sql_has_places(s, gold[i]["entities"]) for i, s in zip(d.id, d.sql)) / len(d), 4),
                         "sql_year_set_correct": round(sum(yr_ok) / len(d), 4)}
        if res:
            out[split] = res
    pairs = {}
    for a, b in (("v2", "baseline-v1 full"), ("full", "baseline-v1 full"), ("v2", "full"), ("v2", "v2_loio")):
        if a in runs and b in runs:
            for split in ("test", "hard_test"):
                x, y = runs[a][runs[a].split == split], runs[b][runs[b].split == split]
                if len(x) and len(y):
                    pairs[f"{a} vs {b} [{split}]"] = mcnemar(x, y)
    out["paired_tests"] = pairs
    ev = lambda d: d[d.split.isin(["test", "hard_test"])]  # noqa: E731
    out["error_analysis"] = {name: error_analysis(ev(df), gold, OUT / f"errors_{name.replace(' ', '_')}.csv")
                             for name, df in runs.items() if name in ("baseline-v1 full", "v2") and len(ev(df))}
    (OUT / "results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for split, res in out.items():
        if split in ("paired_tests", "error_analysis"):
            print(f"== {split}\n" + json.dumps(res if split == "paired_tests" else {k: v["counts"] for k, v in res.items()}, indent=1))
            continue
        print(f"== {split}")
        for k, v in res.items():
            print(f"  {k:18s} EX {v['EX']:.3f} {v['EX_ci95']} n={v['n']} first {v['first_attempt_EX']:.3f} places-in-SQL "
                  f"{v['sql_has_all_gold_places']:.3f} years {v['sql_year_set_correct']:.3f} {v['by_language']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["places", "run", "summary"])
    ap.add_argument("--config", default="v2", choices=list(CONFIGS))
    ap.add_argument("--splits", nargs="+", default=["test"])
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    OUT = Path(a.out)
    OUT.mkdir(parents=True, exist_ok=True)
    {"places": stage_places, "run": lambda: stage_run(a.config, a.splits), "summary": stage_summary}[a.stage]()
