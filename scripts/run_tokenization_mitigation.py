"""Tokenization mitigation experiment (Phase 7). Stages (each cached / resumable):

    python scripts/run_tokenization_mitigation.py --stage translate   # Method 1: translate -> English -> SQL (LLM)
    python scripts/run_tokenization_mitigation.py --stage vocab       # Method 3: vocabulary-adapted encoder (CPU)
    python scripts/run_tokenization_mitigation.py --stage hints       # EX with top-5 linker hints (FT vs vocab-adapted)
    python scripts/run_tokenization_mitigation.py --stage summary     # experiments/tokenization/mitigation.json

Method 2 (direct multilingual) = baseline D (experiments/baselines/D_qwen3_8b_zeroshot).
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.evaluation.execution import execution_match  # noqa: E402
from src.evaluation.report import bootstrap_ci  # noqa: E402
from src.utils.safe_sql import connect_ro  # noqa: E402

OUT = ROOT / "experiments/tokenization"
EVAL = ("dev", "test", "hard_test")
MODEL = "qwen3:8b"
FT_CKPT = ROOT / "experiments/schema_linking/checkpoints/finetuned_e5"
VA_CKPT = ROOT / "experiments/tokenization/checkpoints/vocab_adapted_e5"


def load_rows():
    rows = [json.loads(x) for x in (ROOT / "data/benchmark/ingres_bench_v1.jsonl").read_text(encoding="utf-8").splitlines()]
    return rows, [r for r in rows if r["split"] == "train"], [r for sp in EVAL for r in rows if r["split"] == sp]


def write_jsonl(path, recs):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for x in recs:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")


def stage_translate():
    from src.baselines.llm import LLMBaseline, OllamaClient
    from src.tokenization.mitigation import translate
    rows, train, ev = load_rows()
    con = connect_ro(ROOT / "data/processed/ingres.db")
    sql_model = LLMBaseline(con, train, model=MODEL, backend="ollama")
    tr_client = OllamaClient(MODEL, max_tokens=256)
    recs = []
    for i, r in enumerate(ev, 1):
        t = translate(tr_client, r["question"], r["language"])
        p = sql_model.predict(t["text"])
        ex = execution_match(con, p["sql"], r["sql"], r["gold_result"])
        recs.append({"id": r["id"], "language": r["language"], "split": r["split"], "difficulty": r["difficulty"],
                     "translation": t["text"], "pred_sql": p["sql"], "correct": int(ex.correct),
                     "latency_s": round(t["latency_s"] + p["api_latency_s"], 3),
                     "prompt_tokens": t["prompt_tokens"] + p["prompt_tokens"], "output_tokens": t["output_tokens"] + p["output_tokens"]})
        if i % 100 == 0:
            print(f"  {i}/{len(ev)} EX so far {np.mean([x['correct'] for x in recs]):.3f}", flush=True)
    write_jsonl(OUT / "method1_translate.jsonl", recs)
    print("Method 1 EX", np.mean([x["correct"] for x in recs]))


def stage_vocab(epochs=3, seed=0, n_new=400):
    import torch
    from sentence_transformers import SentenceTransformer
    from src.schema_linking.retrieval import EmbeddingRetriever, gold_elements, init_elements, rank_metrics
    from src.schema_linking.train import build_pairs, train
    from src.tokenization.metrics import tokenizer_stats
    from src.tokenization.mitigation import adapt_vocabulary, select_new_tokens
    torch.manual_seed(seed)
    rows, train_rows, ev = load_rows()
    els = init_elements(json.loads((ROOT / "data/schema/schema.json").read_text(encoding="utf-8")))
    base_tok = SentenceTransformer(EmbeddingRetriever.model_id, device="cpu")[0].tokenizer
    new = select_new_tokens(train_rows, base_tok, n=n_new)
    t0 = time.time()
    if not VA_CKPT.exists():
        model = SentenceTransformer(EmbeddingRetriever.model_id, device="cpu")
        added = adapt_vocabulary(model, new)
        info = train(model, build_pairs(train_rows, els, k_hard=3, seed=seed), epochs=epochs, seed=seed)
        VA_CKPT.mkdir(parents=True, exist_ok=True)
        model.save(str(VA_CKPT))
        (VA_CKPT / "adaptation.json").write_text(json.dumps({"new_words": new, "added_tokens": added, **info}, ensure_ascii=False, indent=1), encoding="utf-8")
    meta = json.loads((VA_CKPT / "adaptation.json").read_text(encoding="utf-8"))
    res = {}
    for name, path in (("fine-tuned (Phase 5)", FT_CKPT), ("fine-tuned + vocabulary adaptation", VA_CKPT)):
        m = SentenceTransformer(str(path), device="cpu")
        tok = m[0].tokenizer
        r = EmbeddingRetriever(els, model=m)
        qs = [x["question"] for x in ev]
        t1 = time.perf_counter()
        S = r.scores_batch(qs)
        enc_s = (time.perf_counter() - t1) / len(qs)
        recs = []
        for x, sc in zip(ev, S):
            _, gc = gold_elements(x)
            mt = rank_metrics(sc, els, gc, "column")
            st = tokenizer_stats(tok, x["question"])
            recs.append({"id": x["id"], "language": x["language"], **st, **({k: v for k, v in mt.items()} if mt else {})})
        df = pd.DataFrame(recs)
        res[name] = {"vocab_size": len(tok), "params_M": round(sum(p.numel() for p in m.parameters()) / 1e6, 2),
                     "encode_latency_ms": round(1000 * enc_s, 2),
                     "by_language": {lang: {"fertility": round(g.fertility.mean(), 3), "frag_rate": round(g.frag_rate.mean(), 3),
                                            "R@3": round(g["R@3"].mean(), 4), "MRR": round(g["MRR"].mean(), 4)}
                                     for lang, g in df.groupby("language")},
                     "overall": {"fertility": round(df.fertility.mean(), 3), "R@3": round(df["R@3"].mean(), 4),
                                 "R@3_ci95": [round(v, 4) for v in bootstrap_ci(df["R@3"].dropna())], "MRR": round(df["MRR"].mean(), 4)}}
        df.to_csv(OUT / f"method3_{'va' if 'vocabulary' in name else 'ft'}_per_question.csv", index=False)
    res["adaptation"] = {"new_words_requested": len(meta["new_words"]), "added_tokens": meta["added_tokens"],
                         "train_time_s": meta.get("train_time_s"), "examples": meta["new_words"][:25]}
    (OUT / "method3_vocab.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v.get("overall", v) for k, v in res.items()}, ensure_ascii=False, indent=1))


def stage_hints(k=5, splits=("test",)):
    from sentence_transformers import SentenceTransformer
    from src.baselines.llm import LLMBaseline
    from src.schema_linking.retrieval import EmbeddingRetriever, init_elements
    rows, train, _ = load_rows()
    ev = [r for sp in splits for r in rows if r["split"] == sp]
    con = connect_ro(ROOT / "data/processed/ingres.db")
    els = init_elements(json.loads((ROOT / "data/schema/schema.json").read_text(encoding="utf-8")))
    cols = [i for i, e in enumerate(els) if e.kind == "column"]
    llm = LLMBaseline(con, train, model=MODEL, backend="ollama")
    for tag, path in (("ft", FT_CKPT), ("va", VA_CKPT)):
        S = EmbeddingRetriever(els, model=SentenceTransformer(str(path), device="cpu")).scores_batch([r["question"] for r in ev])
        recs = []
        for r, sc in zip(ev, S):
            hints = [els[i].key for i in sorted(cols, key=lambda i: -sc[i])[:k]]
            p = llm.predict(r["question"], hints=hints)
            ex = execution_match(con, p["sql"], r["sql"], r["gold_result"])
            recs.append({"id": r["id"], "language": r["language"], "split": r["split"], "difficulty": r["difficulty"],
                         "hints": hints, "pred_sql": p["sql"], "correct": int(ex.correct), "latency_s": p["api_latency_s"],
                         "prompt_tokens": p["prompt_tokens"], "output_tokens": p["output_tokens"]})
        write_jsonl(OUT / f"hints_{tag}.jsonl", recs)
        print(tag, "EX with hints:", np.mean([x["correct"] for x in recs]), flush=True)


def stage_summary():
    def load(p):
        return pd.DataFrame([json.loads(x) for x in Path(p).read_text(encoding="utf-8").splitlines()])
    d = load(ROOT / "experiments/baselines/D_qwen3_8b_zeroshot/predictions.jsonl")
    m1 = load(OUT / "method1_translate.jsonl")
    out = {}
    for name, df in (("Method 2: direct (baseline D)", d), ("Method 1: translate -> English -> SQL", m1)):
        lat = df["latency_s"] if "latency_s" in df else df["api_latency_s"]
        out[name] = {"n": len(df), "EX": round(df.correct.mean(), 4), "EX_ci95": [round(v, 4) for v in bootstrap_ci(df.correct)],
                     "EX_by_language": df.groupby("language").correct.mean().round(4).to_dict(),
                     "latency_mean_s": round(lat.mean(), 3),
                     "prompt_tokens_mean": round(df.prompt_tokens.mean(), 1), "output_tokens_mean": round(df.output_tokens.mean(), 1)}
    sub = {"test"}
    for tag, label in (("ft", "direct + fine-tuned linker hints"), ("va", "direct + vocabulary-adapted linker hints")):
        p = OUT / f"hints_{tag}.jsonl"
        if p.exists():
            h = load(p)
            out[label] = {"n": len(h), "EX": round(h.correct.mean(), 4), "EX_ci95": [round(v, 4) for v in bootstrap_ci(h.correct)],
                          "EX_by_language": h.groupby("language").correct.mean().round(4).to_dict(),
                          "latency_mean_s": round(h.latency_s.mean(), 3), "prompt_tokens_mean": round(h.prompt_tokens.mean(), 1)}
    dd = d[d.split.isin(sub)]
    out["direct (baseline D), test only"] = {"n": len(dd), "EX": round(dd.correct.mean(), 4),
                                                       "EX_by_language": dd.groupby("language").correct.mean().round(4).to_dict()}
    if (OUT / "method3_vocab.json").exists():
        out["Method 3: schema linker vocabulary adaptation"] = json.loads((OUT / "method3_vocab.json").read_text(encoding="utf-8"))
    (OUT / "mitigation.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: {kk: v[kk] for kk in ("n", "EX", "EX_by_language") if kk in v} for k, v in out.items() if "EX" in v},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["translate", "vocab", "hints", "summary"])
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    {"translate": stage_translate, "vocab": stage_vocab, "hints": stage_hints, "summary": stage_summary}[a.stage]()
