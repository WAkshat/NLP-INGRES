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
import time
from collections import Counter
from pathlib import Path

import numpy as np

from src.baselines.llm import SYSTEM, LLMBaseline, extract_sql
from src.entity_resolution.gazetteer import build_gazetteer
from src.entity_resolution.resolver import Resolver
from src.grounding.verifier import grounded_answer
from src.pipeline import years
from src.pipeline.values import ValueSnapper
from src.schema_linking.retrieval import EmbeddingRetriever, init_elements
from src.tokenization.metrics import PUNCT, words
from src.utils.safe_sql import UnsafeSQL, execute

ROOT = Path(__file__).resolve().parents[2]
FT_CKPT = ROOT / "experiments/schema_linking/checkpoints/finetuned_e5"
RANKER = ROOT / "experiments/entity_resolution/ranker.pkl"
# Definitions added after the dev-set error analysis (docs/PIPELINE.md): 9 of 38 dev errors used stage_of_extraction_pct
# for "what share of extraction was for irrigation", and 5 listed extra columns. Kept out of CONVENTIONS so earlier
# experiments keep their exact prompts.
DOMAIN_NOTES = ("Definitions: stage_of_extraction_pct = extraction_total_ham / extractable_resource_ham x 100 (use of the "
                "available resource); it is NOT a share of total extraction. \"What percent/share of extraction was for "
                "irrigation\" = 100.0 * extraction_irrigation_ham / extraction_total_ham (likewise extraction_domestic_ham, "
                "extraction_industrial_ham). When the question asks which units/districts/states, select only their names "
                "unless it also asks for values.")
ALIAS_CACHE = ROOT / "cache/alias_emb"       # alias embeddings of the base encoder (git-ignored, rebuilt if missing)


