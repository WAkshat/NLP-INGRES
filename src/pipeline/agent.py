"""Full multilingual Text-to-SQL pipeline (Phase 9).

question --> [schema linker: top-k columns]          (Phase 5, fine-tuned multilingual-e5-small)
         --> [place-name linker: n-gram spans -> resolver -> exact DB spellings]   (Phase 6)
         --> [retrieved few-shot: k most similar TRAIN questions + their SQL]
         --> LLM (qwen3:8b) --> SQL --> read-only execution
         --> repair loop: on an error or an empty result, the error is fed back (max_repairs turns)
         --> answer + numeric-grounding check (Phase 8)
Each component can be switched off for ablations.
"""
from __future__ import annotations

import json
import pickle
from collections import Counter
from pathlib import Path

import numpy as np

from src.baselines.llm import SYSTEM, LLMBaseline, extract_sql
from src.entity_resolution.gazetteer import build_gazetteer
from src.entity_resolution.resolver import Resolver
from src.grounding.verifier import grounded_answer
from src.schema_linking.retrieval import EmbeddingRetriever, init_elements
from src.tokenization.metrics import PUNCT, words
from src.utils.safe_sql import UnsafeSQL, execute

ROOT = Path(__file__).resolve().parents[2]
FT_CKPT = ROOT / "experiments/schema_linking/checkpoints/finetuned_e5"
RANKER = ROOT / "experiments/entity_resolution/ranker.pkl"


class PlaceLinker:
    """Detect place mentions by scanning 1-3 word spans and keeping confident, non-overlapping resolver matches.
    Spans made only of frequent, place-unspecific TRAIN-question words (function / domain words) are skipped."""

    def __init__(self, con, embedder, train_rows: list[dict], tau: float = 0.9, min_freq: int = 5):
        self.res = Resolver(build_gazetteer(con), embedder=embedder)
        with open(RANKER, "rb") as f:
            self.res.ranker = pickle.load(f)
        # stopword = frequent in TRAIN questions AND not tied to one place (place names co-occur with their gold entity)
        cnt, co = Counter(), {}
        for r in train_rows:
            ents = {e["db_name"] for e in r["entities"]}
            for w in {w.lower() for w in words(r["question"])}:
                cnt[w] += 1
                co.setdefault(w, Counter()).update(ents)
        self.stop = {w for w, c in cnt.items() if c >= min_freq and max(co[w].values(), default=0) / c < 0.8}
        self.tau = tau

    def link(self, question: str) -> list[dict]:
        ws = [w for w in words(question) if not any(ch.isdigit() for ch in w)]
        spans = [(i, n) for n in (3, 2, 1) for i in range(len(ws) - n + 1)
                 if not all(w.lower() in self.stop for w in ws[i:i + n])]
        found = []
        for i, n in spans:
            out = self.res.resolve(" ".join(ws[i:i + n]).strip(PUNCT), k=1)
            if out and out[0][1] >= self.tau:
                found.append((out[0][1], n, i, out[0][0]))
        used, picked = set(), []
        for s, n, i, e in sorted(found, key=lambda x: (-x[0], -x[1])):   # greedy, non-overlapping, best first
            if used.isdisjoint(range(i, i + n)):
                used |= set(range(i, i + n))
                picked.append({"mention": " ".join(ws[i:i + n]), "level": e.level, "db_name": e.db_name,
                               "district": e.district, "state": e.state, "score": round(s, 3)})
        # second pass: re-resolve districts / units with the detected states as hierarchy context
        states = {p["db_name"] for p in picked if p["level"] == "state"}
        if states:
            for p in picked:
                if p["level"] != "state":
                    e, s = self.res.resolve(p["mention"], {"states": states, "districts": set()}, k=1)[0]
                    p.update(level=e.level, db_name=e.db_name, district=e.district, state=e.state, score=round(s, 3))
        return picked

    @staticmethod
    def render(places: list[dict]) -> str:
        if not places:
            return ""
        parts = []
        for p in places:
            where = {"state": "", "district": f" in state '{p['state']}'",
                     "unit": f" in district '{p['district']}', state '{p['state']}'"}[p["level"]]
            parts.append(f"{p['level']} '{p['db_name']}'{where} (written \"{p['mention']}\")")
        return "Places in the question, with their exact database spellings (resolver, may be wrong): " + "; ".join(parts)


