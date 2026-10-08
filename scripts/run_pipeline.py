"""Phase 9: full pipeline evaluation + component ablations.

    python scripts/run_pipeline.py --stage places                       # tune / evaluate the place linker on DEV (no LLM)
    python scripts/run_pipeline.py --stage run --config full --splits test hard_test
    python scripts/run_pipeline.py --stage run --config no_fewshot      # (test)
    python scripts/run_pipeline.py --stage run --config no_places       # (test)
    python scripts/run_pipeline.py --stage summary

Configs: full = schema hints + place hints + retrieved few-shot + repair. "no_repair" needs no run: it is the first
attempt of each run. D (zero-shot) and D + schema hints come from Phases 4 and 7.
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

OUT = ROOT / "experiments/pipeline"
CONFIGS = {"full": {}, "no_fewshot": {"fewshot": False}, "no_places": {"places": False}, "no_schema": {"schema_hints": False}}


def load():
    rows = [json.loads(x) for x in (ROOT / "data/benchmark/ingres_bench_v1.jsonl").read_text(encoding="utf-8").splitlines()]
    return rows, [r for r in rows if r["split"] == "train"]


def stage_places():
    from sentence_transformers import SentenceTransformer
    from src.pipeline.agent import PlaceLinker
    rows, train = load()
    dev = [r for r in rows if r["split"] == "dev"]
    con = connect_ro(ROOT / "data/processed/ingres.db")
    pl = PlaceLinker(con, SentenceTransformer("intfloat/multilingual-e5-small", device="cpu"), train)
    cache, orig = {}, pl.res.resolve

    def cached(m, ctx=None, level=None, k=5):
        key = (m, json.dumps(ctx, default=sorted, sort_keys=True), level, k)
        if key not in cache:
            cache[key] = orig(m, ctx, level, k)
        return cache[key]
    pl.res.resolve = cached
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
                    "f1_by_language": {k: f1(*v) for k, v in by_lang.items()}, "s_per_question": round((time.perf_counter() - t0) / len(dev), 3)}
        print(tau, res[tau], flush=True)
    best = max(res, key=lambda t: res[t]["f1"])
    OUT.mkdir(parents=True, exist_ok=True)
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
            o = pipe.sql(r["question"])
            o.pop("result")
            ex = execution_match(con, o["sql"], r["sql"], r["gold_result"])
            ex0 = execution_match(con, o["first_sql"], r["sql"], r["gold_result"])
            gold_places = {e["db_name"].lower() for e in r["entities"]}
            f.write(json.dumps({"id": r["id"], "language": r["language"], "split": r["split"], "difficulty": r["difficulty"],
                                "intent": r["intent"], "noisy": bool(r["noise"]), "correct": int(ex.correct),
                                "correct_first_attempt": int(ex0.correct), "exec_error": ex.error,
                                "n_attempts": len(o["attempts"]), "places_ok": int(gold_places <= {p["db_name"].lower() for p in o["places"]}),
                                **{k: o[k] for k in ("sql", "first_sql", "hints", "places", "latency_s", "prompt_tokens", "output_tokens")}},
                               ensure_ascii=False) + "\n")
            f.flush()
            if i % 50 == 0:
                print(f"  {config} {i}/{len(ev)}", flush=True)


AGG = re.compile(r"\b(AVG|SUM|COUNT|MAX|MIN)\s*\(", re.I)
YEARS = re.compile(r"'(\d{4}-\d{4})'")
METRIC = re.compile(r"\b(?:ua|da|sa|a|b|ua2)\.(\w+)")


def error_category(r, gold_sql):
    """First matching rule wins (rule-based; categories overlap in reality)."""
    pred = r["sql"] or ""
    if r["exec_error"]:
        return "no SQL / execution error"
    if not r["places_ok"]:
        return "place not linked (resolver miss)"
    if set(YEARS.findall(pred)) != set(YEARS.findall(gold_sql)):
        return "wrong assessment year"
    if set(METRIC.findall(pred)) - {"unit_id", "assessment_year"} != set(METRIC.findall(gold_sql)) - {"unit_id", "assessment_year"}:
        return "wrong metric / column"
    if sorted(m.upper() for m in AGG.findall(pred)) != sorted(m.upper() for m in AGG.findall(gold_sql)):
        return "wrong aggregation"
    return "other (filters, joins, output shape)"


def error_analysis(df):
    gold = {json.loads(x)["id"]: json.loads(x)["sql"] for x in (ROOT / "data/benchmark/ingres_bench_v1.jsonl").read_text(encoding="utf-8").splitlines()}
    err = df[df.correct == 0].copy()
    err["category"] = [error_category(r, gold[r["id"]]) for r in err.to_dict("records")]
    err.to_csv(OUT / "errors_full.csv", index=False)
    return {"n_errors": len(err), "share_of_errors": err.category.value_counts(normalize=True).round(4).to_dict(),
            "by_language": err.groupby(["language", "category"]).size().unstack(fill_value=0).to_dict(orient="index")}


def stage_summary():
    def load_jsonl(p):
        return pd.DataFrame([json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines()])

    def summ(df, col="correct"):
        lo, hi = bootstrap_ci(df[col])
        return {"n": len(df), "EX": round(df[col].mean(), 4), "EX_ci95": [round(lo, 4), round(hi, 4)],
                "by_language": df.groupby("language")[col].mean().round(4).to_dict(),
                "by_difficulty": df.groupby("difficulty")[col].mean().round(4).to_dict()}
    out = {}
    d = load_jsonl(ROOT / "experiments/baselines/D_qwen3_8b_zeroshot/predictions.jsonl")
    a = load_jsonl(ROOT / "experiments/baselines/A_keyword_template/predictions.jsonl")
    h = ROOT / "experiments/tokenization/hints_ft.jsonl"
    for split in ("test", "hard_test"):
        res = {"A keyword/template": summ(a[a.split == split]), "D qwen3:8b zero-shot": summ(d[d.split == split])}
        if split == "test" and h.exists():
            res["D + schema hints"] = summ(load_jsonl(h))
        for cfg in CONFIGS:
            p = OUT / f"{cfg}.jsonl"
            if p.exists():
                df = load_jsonl(p)
                df = df[df.split == split]
                if len(df):
                    res[f"pipeline {cfg}"] = {**summ(df), "latency_mean_s": round(df.latency_s.mean(), 3),
                                              "prompt_tokens_mean": round(df.prompt_tokens.mean(), 1),
                                              "repair_turns_mean": round(df.n_attempts.mean() - 1, 3),
                                              "places_all_found": round(df.places_ok.mean(), 4) if cfg != "no_places" else None}
                    res[f"pipeline {cfg}, first attempt (no repair)"] = summ(df, "correct_first_attempt")
        out[split] = res
    if (OUT / "full.jsonl").exists():
        out["error_analysis_full"] = error_analysis(load_jsonl(OUT / "full.jsonl"))
    (OUT / "results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for split, res in out.items():
        if split.startswith("error"):
            print(json.dumps(res["share_of_errors"], indent=1))
            continue
        print(f"== {split}")
        for k, v in res.items():
            print(f"  {k:55s} EX {v['EX']:.3f} {v['EX_ci95']}  n={v['n']}  {v['by_language']}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["places", "run", "summary"])
    ap.add_argument("--config", default="full", choices=list(CONFIGS))
    ap.add_argument("--splits", nargs="+", default=["test"])
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    {"places": stage_places, "run": lambda: stage_run(a.config, a.splits), "summary": stage_summary}[a.stage]()
