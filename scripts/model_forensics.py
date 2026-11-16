"""Model forensics: exact, programmatically derived facts about every model INGRES loads.

    python scripts/model_forensics.py            -> experiments/forensics/models.json

- Encoders (base / fine-tuned / vocabulary-adapted multilingual-e5-small): parameter enumeration with torch,
  config, tokenizer, on-disk size, HF snapshot revision, and a tensor-shape trace of one question.
- LLM (qwen3:8b in Ollama): the GGUF file is parsed directly (metadata + every tensor's shape and storage type),
  so the parameter count is exact and not taken from a model card.
- Entity-resolver ranker (logistic regression): coefficients + intercept.
Nothing here is estimated; a value that cannot be read is written as null.
"""
import json
import pickle
import struct
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "experiments/forensics"
FT = ROOT / "experiments/schema_linking/checkpoints/finetuned_e5"
VA = ROOT / "experiments/tokenization/checkpoints/vocab_adapted_e5"
BASE_ID = "intfloat/multilingual-e5-small"

# ---------------------------------------------------------------------------------- GGUF
GGUF_TYPES = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}
GGML_TYPE = {0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 6: "Q5_0", 7: "Q5_1", 8: "Q8_0", 9: "Q8_1", 10: "Q2_K", 11: "Q3_K",
             12: "Q4_K", 13: "Q5_K", 14: "Q6_K", 15: "Q8_K", 30: "BF16"}


def _read(f, fmt):
    return struct.unpack(fmt, f.read(struct.calcsize(fmt)))[0]


def _string(f):
    return f.read(_read(f, "<Q")).decode("utf-8", "replace")


def _value(f, t, keep_arrays=False):
    if t == 8:
        return _string(f)
    if t == 9:
        et, n = _read(f, "<I"), _read(f, "<Q")
        vals = [_value(f, et) for _ in range(n)]
        return vals if keep_arrays or n <= 16 else {"array_len": n}
    return _read(f, GGUF_TYPES[t])


def parse_gguf(path: Path) -> dict:
    with open(path, "rb") as f:
        assert f.read(4) == b"GGUF", "not a GGUF file"
        version, n_tensors, n_kv = _read(f, "<I"), _read(f, "<Q"), _read(f, "<Q")
        meta = {}
        for _ in range(n_kv):
            k = _string(f)
            meta[k] = _value(f, _read(f, "<I"))
        tensors = []
        for _ in range(n_tensors):
            name = _string(f)
            dims = [_read(f, "<Q") for _ in range(_read(f, "<I"))]
            ttype, _off = _read(f, "<I"), _read(f, "<Q")
            n = 1
            for d in dims:
                n *= d
            tensors.append((name, dims, GGML_TYPE.get(ttype, str(ttype)), n))
    by_type, by_group = Counter(), Counter()
    for name, dims, tt, n in tensors:
        by_type[tt] += n
        by_group["token_embedding" if name == "token_embd.weight" else "output_head" if name.startswith("output")
                 else "transformer_blocks" if name.startswith("blk.") else "other"] += n
    return {"gguf_version": version, "n_tensors": n_tensors, "total_parameters": sum(t[3] for t in tensors),
            "parameters_by_storage_type": dict(by_type), "parameters_by_group": dict(by_group),
            "metadata": {k: v for k, v in meta.items() if not k.startswith("tokenizer.chat_template")},
            "has_separate_output_head": any(t[0] == "output.weight" for t in tensors),
            "example_tensors": [{"name": a, "shape": b, "type": c} for a, b, c, _ in tensors[:6]]}


def ollama_model_blob(name="qwen3", tag="8b"):
    man = Path.home() / ".ollama/models/manifests/registry.ollama.ai/library" / name / tag
    m = json.loads(man.read_text())
    layer = next(x for x in m["layers"] if x["mediaType"].endswith("image.model"))
    blob = Path.home() / ".ollama/models/blobs" / layer["digest"].replace(":", "-")
    return blob, layer["digest"], layer["size"]


