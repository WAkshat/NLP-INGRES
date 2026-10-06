"""Train the learned schema linker (Phase 5) and evaluate it against the baselines.

    python scripts/train_schema_linker.py                 # fine-tune multilingual-e5-small on TRAIN
    python scripts/train_schema_linker.py --eval-only     # re-evaluate saved checkpoint

Writes experiments/schema_linking/checkpoints/finetuned_e5/ (git-ignored), schema_linking/finetuned.json and
schema_linking/ablation_by_language.csv (no linking / BM25 / off-the-shelf / fine-tuned).
"""
import argparse
import json
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.evaluation.report import bootstrap_ci  # noqa: E402
from src.schema_linking.retrieval import BM25Retriever, EmbeddingRetriever, gold_elements, init_elements, rank_metrics  # noqa: E402
from src.schema_linking.train import build_pairs, train  # noqa: E402

OUT = ROOT / "experiments/schema_linking"
CKPT = OUT / "checkpoints/finetuned_e5"
EVAL_SPLITS = ("dev", "test", "hard_test")


def evaluate(name, scores, rows, els):
    recs = []
    for r, sc in zip(rows, scores):
        _, gc = gold_elements(r)
        m = rank_metrics(sc, els, gc, "column")
        if m:
            heldout = r["template_id"].endswith(f"#{N_TEMPLATES[(r['intent'], r['language'])] - 1}")
            recs.append({"method": name, "id": r["id"], "language": r["language"], "split": r["split"],
                         "difficulty": r["difficulty"], "heldout_phrasing": heldout, "noisy": bool(r["noise"]), **m})
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval-only", action="store_true")
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--k-hard", type=int, default=3)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--intent-holdout", type=float, default=0.0,
                    help="hold out this fraction of intents from training; evaluate on held-out intents only")
    args = ap.parse_args()
    if args.intent_holdout:
        return intent_holdout(args)
    torch.manual_seed(args.seed)

    from sentence_transformers import SentenceTransformer
    from src.benchmark.intents import INTENTS
    global N_TEMPLATES
    N_TEMPLATES = {(i["id"], lang): len(t) for i in INTENTS for lang, t in i["templates"].items()}

    schema = json.loads((ROOT / "data/schema/schema.json").read_text(encoding="utf-8"))
    els = init_elements(schema)
    rows = [json.loads(x) for x in (ROOT / "data/benchmark/ingres_bench_v1.jsonl").read_text(encoding="utf-8").splitlines()]
    train_rows = [r for r in rows if r["split"] == "train"]
    eval_rows = [r for r in rows if r["split"] in EVAL_SPLITS]
    info = {"seed": args.seed, "epochs": args.epochs, "k_hard": args.k_hard, "base_model": EmbeddingRetriever.model_id,
            "hardware": platform.processor(), "train_questions": len(train_rows)}

    if not args.eval_only:
        model = SentenceTransformer(EmbeddingRetriever.model_id, device="cpu")
        pairs = build_pairs(train_rows, els, k_hard=args.k_hard, seed=args.seed)
        info["train_pairs"] = len(pairs)
        print(f"training on {len(pairs)} (question, column, {args.k_hard} hard negatives) pairs")
        info.update(train(model, pairs, epochs=args.epochs, seed=args.seed))
        CKPT.mkdir(parents=True, exist_ok=True)
        model.save(str(CKPT))
    ft = EmbeddingRetriever(els, model=SentenceTransformer(str(CKPT), device="cpu"))
    ft.name = "D_finetuned_e5_small"
    base = EmbeddingRetriever(els)
    qs = [r["question"] for r in eval_rows]
    rng = np.random.default_rng(0)
    bm = BM25Retriever(els)
    recs = (evaluate("1 no schema linking (random)", rng.random((len(qs), len(els))), eval_rows, els)
            + evaluate("2 BM25", np.stack([bm.scores(q) for q in qs]), eval_rows, els)
            + evaluate("3 off-the-shelf mE5-small", base.scores_batch(qs), eval_rows, els)
            + evaluate("4 fine-tuned mE5-small (ours)", ft.scores_batch(qs), eval_rows, els))
    df = pd.DataFrame(recs)
    table = df.pivot_table(index="method", columns="language", values="R@3", aggfunc="mean")
    table["overall"] = df.groupby("method")["R@3"].mean()
    table = table[["english", "hindi", "hinglish", "tamil", "overall"]].round(3)
    summary = {m: {**{k: round(g[k].mean(), 4) for k in ("R@1", "R@3", "R@5", "MRR")},
                   "R@3_ci95": [round(x, 4) for x in bootstrap_ci(g["R@3"])],
                   "by_language": {lang: {k: round(x[k].mean(), 4) for k in ("R@1", "R@3", "R@5", "MRR")} for lang, x in g.groupby("language")},
                   "heldout_phrasing_R@3": round(g[g.heldout_phrasing]["R@3"].mean(), 4),
                   "seen_phrasing_R@3": round(g[~g.heldout_phrasing]["R@3"].mean(), 4),
                   "by_split_R@3": {s: round(x["R@3"].mean(), 4) for s, x in g.groupby("split")}}
               for m, g in df.groupby("method")}
    (OUT / "finetuned.json").write_text(json.dumps({"info": info, "eval_splits": EVAL_SPLITS, "results": summary}, indent=1), encoding="utf-8")
    table.to_csv(OUT / "ablation_by_language.csv")
    df.to_csv(OUT / "per_question.csv", index=False)
    print("\nColumn Recall@3 (dev+test+hard_test):")
    print(table.to_string())
    for m, v in summary.items():
        print(f"  {m:32s} R@1 {v['R@1']:.3f} R@3 {v['R@3']:.3f} R@5 {v['R@5']:.3f} MRR {v['MRR']:.3f} | held-out phrasing R@3 {v['heldout_phrasing_R@3']:.3f}")