class PlaceLinker:
    """Detect place mentions by scanning 1-3 word spans and keeping confident, non-overlapping resolver matches.
    Spans made only of frequent, place-unspecific TRAIN-question words (function / domain words) are skipped."""

    def __init__(self, con, embedder, train_rows: list[dict], tau: float = 0.9, min_freq: int = 5):
        self.res = Resolver(build_gazetteer(con), embedder=embedder, emb_cache=ALIAS_CACHE)
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
        texts = [" ".join(ws[i:i + n]).strip(PUNCT) for i, n in spans]
        embs = self.res.embed(texts) if texts else []          # one batched forward pass for all spans
        found = []
        for (i, n), text, emb in zip(spans, texts, embs):
            out = self.res.resolve(text, k=1, m_emb=emb)
            if out and out[0][1] >= self.tau:
                found.append((out[0][1], n, i, out[0][0]))
        used, picked = set(), []
        for s, n, i, e in sorted(found, key=lambda x: (-x[0], -x[1])):   # greedy, non-overlapping, best first
            if used.isdisjoint(range(i, i + n)):
                used |= set(range(i, i + n))
                picked.append({"mention": " ".join(ws[i:i + n]), "level": e.level, "db_name": e.db_name,
                               "district": e.district, "state": e.state, "score": round(s, 3)})
        # second pass: re-resolve districts / units with the detected states as hierarchy context. The new match must clear
        # the same threshold (baseline-v1 kept it whatever its score, e.g. "शीर्ष" -> SIRSA at 0.0); a place outside the
        # stated states that has no confident match inside them is dropped.
        states = {p["db_name"] for p in picked if p["level"] == "state"}
        if states:
            kept = []
            for p in picked:
                if p["level"] != "state":
                    e, s = self.res.resolve(p["mention"], {"states": states, "districts": set()}, k=1)[0]
                    if s >= self.tau:
                        p.update(level=e.level, db_name=e.db_name, district=e.district, state=e.state, score=round(s, 3))
                    elif p["state"] not in states:
                        continue
                kept.append(p)
            picked = kept
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
                 encoder=None, place_linker: PlaceLinker | None = None, year_hints: bool = True,
                 snap_values: bool = True, domain_notes: bool = True):
        from sentence_transformers import SentenceTransformer
        self.con, self.train = con, train_rows
        self.cfg = {"model": model, "schema_hints": schema_hints, "places": places, "fewshot": fewshot,
                    "max_repairs": max_repairs, "k_cols": k_cols, "k_shots": k_shots, "year_hints": year_hints,
                    "snap_values": snap_values, "domain_notes": domain_notes}
        self.snapper = ValueSnapper(con) if snap_values else None
        self.intents = np.array([r.get("intent", "") for r in train_rows])
        self.llm = LLMBaseline(con, train_rows, model=model, backend="ollama")
        self.enc = encoder or SentenceTransformer(str(FT_CKPT), device="cpu")
        self.els = init_elements(json.loads((ROOT / "data/schema/schema.json").read_text(encoding="utf-8")))
        self.cols = [i for i, e in enumerate(self.els) if e.kind == "column"]
        self.linker = EmbeddingRetriever(self.els, model=self.enc) if schema_hints else None
        self.TQ = self.enc.encode([f"query: {r['question']}" for r in train_rows], normalize_embeddings=True,
                                  batch_size=64) if fewshot else None
        self.places = (place_linker or PlaceLinker(con, SentenceTransformer(EmbeddingRetriever.model_id, device="cpu"),
                                                   train_rows)) if places else None

    def _examples(self, q_emb, exclude_intent: str | None = None) -> str:
        sims = self.TQ @ q_emb
        if exclude_intent:                    # evaluation only: hide TRAIN examples of the question's own type
            sims = np.where(self.intents == exclude_intent, -np.inf, sims)
        idx = np.argsort(-sims)[: self.cfg["k_shots"]]
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

    def sql(self, question: str, exclude_intent: str | None = None) -> dict:
        t = {}
        t0 = time.perf_counter()
        q_emb = self.enc.encode([f"query: {question}"], normalize_embeddings=True)[0]
        t["encode_ms"] = time.perf_counter() - t0
        hints = None
        if self.linker is not None:
            sc = q_emb @ self.linker.E.T
            hints = [self.els[i].key for i in sorted(self.cols, key=lambda i: -sc[i])[: self.cfg["k_cols"]]]
        t0 = time.perf_counter()
        places = self.places.link(question) if self.places else []
        t["place_link_ms"] = time.perf_counter() - t0
        examples = self._examples(q_emb, exclude_intent) if self.TQ is not None else ""
        yrs = years.year_labels(question) if self.cfg.get("year_hints") else []
        notes = DOMAIN_NOTES if self.cfg.get("domain_notes") else ""
        extra = "\n".join(x for x in (PlaceLinker.render(places), years.render(yrs), notes) if x)
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": self.llm.prompt(question, hints, examples, extra)}]
        attempts, lat, ptok, otok = [], 0.0, 0, 0
        t_exec = 0.0
        for turn in range(self.cfg["max_repairs"] + 1):
            out = self.llm.client.generate(messages=msgs)
            lat, ptok, otok = lat + out["latency_s"], ptok + out["prompt_tokens"], otok + out["output_tokens"]
            s = extract_sql(out["text"])
            raw, snapped = s, []
            if self.snapper is not None:
                s, snapped = self.snapper.snap(s, places)
            t0 = time.perf_counter()
            res, problem = self._run(s)
            t_exec += time.perf_counter() - t0
            attempts.append({"sql": s, "problem": problem, **({"llm_sql": raw, "snapped": snapped} if snapped else {})})
            if problem is None or turn == self.cfg["max_repairs"]:
                break
            msgs += [{"role": "assistant", "content": out["text"]},
                     {"role": "user", "content": f"Executing that query gave: {problem}. Check table/column names, "
                      "the place-name spellings and the year labels, then return the corrected SQL only. If no rows "
                      "is really the right answer, return the same query."}]
            if attempts[-1]["sql"] and len(attempts) >= 2 and attempts[-1]["sql"] == attempts[-2]["sql"]:
                break                                   # model insists: stop
        t["llm_ms"], t["sql_exec_ms"] = lat, t_exec
        return {"sql": attempts[-1]["sql"], "first_sql": attempts[0]["sql"], "attempts": attempts, "hints": hints,
                "places": places, "years": yrs, "latency_s": round(lat, 3), "prompt_tokens": ptok, "output_tokens": otok,
                "timings_ms": {k: round(1000 * v, 1) for k, v in t.items()}, "result": res}

    def answer(self, question: str) -> dict:
        out = self.sql(question)
        r = out.pop("result")
        if r is None or r.error:
            return {**out, "answer": "Could not produce a valid query for this question.", "columns": [], "rows": []}
        t0 = time.perf_counter()
        ans = grounded_answer(self.llm.client, question, r.columns, r.rows)
        out["timings_ms"]["answer_ms"] = round(1000 * (time.perf_counter() - t0), 1)
        return {**out, **ans, "columns": r.columns, "rows": r.rows}
