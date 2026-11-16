"""Performance benchmark (latency, throughput, memory) of the INGRES pipeline.

    python scripts/benchmark_perf.py --label baseline --stage components     # no LLM needed
    python scripts/benchmark_perf.py --label baseline --stage llm            # needs `ollama serve` + qwen3:8b
    python scripts/benchmark_perf.py --label baseline --stage e2e            # full pipeline, LLM cache bypassed

Writes experiments/perf/<label>_<stage>.json with the environment, the method and the raw per-request timings.
Questions: the first N//4 TEST questions of each language (fixed order, so runs are comparable). Warm-up requests use
DEV questions, so no measured request repeats a warm-up request.
All latencies are wall-clock (time.perf_counter) on this machine; nothing is extrapolated.
"""
import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "experiments/perf"
WARM = []


def stats(xs):
    xs = np.asarray(xs, float)
    return {"n": int(len(xs)), "mean_ms": round(1000 * xs.mean(), 2), "median_ms": round(1000 * float(np.median(xs)), 2),
            "p90_ms": round(1000 * float(np.percentile(xs, 90)), 2), "p95_ms": round(1000 * float(np.percentile(xs, 95)), 2),
            "p99_ms": round(1000 * float(np.percentile(xs, 99)), 2), "std_ms": round(1000 * xs.std(), 2),
            "throughput_per_s": round(len(xs) / xs.sum(), 2)}