def intent_holdout(args):
    """Generalisation to unseen QUESTION TYPES: train without a random fraction of intents, test on those only."""
    import random
    from sentence_transformers import SentenceTransformer
    from src.benchmark.intents import INTENTS
    global N_TEMPLATES
    N_TEMPLATES = {(i["id"], lang): len(t) for i in INTENTS for lang, t in i["templates"].items()}
    schema = json.loads((ROOT / "data/schema/schema.json").read_text(encoding="utf-8"))
    els = init_elements(schema)
    rows = [json.loads(x) for x in (ROOT / "data/benchmark/ingres_bench_v1.jsonl").read_text(encoding="utf-8").splitlines()]
    intents = sorted({r["intent"] for r in rows})
    held = set(random.Random(args.seed).sample(intents, round(args.intent_holdout * len(intents))))
    train_rows = [r for r in rows if r["split"] == "train" and r["intent"] not in held]
    eval_rows = [r for r in rows if r["split"] in EVAL_SPLITS and r["intent"] in held]
    model = SentenceTransformer(EmbeddingRetriever.model_id, device="cpu")
    info = train(model, build_pairs(train_rows, els, k_hard=args.k_hard, seed=args.seed), epochs=args.epochs, seed=args.seed)
    qs = [r["question"] for r in eval_rows]
    ft = EmbeddingRetriever(els, model=model)
    recs = (evaluate("3 off-the-shelf mE5-small", EmbeddingRetriever(els).scores_batch(qs), eval_rows, els)
            + evaluate("4 fine-tuned (unseen intents)", ft.scores_batch(qs), eval_rows, els))
    df = pd.DataFrame(recs)
    table = df.pivot_table(index="method", columns="language", values="R@3", aggfunc="mean")
    table["overall"] = df.groupby("method")["R@3"].mean()
    res = {"seed": args.seed, "held_out_intents": sorted(held), "n_eval": int(len(eval_rows)), **info,
           "R@3": table.round(4).to_dict(orient="index")}
    path = OUT / "intent_holdout.json"
    allres = json.loads(path.read_text()) if path.exists() else []
    allres = [x for x in allres if x["seed"] != args.seed] + [res]
    path.write_text(json.dumps(allres, indent=1), encoding="utf-8")
    print(f"held-out intents (seed {args.seed}): {sorted(held)}")
    print(table.round(3).to_string())


if __name__ == "__main__":
    main()
