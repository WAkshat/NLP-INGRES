"""Schema-linking retrievers: rank schema elements (tables, columns) for a question.

Elements come from data/schema/schema.json: "table" and "table.column" with their descriptions.
Gold = tables/columns referenced by the gold SQL; join keys (*_id) and pure name columns are excluded
from the column gold because every query touches them (they carry no linking signal).
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

import numpy as np

TRIVIAL_COLUMNS = {"state_id", "district_id", "unit_id", "state_name", "district_name", "unit_name", "assessment_year"}


@dataclass
class Element:
    key: str        # "table" or "table.column"
    kind: str       # table | column
    text: str       # text indexed by the retriever


def schema_elements(schema: dict) -> list[Element]:
    els = []
    for t in schema["tables"]:
        els.append(Element(t["name"], "table", f"{t['name'].replace('_', ' ')}: {t['description']}"))
        for c in t["columns"]:
            unit = f" ({c['unit']})" if c.get("unit") else ""
            els.append(Element(f"{t['name']}.{c['name']}", "column",
                               f"{c['name'].replace('_', ' ')}{unit}: {c['description']} [table {t['name'].replace('_', ' ')}]"))
    return els


def gold_elements(row: dict) -> tuple[set, set]:
    """(gold tables, gold content columns as 'table.column') for a benchmark row."""
    tables = set(row["tables"])
    sql = row["sql"]
    cols = set()
    for c in row["columns"]:
        if c in TRIVIAL_COLUMNS:
            continue
        # attribute the column to the referenced table(s) that own it; metric columns exist in 3 fact tables,
        # so resolve by alias: ua./a./b. -> unit_assessments, da. -> district_assessments, sa. -> state_assessments
        owners = []
        for alias, table in (("ua", "unit_assessments"), ("ua2", "unit_assessments"), ("a", None), ("b", None),
                             ("da", "district_assessments"), ("sa", "state_assessments"), ("g", "state_unit_granularity"),
                             ("u", "assessment_units")):
            if re.search(rf"\b{alias}\.{c}\b", sql):
                if table is None:  # a./b. are unit_, district_ or state_assessments depending on the FROM clause
                    m = re.search(rf"FROM (\w+) {alias}\b|JOIN (\w+) {alias}\b", sql)
                    table = (m.group(1) or m.group(2)) if m else None
                if table:
                    owners.append(table)
        cols |= {f"{t}.{c}" for t in (owners or [t for t in tables])} & ELEMENT_KEYS
    return tables, cols


ELEMENT_KEYS: set = set()  # filled by init_elements()


def init_elements(schema: dict) -> list[Element]:
    els = schema_elements(schema)
    ELEMENT_KEYS.clear()
    ELEMENT_KEYS.update(e.key for e in els)
    return els


def _tok(s: str) -> list[str]:
    return re.findall(r"[^\W_]+", s.lower())


class BM25Retriever:
    name = "B_bm25"

    def __init__(self, elements: list[Element], k1: float = 1.2, b: float = 0.75):
        self.els, self.k1, self.b = elements, k1, b
        self.docs = [_tok(e.text) for e in elements]
        self.avgdl = sum(map(len, self.docs)) / len(self.docs)
        df = Counter(t for d in self.docs for t in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in self.docs]

    def scores(self, query: str) -> np.ndarray:
        q = _tok(query)
        out = np.zeros(len(self.els))
        for i, (tf, d) in enumerate(zip(self.tf, self.docs)):
            s = 0.0
            for t in q:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(d) / self.avgdl))
            out[i] = s
        return out


class EmbeddingRetriever:
    name = "C_multilingual_e5_small"
    model_id = "intfloat/multilingual-e5-small"

    def __init__(self, elements: list[Element], model=None):
        from sentence_transformers import SentenceTransformer
        self.els = elements
        self.model = model or SentenceTransformer(self.model_id, device="cpu")
        self.E = self.model.encode([f"passage: {e.text}" for e in elements], normalize_embeddings=True, batch_size=64)

    def scores_batch(self, queries: list[str]) -> np.ndarray:
        Q = self.model.encode([f"query: {q}" for q in queries], normalize_embeddings=True, batch_size=64)
        return Q @ self.E.T


def rank_metrics(scores: np.ndarray, elements: list[Element], gold: set, kind: str, ks=(1, 3, 5)) -> dict:
    """Recall@k (share of gold elements of this kind in the top-k of that kind), MRR over gold elements."""
    idx = [i for i, e in enumerate(elements) if e.kind == kind]
    order = [elements[i].key for i in sorted(idx, key=lambda i: -scores[i])]
    if not gold:
        return {}
    ranks = [order.index(g) + 1 for g in gold if g in order]
    out = {f"R@{k}": sum(r <= k for r in ranks) / len(gold) for k in ks}
    out["MRR"] = sum(1 / r for r in ranks) / len(gold)
    return out
