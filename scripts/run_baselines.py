"""Run Text-to-SQL baselines on INGRES-Bench and score execution accuracy.

    python scripts/run_baselines.py --baseline A                 # keyword / template retrieve-and-fill
    python scripts/run_baselines.py --baseline D --splits test   # Gemini (see src/baselines/llm.py)

Writes experiments/baselines/<name>/predictions.jsonl, metrics.json and updates experiments/baselines/results.json.
"""
import argparse
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.evaluation.execution import execution_match  # noqa: E402
from src.evaluation.report import breakdown, enrich  # noqa: E402
from src.utils.safe_sql import connect_ro  # noqa: E402

BENCH = ROOT / "data/benchmark/ingres_bench_v1.jsonl"
OUT = ROOT / "experiments/baselines"


def git_hash() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        return "unknown"


def load_system(name: str, con, rows, args):
    train = [r for r in rows if r["split"] == "train"]
    if name == "A":
        from src.baselines.keyword import KeywordBaseline
        return KeywordBaseline(con, train)
    if name == "D":
        from src.baselines.llm import GeminiBaseline
        return GeminiBaseline(con, train, model=args.model, few_shot=args.few_shot, patient=args.patient)
    raise SystemExit(f"unknown baseline {name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--splits", nargs="*", default=["dev", "test", "hard_test"])
    ap.add_argument("--model", default=None)
    ap.add_argument("--few-shot", type=int, default=0)
    ap.add_argument("--limit", type=int, default=None, help="evaluate only the first N instances (smoke test)")
    ap.add_argument("--patient", action="store_true", help="LLM: many retries with long backoff (free-tier overload)")
    args = ap.parse_args()

    rows = [json.loads(line) for line in BENCH.read_text(encoding="utf-8").splitlines()]
    con = connect_ro(ROOT / "data/processed/ingres.db")
    system = load_system(args.baseline, con, rows, args)
    evalset = [r for sp in args.splits for r in rows if r["split"] == sp][: args.limit]  # splits in the given order

    recs, partial = [], None
    t_all = time.perf_counter()
    for i, r in enumerate(evalset, 1):
        t0 = time.perf_counter()
        try:
            pred = system.predict(r["question"])
        except Exception as e:  # e.g. QuotaExhausted: keep what we have; a rerun resumes from the LLM cache
            partial = f"stopped at {i}/{len(evalset)}: {type(e).__name__}: {str(e)[:200]}"
            print("  " + partial)
            break
        latency = time.perf_counter() - t0
        ex = execution_match(con, pred.get("sql"), r["sql"], r["gold_result"])
        recs.append({**{k: r[k] for k in ("id", "item_id", "split", "language", "difficulty", "intent", "question",
                                           "entities", "noise", "sql")},
                     "pred_sql": pred.get("sql"), "correct": int(ex.correct), "exec_error": ex.error,
                     "latency_s": round(latency, 4), **{k: v for k, v in pred.items() if k != "sql"}})
        if i % 100 == 0 or i == len(evalset):
            print(f"  {i}/{len(evalset)}  EX so far {sum(x['correct'] for x in recs) / len(recs):.3f}", flush=True)
    wall = time.perf_counter() - t_all

    out = OUT / system.name
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "predictions.jsonl", "w", encoding="utf-8") as f:
        for x in recs:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    df = enrich(pd.DataFrame(recs))
    metrics = {
        "experiment_id": f"{system.name}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        "baseline": system.name, "git_commit": git_hash(), "benchmark": BENCH.name, "splits": args.splits,
        "n": len(df), "partial": partial, "execution_accuracy": round(df.correct.mean(), 4),
        "exact_match_sql": round((df.pred_sql.str.strip() == df.sql.str.strip()).mean(), 4),
        "exec_error_rate": round(df.exec_error.notna().mean(), 4),
        "latency_mean_s": round(df.latency_s.mean(), 4), "wall_time_s": round(wall, 1),
        "hardware": platform.processor() or platform.machine(), "python": platform.python_version(),
        "config": getattr(system, "config", {}),
        "usage": getattr(system, "usage", {}),
        "breakdowns": {by: breakdown(df, by).to_dict("records")
                       for by in ("split", "language", "difficulty", "length_bin", "code_mix_bin", "ambiguous_entity", "noisy", "intent")},
    }
    by_split_lang = df.pivot_table(index="split", columns="language", values="correct", aggfunc="mean").round(4)
    metrics["split_x_language"] = by_split_lang.to_dict()
    (out / "metrics.json").write_text(json.dumps(metrics, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    res_path = OUT / "results.json"
    allres = json.loads(res_path.read_text(encoding="utf-8")) if res_path.exists() else {}
    allres[system.name] = {k: metrics[k] for k in ("experiment_id", "git_commit", "n", "partial", "splits", "execution_accuracy",
                                                   "exact_match_sql", "exec_error_rate", "latency_mean_s", "config", "usage")}
    allres[system.name]["by_split_x_language"] = metrics["split_x_language"]
    res_path.write_text(json.dumps(allres, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n{system.name}: EX = {metrics['execution_accuracy']} on {len(df)} instances")
    print(by_split_lang.to_string())
    print(breakdown(df, "difficulty").to_string(index=False))


if __name__ == "__main__":
    main()