class Pipeline:
    def __init__(self, con, train_rows: list[dict], model: str = "qwen3:8b", schema_hints: bool = True,
                 places: bool = True, fewshot: bool = True, max_repairs: int = 2, k_cols: int = 5, k_shots: int = 3,
                 encoder=None, place_linker: PlaceLinker | None = None):
        from sentence_transformers import SentenceTransformer
        self.con, self.train = con, train_rows
        self.cfg = {"model": model, "schema_hints": schema_hints, "places": places, "fewshot": fewshot,
                    "max_repairs": max_repairs, "k_cols": k_cols, "k_shots": k_shots}
        self.llm = LLMBaseline(con, train_rows, model=model, backend="ollama")
        self.enc = encoder or SentenceTransformer(str(FT_CKPT), device="cpu")
        self.els = init_elements(json.loads((ROOT / "data/schema/schema.json").read_text(encoding="utf-8")))
        self.cols = [i for i, e in enumerate(self.els) if e.kind == "column"]
        self.linker = EmbeddingRetriever(self.els, model=self.enc) if schema_hints else None
        self.TQ = self.enc.encode([f"query: {r['question']}" for r in train_rows], normalize_embeddings=True,
                                  batch_size=64) if fewshot else None
        self.places = (place_linker or PlaceLinker(con, SentenceTransformer(EmbeddingRetriever.model_id, device="cpu"),
                                                   train_rows)) if places else None

    def _examples(self, q_emb) -> str:
        idx = np.argsort(-(self.TQ @ q_emb))[: self.cfg["k_shots"]]
        return "\n\n".join(f"Question: {self.train[i]['question']}\nSQL:\n```sql\n{self.train[i]['sql']}\n```" for i in idx[::-1])

    def _run(self, sql):
        if not sql:
            return None, "the reply contained no SQL query"
        try:
            r = execute(self.con, sql)
        except UnsafeSQL as e:
            return None, f"refused (only read-only SELECT is allowed): {e}"
        if r.error:
            return r, r.error
        if not r.rows or all(v is None for v in r.rows[0]) and len(r.rows) == 1:
            return r, "the query returned no rows (or only NULL)"
        return r, None

    def sql(self, question: str) -> dict:
        q_emb = self.enc.encode([f"query: {question}"], normalize_embeddings=True)[0]
        hints = None
        if self.linker is not None:
            sc = q_emb @ self.linker.E.T
            hints = [self.els[i].key for i in sorted(self.cols, key=lambda i: -sc[i])[: self.cfg["k_cols"]]]
        places = self.places.link(question) if self.places else []
        examples = self._examples(q_emb) if self.TQ is not None else ""
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": self.llm.prompt(question, hints, examples, PlaceLinker.render(places))}]
        attempts, lat, ptok, otok = [], 0.0, 0, 0
        for turn in range(self.cfg["max_repairs"] + 1):
            out = self.llm.client.generate(messages=msgs)
            lat, ptok, otok = lat + out["latency_s"], ptok + out["prompt_tokens"], otok + out["output_tokens"]
            s = extract_sql(out["text"])
            res, problem = self._run(s)
            attempts.append({"sql": s, "problem": problem})
            if problem is None or turn == self.cfg["max_repairs"]:
                break
            msgs += [{"role": "assistant", "content": out["text"]},
                     {"role": "user", "content": f"Executing that query gave: {problem}. Check table/column names, "
                      "the place-name spellings and the year labels, then return the corrected SQL only. If no rows "
                      "is really the right answer, return the same query."}]
            if attempts[-1]["sql"] and len(attempts) >= 2 and attempts[-1]["sql"] == attempts[-2]["sql"]:
                break                                   # model insists: stop
        return {"sql": attempts[-1]["sql"], "first_sql": attempts[0]["sql"], "attempts": attempts, "hints": hints,
                "places": places, "latency_s": round(lat, 3), "prompt_tokens": ptok, "output_tokens": otok,
                "result": res}

    def answer(self, question: str) -> dict:
        out = self.sql(question)
        r = out.pop("result")
        if r is None or r.error:
            return {**out, "answer": "Could not produce a valid query for this question.", "columns": [], "rows": []}
        return {**out, **grounded_answer(self.llm.client, question, r.columns, r.rows), "columns": r.columns, "rows": r.rows}