def _mem():
    """(current, peak) working-set bytes of this process. Windows API via ctypes; no extra dependency."""
    import ctypes
    from ctypes import wintypes

    class PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (n, ctypes.c_size_t) for n in ("PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage",
                                           "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    c = PMC()
    c.cb = ctypes.sizeof(c)
    k = ctypes.WinDLL("kernel32")
    k.GetCurrentProcess.restype = wintypes.HANDLE
    psapi = ctypes.WinDLL("psapi")
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    psapi.GetProcessMemoryInfo(k.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.WorkingSetSize, c.PeakWorkingSetSize


def rss_mb():
    return round(_mem()[0] / 2**20, 1)


def peak_rss_mb():
    return round(_mem()[1] / 2**20, 1)


def gpu():
    try:
        o = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,driver_version",
                            "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=20).stdout.strip()
        n, used, total, util, drv = [x.strip() for x in o.split(",")]
        return {"name": n, "vram_used_mib": int(used), "vram_total_mib": int(total), "util_pct": int(util), "driver": drv}
    except Exception as e:  # no GPU / no nvidia-smi
        return {"error": str(e)}


def _ram_gb():
    import ctypes
    kb = ctypes.c_ulonglong(0)
    ctypes.windll.kernel32.GetPhysicallyInstalledSystemMemory(ctypes.byref(kb))
    return round(kb.value / 2**20, 1)


def environment():
    import sentence_transformers
    import torch
    import transformers
    git = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "src"], capture_output=True, text=True, cwd=ROOT).stdout.strip())
    return {"git_commit": git, "src_dirty": dirty, "os": platform.platform(), "python": platform.python_version(),
            "cpu": platform.processor(), "cpu_logical": os.cpu_count(), "ram_gb": _ram_gb(),
            "torch": torch.__version__, "torch_threads": torch.get_num_threads(), "transformers": transformers.__version__,
            "sentence_transformers": sentence_transformers.__version__, "gpu": gpu(),
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def questions(n):
    rows = [json.loads(x) for x in (ROOT / "data/benchmark/ingres_bench_v1.jsonl").read_text(encoding="utf-8").splitlines()]
    train = [r for r in rows if r["split"] == "train"]
    test = [r for r in rows if r["split"] == "test"]
    qs = [r for lang in ("english", "hindi", "hinglish", "tamil") for r in [x for x in test if x["language"] == lang][: n // 4]]
    global WARM
    WARM = [r for r in rows if r["split"] == "dev"][::7]      # spread over languages; never part of the measured set
    return rows, train, qs


def build_pipeline(train, timings=None):
    """Builds the pipeline exactly as the app does; records component load times when `timings` is given."""
    from sentence_transformers import SentenceTransformer
    from src.pipeline.agent import FT_CKPT, Pipeline, PlaceLinker
    from src.schema_linking.retrieval import EmbeddingRetriever
    from src.utils.safe_sql import connect_ro
    t = timings if timings is not None else {}
    con = connect_ro(ROOT / "data/processed/ingres.db")
    r0 = rss_mb()
    t0 = time.perf_counter()
    enc = SentenceTransformer(str(FT_CKPT), device="cpu")
    t["load_finetuned_encoder_s"] = round(time.perf_counter() - t0, 2)
    t0 = time.perf_counter()
    base = SentenceTransformer(EmbeddingRetriever.model_id, device="cpu")
    t["load_base_encoder_s"] = round(time.perf_counter() - t0, 2)
    t0 = time.perf_counter()
    pl = PlaceLinker(con, base, train)
    t["build_place_linker_s"] = round(time.perf_counter() - t0, 2)
    t0 = time.perf_counter()
    pipe = Pipeline(con, train, encoder=enc, place_linker=pl)
    t["build_pipeline_index_s"] = round(time.perf_counter() - t0, 2)
    t["cold_start_total_s"] = round(sum(v for k, v in t.items() if k.endswith("_s")), 2)
    t["rss_before_mb"], t["rss_after_load_mb"] = r0, rss_mb()
    tau = ROOT / "experiments/pipeline/places_dev.json"
    pipe.places.tau = float(json.loads(tau.read_text())["chosen_tau"])
    return pipe


def stage_components(label, n, warmup):
    rows, train, qs = questions(n)
    load = {}
    pipe = build_pipeline(train, load)
    cols = pipe.cols
    enc_t, link_t, place_t, shot_t, total_t, n_spans, toks = [], [], [], [], [], [], []
    from src.tokenization.metrics import words
    for i, r in enumerate(WARM[:warmup] + qs):
        q = r["question"]
        t0 = time.perf_counter()
        q_emb = pipe.enc.encode([f"query: {q}"], normalize_embeddings=True)[0]
        t1 = time.perf_counter()
        sc = q_emb @ pipe.linker.E.T
        _ = [pipe.els[j].key for j in sorted(cols, key=lambda j: -sc[j])[:5]]
        t2 = time.perf_counter()
        places = pipe.places.link(q)
        t3 = time.perf_counter()
        _ = pipe._examples(q_emb)
        t4 = time.perf_counter()
        if i >= warmup:
            enc_t.append(t1 - t0); link_t.append(t2 - t1); place_t.append(t3 - t2); shot_t.append(t4 - t3); total_t.append(t4 - t0)
            n_spans.append(len(words(q)))
            toks.append(len(pipe.enc[0].tokenizer(q)["input_ids"]))
    by_lang = {}
    for lang in ("english", "hindi", "hinglish", "tamil"):
        idx = [i for i, r in enumerate(qs) if r["language"] == lang]
        by_lang[lang] = {"place_link": stats([place_t[i] for i in idx]), "total_pre_llm": stats([total_t[i] for i in idx])}
    # batch-size scaling of the encoder (queries/s)
    texts = [f"query: {r['question']}" for r in qs]
    scaling = {}
    for bs in (1, 8, 32, 64):
        t0 = time.perf_counter()
        pipe.enc.encode(texts, normalize_embeddings=True, batch_size=bs)
        scaling[bs] = round(len(texts) / (time.perf_counter() - t0), 1)
    out = {"label": label, "stage": "components", "environment": environment(),
           "method": {"questions": len(qs), "warmup_runs": warmup, "device": "cpu", "batch_size": 1, "concurrency": 1,
                      "mean_words": round(float(np.mean(n_spans)), 1), "mean_encoder_tokens": round(float(np.mean(toks)), 1)},
           "load": load, "peak_rss_mb": peak_rss_mb(),
           "query_encode": stats(enc_t), "schema_rank": stats(link_t), "place_link": stats(place_t),
           "example_retrieval": stats(shot_t), "total_pre_llm": stats(total_t), "by_language": by_lang,
           "encoder_batch_scaling_queries_per_s": scaling,
           "raw": {"query_encode": enc_t, "place_link": place_t, "total_pre_llm": total_t}}
    return out


def ollama_chat(body, stream=False):
    import urllib.request
    req = urllib.request.Request("http://127.0.0.1:11434/api/chat", json.dumps({**body, "stream": stream}).encode(),
                                 {"Content-Type": "application/json"})
    t0 = time.perf_counter()
    ttft, last = None, None
    with urllib.request.urlopen(req, timeout=900) as r:
        if not stream:
            return json.load(r), time.perf_counter() - t0, None
        for line in r:
            if not line.strip():
                continue
            d = json.loads(line)
            if ttft is None and d.get("message", {}).get("content"):
                ttft = time.perf_counter() - t0
            last = d
    return last, time.perf_counter() - t0, ttft


def stage_llm(label, n, warmup):
    """Raw LLM serving performance with the exact pipeline prompts (no response cache; streaming for TTFT)."""
    from src.baselines.llm import SYSTEM
    from src.pipeline.agent import PlaceLinker
    rows, train, qs = questions(n)
    pipe = build_pipeline(train)
    g0 = gpu()
    bodies = []
    for r in WARM[:warmup] + qs:
        q = r["question"]
        q_emb = pipe.enc.encode([f"query: {q}"], normalize_embeddings=True)[0]
        sc = q_emb @ pipe.linker.E.T
        hints = [pipe.els[j].key for j in sorted(pipe.cols, key=lambda j: -sc[j])[:5]]
        prompt = pipe.llm.prompt(q, hints, pipe._examples(q_emb), PlaceLinker.render(pipe.places.link(q)))
        bodies.append({"model": pipe.llm.client.model, "think": False, "options": pipe.llm.client.options,
                       "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]})
    # cold start: first request after the model is unloaded
    ollama_chat({"model": bodies[0]["model"], "messages": [], "keep_alive": 0})
    time.sleep(2)
    d, cold_wall, cold_ttft = ollama_chat(bodies[0], stream=True)      # bodies[0] is a warm-up (DEV) prompt
    cold = {"wall_s": round(cold_wall, 2), "ttft_s": round(cold_ttft or 0, 2), "model_load_s": round(d.get("load_duration", 0) / 1e9, 2)}
    wall, ttft, ptok, otok, peval, geval = [], [], [], [], [], []
    for i, b in enumerate(bodies):
        d, w, t = ollama_chat(b, stream=True)
        if i >= warmup:
            wall.append(w); ttft.append(t or w)
            ptok.append(d.get("prompt_eval_count", 0)); otok.append(d.get("eval_count", 0))
            peval.append(d.get("prompt_eval_duration", 0) / 1e9); geval.append(d.get("eval_duration", 0) / 1e9)
    g1 = gpu()
    ps = subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout
    return {"label": label, "stage": "llm", "environment": environment(),
            "method": {"questions": len(qs), "warmup_runs": warmup, "concurrency": 1, "streaming": True, "response_cache": "bypassed",
                       "options": bodies[0]["options"], "model": bodies[0]["model"], "think": False},
            "cold_start": cold, "request_wall": stats(wall), "time_to_first_token": stats(ttft),
            "prompt_tokens_mean": round(float(np.mean(ptok)), 1), "output_tokens_mean": round(float(np.mean(otok)), 1),
            "generation_tokens_per_s": round(sum(otok) / max(1e-9, sum(geval)), 1),
            "prompt_eval_tokens_per_s": round(sum(ptok) / max(1e-9, sum(peval)), 1),
            "gpu_before": g0, "gpu_after": g1, "ollama_ps": ps,
            "raw": {"wall": wall, "ttft": ttft, "prompt_tokens": ptok, "output_tokens": otok}}


def stage_e2e(label, n, warmup):
    """Whole Pipeline.sql wall-clock per question with the LLM response cache disabled."""
    import src.baselines.llm as llm
    rows, train, qs = questions(n)
    pipe = build_pipeline(train)
    import tempfile
    llm.CACHE = Path(tempfile.mkdtemp(prefix="ingres_nocache_"))        # empty cache dir => every call hits the model
    wall, llm_s, attempts = [], [], []
    for i, r in enumerate(WARM[:warmup] + qs):
        t0 = time.perf_counter()
        o = pipe.sql(r["question"])
        w = time.perf_counter() - t0
        if i >= warmup:
            wall.append(w); llm_s.append(o["latency_s"]); attempts.append(len(o["attempts"]))
    by_lang = {lang: stats([wall[i] for i, r in enumerate(qs) if r["language"] == lang]) for lang in ("english", "hindi", "hinglish", "tamil")}
    return {"label": label, "stage": "e2e", "environment": environment(),
            "method": {"questions": len(qs), "warmup_runs": warmup, "concurrency": 1, "response_cache": "bypassed (empty temp dir)"},
            "pipeline_sql_wall": stats(wall), "llm_share_of_wall": round(sum(llm_s) / sum(wall), 4),
            "non_llm_overhead": stats([w - l for w, l in zip(wall, llm_s)]), "mean_attempts": round(float(np.mean(attempts)), 3),
            "by_language": by_lang, "peak_rss_mb": peak_rss_mb(), "gpu": gpu(), "raw": {"wall": wall, "llm": llm_s}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--stage", required=True, choices=["components", "llm", "e2e"])
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--warmup", type=int, default=5)
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    res = {"components": stage_components, "llm": stage_llm, "e2e": stage_e2e}[a.stage](a.label, a.n, a.warmup)
    (OUT / f"{a.label}_{a.stage}.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k not in ("raw", "environment")}, indent=1))
