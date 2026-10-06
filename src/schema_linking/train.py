"""Learned schema linking: contrastive fine-tuning of a multilingual bi-encoder (question -> schema column).

Objective: InfoNCE / multiple-negatives ranking. For a batch of (question, positive column) pairs, every other
positive in the batch is a negative, plus k explicit HARD negatives per question drawn from semantically adjacent
columns (see HARD_GROUPS) and the same column at a different administrative level (unit vs district vs state).
Only TRAIN-split questions are used. Plain PyTorch loop (no datasets/accelerate dependency).
"""
from __future__ import annotations

import random
import time

import torch
import torch.nn.functional as F

from src.schema_linking.retrieval import Element, gold_elements

FACT_TABLES = ("unit_assessments", "district_assessments", "state_assessments")
# columns that users (and models) confuse with each other
HARD_GROUPS = [
    {"annual_recharge_ham", "recharge_rainfall_ham", "extractable_resource_ham", "natural_discharge_ham",
     "future_availability_ham", "recharge_poor_quality_ham", "domestic_allocation_ham"},
    {"extraction_total_ham", "extraction_irrigation_ham", "extraction_domestic_ham", "extraction_industrial_ham",
     "stage_of_extraction_pct", "extraction_poor_quality_ham"},
    {"stage_of_extraction_pct", "category"},
    {"rainfall_mm", "recharge_rainfall_ham"},
    {"unit_type", "category"},
]


def hard_negatives(pos_key: str, element_keys: list[str], gold: set, k: int, rng: random.Random) -> list[str]:
    table, col = pos_key.split(".")
    cand = set()
    for g in HARD_GROUPS:                                  # semantically adjacent columns, same table
        if col in g:
            cand |= {f"{table}.{c}" for c in g if c != col}
    if table in FACT_TABLES:                               # same column, different administrative level
        cand |= {f"{t}.{col}" for t in FACT_TABLES if t != table}
    if col == "unit_type":
        cand |= {"assessment_units.unit_type", "state_unit_granularity.unit_type"} - {pos_key}
    cand = [c for c in cand if c in element_keys and c not in gold]
    rng.shuffle(cand)
    out = cand[:k]
    while len(out) < k:                                    # pad with random columns (never all-random)
        c = rng.choice(element_keys)
        if c not in gold and c not in out:
            out.append(c)
    return out


def build_pairs(rows: list[dict], elements: list[Element], k_hard: int = 3, seed: int = 0):
    rng = random.Random(seed)
    text = {e.key: e.text for e in elements}
    cols = [e.key for e in elements if e.kind == "column"]
    pairs = []
    for r in rows:
        _, gold = gold_elements(r)
        for g in sorted(gold):
            pairs.append((r["question"], text[g], [text[n] for n in hard_negatives(g, cols, gold, k_hard, rng)]))
    return pairs


def _encode(model, texts: list[str]):
    feats = model.tokenize(texts)
    feats = {k: v.to(model.device) for k, v in feats.items()}
    return F.normalize(model(feats)["sentence_embedding"], dim=-1)


def train(model, pairs, epochs: int = 3, batch_size: int = 16, lr: float = 2e-5, scale: float = 20.0, seed: int = 0,
          log=print) -> dict:
    torch.manual_seed(seed)
    rng = random.Random(seed)
    opt = torch.optim.AdamW(model.parameters(), lr=lr)
    steps = epochs * ((len(pairs) + batch_size - 1) // batch_size)
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / max(1, steps // 10)))  # warmup
    model.train()
    hist, t0, step = [], time.time(), 0
    for ep in range(epochs):
        order = list(range(len(pairs)))
        rng.shuffle(order)
        for i in range(0, len(order), batch_size):
            batch = [pairs[j] for j in order[i:i + batch_size]]
            q = _encode(model, [f"query: {b[0]}" for b in batch])
            docs = [f"passage: {b[1]}" for b in batch] + [f"passage: {n}" for b in batch for n in b[2]]
            d = _encode(model, docs)
            logits = scale * q @ d.T
            loss = F.cross_entropy(logits, torch.arange(len(batch), device=logits.device))
            opt.zero_grad()
            loss.backward()
            opt.step()
            sched.step()
            step += 1
            hist.append(loss.item())
        log(f"  epoch {ep + 1}/{epochs}: mean loss {sum(hist[-((len(order) + batch_size - 1) // batch_size):]) / ((len(order) + batch_size - 1) // batch_size):.4f}")
    model.eval()
    return {"steps": step, "final_loss": round(sum(hist[-10:]) / min(10, len(hist)), 4), "train_time_s": round(time.time() - t0, 1)}
