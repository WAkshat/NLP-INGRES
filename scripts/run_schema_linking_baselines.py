"""Schema-linking baselines B (BM25) and C (off-the-shelf multilingual embeddings) + random reference.

    python scripts/run_schema_linking_baselines.py

Evaluated on dev + test + hard_test (no training involved). Writes experiments/schema_linking/baselines.json
and experiments/schema_linking/baselines_by_language.csv.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.evaluation.report import bootstrap_ci  # noqa: E402
from src.schema_linking.retrieval import (BM25Retriever, EmbeddingRetriever, gold_elements,  # noqa: E402
                                          init_elements, rank_metrics)

SPLITS = ("dev", "test", "hard_test")
OUT = ROOT / "experiments/schema_linking"


def evaluate(name, score_matrix, rows, els):
    recs = []
    for r, sc in zip(rows, score_matrix):
        gt, gc = gold_elements(r)
        for kind, gold in (("column", gc), ("table", gt)):
            m = rank_metrics(sc, els, gold, kind)
            if m:
                recs.append({"method": name, "id": r["id"], "language": r["language"], "split": r["split"],
                             "difficulty": r["difficulty"], "kind": kind, **m})
    return recs


def main():
    schema = json.loads((ROOT / "data/schema/schema.json").read_text(encoding="utf-8"))
    els = init_elements(schema)
    rows = [json.loads(line) for line in (ROOT / "data/benchmark/ingres_bench_v1.jsonl").read_text(encoding="utf-8").splitlines()]
    rows = [r for r in rows if r["split"] in SPLITS]
    qs = [r["question"] for r in rows]
    print(f"{len(els)} schema elements ({sum(e.kind == 'column' for e in els)} columns), {len(rows)} questions")

    recs, timing = [], {}
    rng = np.random.default_rng(0)
    recs += evaluate("random (no linking)", rng.random((len(rows), len(els))), rows, els)
    t = time.perf_counter()
    bm = BM25Retriever(els)
    recs += evaluate(BM25Retriever.name, np.stack([bm.scores(q) for q in qs]), rows, els)
    timing[BM25Retriever.name] = (time.perf_counter() - t) / len(qs)
    t = time.perf_counter()
    em = EmbeddingRetriever(els)
    t_q = time.perf_counter()
    recs += evaluate(EmbeddingRetriever.name, em.scores_batch(qs), rows, els)
    timing[EmbeddingRetriever.name] = (time.perf_counter() - t_q) / len(qs)
    timing["C_model_load_and_index_s"] = t_q - t

    df = pd.DataFrame(recs)
    OUT.mkdir(parents=True, exist_ok=True)
    cols = df[df.kind == "column"]
    table = cols.pivot_table(index="method", columns="language", values="R@3", aggfunc="mean")
    table["overall"] = cols.groupby("method")["R@3"].mean()
    table = table[["english", "hindi", "hinglish", "tamil", "overall"]].round(3)
    summary = {}
    for (method, kind), g in df.groupby(["method", "kind"]):
        summary.setdefault(method, {})[kind] = {
            **{k: round(g[k].mean(), 4) for k in ("R@1", "R@3", "R@5", "MRR")},
            "R@3_ci95": [round(x, 4) for x in bootstrap_ci(g["R@3"])],
            "by_language": {lang: {k: round(x[k].mean(), 4) for k in ("R@1", "R@3", "R@5", "MRR")}
                            for lang, x in g.groupby("language")}}
    (OUT / "baselines.json").write_text(json.dumps({"splits": SPLITS, "n_questions": len(rows), "n_elements": len(els),
                                                     "latency_per_query_s": timing, "results": summary}, indent=1), encoding="utf-8")
    table.to_csv(OUT / "baselines_by_language.csv")
    print("\nColumn Recall@3 by language (dev+test+hard_test):")
    print(table.to_string())
    print("\nOverall (columns | tables):")
    for m, v in summary.items():
        print(f"  {m:28s} col R@1 {v['column']['R@1']:.3f} R@3 {v['column']['R@3']:.3f} R@5 {v['column']['R@5']:.3f} MRR {v['column']['MRR']:.3f}"
              f" | tab R@1 {v['table']['R@1']:.3f} R@3 {v['table']['R@3']:.3f} MRR {v['table']['MRR']:.3f}")
    print("latency/query:", {k: round(v, 5) for k, v in timing.items()})


if __name__ == "__main__":
    main()