# ---------------------------------------------------------------------------------- encoders
def encoder_facts(path_or_id: str) -> dict:
    import torch
    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(str(path_or_id), device="cpu")
    tr = m[0].auto_model
    tok = m[0].tokenizer
    params = list(m.named_parameters())
    uniq = {id(p): p for _, p in params}
    groups = Counter()
    for n, p in params:
        g = ("embeddings.word" if "embeddings.word_embeddings" in n else "embeddings.position" if "position_embeddings" in n
             else "embeddings.other" if ".embeddings." in n else "encoder.layers" if ".encoder.layer." in n
             else "pooler" if ".pooler." in n else "other")
        groups[g] += p.numel()
    cfg = tr.config
    p = Path(str(path_or_id))
    disk = sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else None
    weights = next(iter(p.rglob("model.safetensors")), None) if p.exists() else None
    rev = None
    if not p.exists():
        from huggingface_hub import snapshot_download
        snap = Path(snapshot_download(path_or_id, local_files_only=True))
        rev = snap.name
        weights = next(iter(snap.rglob("model.safetensors")), None)
        disk = sum(f.stat().st_size for f in snap.rglob("*") if f.is_file())
    return {
        "source": str(path_or_id), "hf_revision": rev,
        "modules": [type(x).__name__ for x in m], "pooling": m[1].get_pooling_mode_str(),
        "normalize_module": any(type(x).__name__ == "Normalize" for x in m),
        "architecture": type(tr).__name__, "model_type": cfg.model_type,
        "total_parameters": sum(p.numel() for p in uniq.values()),
        "trainable_parameters": sum(p.numel() for p in uniq.values() if p.requires_grad),
        "frozen_parameters": sum(p.numel() for p in uniq.values() if not p.requires_grad),
        "parameters_by_group": dict(groups), "n_parameter_tensors": len(params), "shared_tensors": len(params) - len(uniq),
        "num_hidden_layers": cfg.num_hidden_layers, "num_attention_heads": cfg.num_attention_heads,
        "hidden_size": cfg.hidden_size, "intermediate_size": cfg.intermediate_size, "hidden_act": cfg.hidden_act,
        "vocab_size_config": cfg.vocab_size, "tokenizer_len": len(tok), "max_position_embeddings": cfg.max_position_embeddings,
        "position_embedding_type": getattr(cfg, "position_embedding_type", None),
        "max_seq_length_configured": m.max_seq_length, "embedding_dim": m.get_sentence_embedding_dimension(),
        "dtype": str(next(tr.parameters()).dtype),
        "weights_bytes_in_memory": sum(p.numel() * p.element_size() for p in uniq.values()),
        "weights_file_bytes": weights.stat().st_size if weights else None, "checkpoint_dir_bytes": disk,
        "tokenizer_class": type(tok).__name__, "special_tokens": tok.special_tokens_map,
        "dropout": {"hidden": cfg.hidden_dropout_prob, "attention": cfg.attention_probs_dropout_prob},
        "torch_version": torch.__version__,
    }


def shape_trace(question: str) -> dict:
    """Shapes through the fine-tuned schema linker for one question (what Pipeline.sql does)."""
    import torch
    from sentence_transformers import SentenceTransformer
    from src.schema_linking.retrieval import EmbeddingRetriever, init_elements
    m = SentenceTransformer(str(FT), device="cpu")
    els = init_elements(json.loads((ROOT / "data/schema/schema.json").read_text(encoding="utf-8")))
    r = EmbeddingRetriever(els, model=m)
    feats = m.tokenize([f"query: {question}"])
    with torch.no_grad():
        out = m[0]({k: v for k, v in feats.items()})
        pooled = m[1](out)["sentence_embedding"]
    q = m.encode([f"query: {question}"], normalize_embeddings=True)
    return {"question": question, "tokens": m[0].tokenizer.convert_ids_to_tokens(feats["input_ids"][0])[:12],
            "input_ids": list(feats["input_ids"].shape), "attention_mask": list(feats["attention_mask"].shape),
            "token_embeddings": list(out["token_embeddings"].shape), "mean_pooled": list(pooled.shape),
            "normalised_query": list(q.shape), "query_l2_norm": round(float((q ** 2).sum() ** 0.5), 6),
            "schema_matrix_E": list(r.E.shape), "scores": list((q @ r.E.T).shape),
            "n_elements": len(els), "n_columns": sum(e.kind == "column" for e in els), "n_tables": sum(e.kind == "table" for e in els)}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    res = {"encoders": {}}
    for name, src in (("base_multilingual_e5_small", BASE_ID), ("finetuned_schema_linker", FT), ("vocab_adapted_schema_linker", VA)):
        res["encoders"][name] = encoder_facts(src)
    res["shape_trace_schema_linker"] = shape_trace("2024-25 में लुधियाना जिले में कुल भूजल निकासी कितनी थी?")
    try:
        blob, digest, size = ollama_model_blob()
        res["llm_qwen3_8b"] = {"ollama_tag": "qwen3:8b", "blob_digest": digest, "file_bytes": size, **parse_gguf(blob)}
    except FileNotFoundError as e:        # model not pulled on this machine: record that, do not guess
        res["llm_qwen3_8b"] = {"ollama_tag": "qwen3:8b", "error": f"GGUF not found ({e}); run `ollama pull qwen3:8b`"}
    with open(ROOT / "experiments/entity_resolution/ranker.pkl", "rb") as f:
        lr = pickle.load(f)
    res["entity_ranker"] = {"class": type(lr).__name__, "n_features": int(lr.coef_.shape[1]),
                            "parameters": int(lr.coef_.size + lr.intercept_.size),
                            "coef": [round(float(x), 4) for x in lr.coef_[0]], "intercept": round(float(lr.intercept_[0]), 4),
                            "C": lr.C, "class_weight": lr.class_weight, "max_iter": lr.max_iter}
    (OUT / "models.json").write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    e = res["encoders"]
    for k, v in e.items():
        print(k, v["total_parameters"], v["parameters_by_group"], v["tokenizer_len"], v["weights_file_bytes"])
    g = res["llm_qwen3_8b"]
    if "error" in g:
        print(g["error"])
    else:
        print("qwen3:8b", g["total_parameters"], g["parameters_by_storage_type"], g["parameters_by_group"])
        print(json.dumps({k: v for k, v in g["metadata"].items() if not isinstance(v, dict)}, indent=1)[:2500])
    print(res["shape_trace_schema_linker"])


if __name__ == "__main__":
    main()
