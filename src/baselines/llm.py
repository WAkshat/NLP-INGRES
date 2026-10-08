"""Baseline D: frontier LLM (Gemini, free tier) with the schema + documentation in the prompt.

Quota safety (free tier; limits are per project and not published per model):
  - every response is cached on disk (cache/llm/), keyed by model + prompt + config -> reruns cost no quota
  - requests are paced (min_interval_s) well below typical free-tier RPM
  - 503/500 (overloaded) -> exponential backoff; 429 -> the QuotaFailure details Google returns are logged
    to experiments/baselines/gemini_quota_log.jsonl, then we wait for RetryInfo; a per-DAY quota violation
    raises QuotaExhausted so the run stops cleanly and can resume the next day from the cache
The API key is read from the GEMINI_API_KEY environment variable or .env (git-ignored), never logged.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "cache/llm"
QUOTA_LOG = ROOT / "experiments/baselines/gemini_quota_log.jsonl"
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class QuotaExhausted(RuntimeError):
    pass


def api_key() -> str:
    key = os.environ.get("GEMINI_API_KEY")
    if not key and (ROOT / ".env").exists():
        for line in (ROOT / ".env").read_text().splitlines():
            if line.startswith("GEMINI_API_KEY="):
                key = line.split("=", 1)[1].strip()
    if not key:
        raise SystemExit("GEMINI_API_KEY not set (see .env.example)")
    return key


class GeminiClient:
    def __init__(self, model: str, min_interval_s: float = 7.0, max_retries: int = 8, temperature: float = 0.0,
                 max_backoff_s: float = 120):
        self.model, self.min_interval_s, self.max_retries, self.temperature = model, min_interval_s, max_retries, temperature
        self.max_backoff_s = max_backoff_s
        self._last = 0.0
        self.usage = {"api_calls": 0, "cache_hits": 0, "prompt_tokens": 0, "output_tokens": 0, "retries": 0}
        CACHE.mkdir(parents=True, exist_ok=True)

    def generate(self, prompt: str, system: str = "") -> dict:
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": self.temperature}}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        key = hashlib.sha256(json.dumps([self.model, body], sort_keys=True).encode()).hexdigest()
        path = CACHE / f"{key}.json"
        if path.exists():
            self.usage["cache_hits"] += 1
            return json.loads(path.read_text(encoding="utf-8"))
        for attempt in range(self.max_retries):
            wait = self.min_interval_s - (time.time() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.time()
            req = urllib.request.Request(API.format(model=self.model), json.dumps(body).encode(),
                                         {"Content-Type": "application/json", "x-goog-api-key": api_key()})
            t0 = time.perf_counter()
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    data = json.load(r)
            except urllib.error.HTTPError as e:
                err = e.read().decode("utf-8", "replace")
                self.usage["retries"] += 1
                if e.code == 429:
                    self._handle_429(err)
                    continue
                if e.code in (500, 502, 503, 504):
                    self.usage["overloaded_503"] = self.usage.get("overloaded_503", 0) + 1
                    time.sleep(min(self.max_backoff_s, 10 * 2 ** attempt))
                    continue
                raise RuntimeError(f"Gemini HTTP {e.code}: {err[:300]}") from e
            except (urllib.error.URLError, TimeoutError) as e:
                self.usage["retries"] += 1
                time.sleep(min(self.max_backoff_s, 10 * 2 ** attempt))
                continue
            text = "".join(p.get("text", "") for c in data.get("candidates", [])[:1]
                           for p in c.get("content", {}).get("parts", []))
            um = data.get("usageMetadata", {})
            out = {"text": text, "latency_s": round(time.perf_counter() - t0, 3), "model_version": data.get("modelVersion"),
                   "prompt_tokens": um.get("promptTokenCount", 0), "output_tokens": um.get("candidatesTokenCount", 0)
                   + um.get("thoughtsTokenCount", 0), "finish_reason": (data.get("candidates") or [{}])[0].get("finishReason")}
            self.usage["api_calls"] += 1
            self.usage["prompt_tokens"] += out["prompt_tokens"]
            self.usage["output_tokens"] += out["output_tokens"]
            path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
            return out
        raise RuntimeError(f"Gemini: gave up after {self.max_retries} attempts")

    def _handle_429(self, err: str):
        try:
            details = json.loads(err)["error"].get("details", [])
        except (ValueError, KeyError):
            details = []
        violations = [v for d in details for v in d.get("violations", [])]
        retry = next((d.get("retryDelay") for d in details if "retryDelay" in d), "60s")
        QUOTA_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(QUOTA_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps({"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "model": self.model,
                                "violations": violations, "retryDelay": retry}) + "\n")
        if any("PerDay" in (v.get("quotaId", "") + v.get("quotaMetric", "")) for v in violations):
            raise QuotaExhausted(f"daily quota exhausted for {self.model}: {violations}")
        secs = float(re.sub(r"[^\d.]", "", retry) or 60)
        time.sleep(secs + 2)


class OllamaClient:
    """Local open model served by Ollama (http://127.0.0.1:11434). Same interface and disk cache as GeminiClient.

    generate(prompt, system) or generate(messages=[...]) for multi-turn (agent). Deterministic: temperature 0,
    fixed seed. Ollama reuses the KV cache of an identical prompt prefix, so the long schema prefix is cheap.
    """

    URL = "http://127.0.0.1:11434/api/chat"

    def __init__(self, model: str = "qwen2.5-coder:7b", num_ctx: int = 8192, temperature: float = 0.0, seed: int = 0,
                 max_tokens: int = 512, think: bool = False):
        self.model, self.think = model, think
        self.options = {"temperature": temperature, "seed": seed, "num_ctx": num_ctx, "num_predict": max_tokens}
        self.usage = {"api_calls": 0, "cache_hits": 0, "prompt_tokens": 0, "output_tokens": 0, "truncated_prompts": 0}
        CACHE.mkdir(parents=True, exist_ok=True)

    def generate(self, prompt: str = "", system: str = "", messages: list | None = None) -> dict:
        msgs = list(messages or [])
        if not msgs:
            msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
        body = {"model": self.model, "messages": msgs, "stream": False, "options": self.options}
        if self.model.startswith("qwen3"):
            body["think"] = self.think   # Qwen3 reasons by default; off unless asked
        key = hashlib.sha256(json.dumps(["ollama", body], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        path = CACHE / f"{key}.json"
        if path.exists():
            self.usage["cache_hits"] += 1
            return json.loads(path.read_text(encoding="utf-8"))
        t0 = time.perf_counter()
        for attempt in range(5):
            try:
                req = urllib.request.Request(self.URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=900) as r:
                    d = json.load(r)
                break
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                time.sleep(5 * (attempt + 1))
        else:
            raise RuntimeError("Ollama server not reachable (is the Ollama app running?)")
        pt, ot = d.get("prompt_eval_count", 0), d.get("eval_count", 0)
        if pt >= self.options["num_ctx"] - 8:
            self.usage["truncated_prompts"] += 1      # prompt hit the context limit: results would be invalid
        out = {"text": re.sub(r"<think>.*?</think>", "", d["message"]["content"], flags=re.S), "latency_s": round(time.perf_counter() - t0, 3), "model_version": self.model,
               "prompt_tokens": pt, "output_tokens": ot, "finish_reason": d.get("done_reason")}
        self.usage["api_calls"] += 1
        self.usage["prompt_tokens"] += pt
        self.usage["output_tokens"] += ot
        path.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        return out


def make_client(backend: str, model: str | None = None, patient: bool = False):
    if backend == "ollama":
        return OllamaClient(model or "qwen2.5-coder:7b")
    return GeminiClient(model or "gemini-3.6-flash", **({"max_retries": 40, "max_backoff_s": 300} if patient else {}))


# ------------------------------------------------------------------ prompt
def compact_schema_prompt(schema: dict, con=None) -> str:
    """Short schema rendering for small-context models: one line per table, shared metric columns described once,
    and the exact INGRES state spellings (users write 'Tamil Nadu'; the DB stores 'TAMILNADU')."""
    tables = {t["name"]: t for t in schema["tables"] if t["name"] != "location_crosswalk"}
    metric_cols = [c for c in tables["state_assessments"]["columns"] if c["name"] not in ("state_id", "assessment_year")]
    metric_names = {c["name"] for c in metric_cols}
    lines = ["TABLES:"]
    for name, t in tables.items():
        cols = []
        for c in t["columns"]:
            if name.endswith("_assessments") and c["name"] in metric_names:
                continue
            fk = next((f["references"] for f in t["foreign_keys"] if f["column"] == c["name"]), None)
            cols.append(c["name"] + (f" -> {fk}" if fk else ""))
        extra = ", <METRICS>" if name.endswith("_assessments") else ""
        lines.append(f"  {name}({', '.join(cols)}{extra})")
    lines.append("<METRICS> = the same columns in unit_assessments, district_assessments and state_assessments:")
    for c in metric_cols:
        unit = f" [{c['unit']}]" if c.get("unit") else ""
        desc = re.sub(r"\s*\([^)]*UNCERTAIN[^)]*\)", "", c["description"]).split(";")[0]
        lines.append(f"  {c['name']}{unit}: {desc}")
    lines.append("unit_assessments.category: 'Safe' | 'Semi-Critical' | 'Critical' | 'Over-Exploited' | 'Saline' | 'Hilly Area'")
    lines.append("assessment_units.unit_type: BLOCK | TALUK | TEHSIL | MANDAL | FIRKA | VALLEY | ISLAND | REGION | DISTRICT")
    if con is not None:
        from src.utils.safe_sql import execute
        states = [r[0] for r in execute(con, "SELECT state_name FROM states ORDER BY 1").rows]
        lines.append("states.state_name values: " + ", ".join(repr(s) for s in states))
    return "\n".join(lines)


def schema_prompt(schema: dict) -> str:
    lines = []
    for t in schema["tables"]:
        if t["name"] == "location_crosswalk":
            continue  # bookkeeping table, not needed to answer questions
        lines.append(f"TABLE {t['name']} -- {t['description']}")
        for c in t["columns"]:
            ex = ", ".join(repr(e) for e in c["examples"][:3])
            unit = f" [{c['unit']}]" if c.get("unit") else ""
            lines.append(f"  {c['name']} {c['type']}{unit} -- {c['description']}" + (f" e.g. {ex}" if ex else ""))
        if t["foreign_keys"]:
            lines.append("  FOREIGN KEYS: " + "; ".join(f"{f['column']} -> {f['references']}" for f in t["foreign_keys"]))
    return "\n".join(lines)


CONVENTIONS = """Conventions of this database (INGRES groundwater assessments, SQLite):
- assessment_year labels look like '2024-2025'. "2024-25" means '2024-2025'. "the N assessment" (e.g. "the 2025
  assessment", "2025 ke assessment", "2025 के आकलन", "2025 மதிப்பீட்டில்") means the published GWRA N report,
  i.e. assessment_year '(N-1)-N' (the 2025 assessment is '2024-2025'). Available: 2019-2020, 2021-2022, 2022-2023,
  2023-2024, 2024-2025.
- category values: 'Safe', 'Semi-Critical', 'Critical', 'Over-Exploited', 'Saline', 'Hilly Area'.
- Names are stored exactly as in INGRES: states in UPPER CASE with INGRES spellings (e.g. 'TAMILNADU',
  'LAKSHDWEEP', 'JAMMU AND KASHMIR'); district and unit names keep INGRES casing, which varies by state
  (e.g. 'LUDHIANA' or 'Ludhiana'). Questions may use other spellings, transliterations or scripts.
- Volumes are in hectare-metres (ham); 1 BCM = 100000 ham; stage_of_extraction_pct is a percentage.
- Unit-level facts are in unit_assessments (join assessment_units -> districts -> states); district- and
  state-level official aggregates are in district_assessments / state_assessments.
- Join different years of the same unit on unit_id (ids are stable across years).
RULES (always follow):
- Write assessment_year values in full: '2019-2020', '2021-2022', '2022-2023', '2023-2024', '2024-2025' (never '2024-25').
- Column locations: unit_name/unit_type are only in assessment_units; district_name only in districts; state_name only in
  states; category and metrics of units only in unit_assessments.
- Unit questions join: unit_assessments ua JOIN assessment_units u ON u.unit_id = ua.unit_id
  JOIN districts d ON d.district_id = u.district_id JOIN states s ON s.state_id = u.state_id.
- Match place names case-insensitively when unsure of INGRES casing, e.g. UPPER(d.district_name) = UPPER('Ludhiana').
- Select only what the question asks for (no extra columns)."""

SYSTEM = ("You translate questions (in English, Hindi, Hinglish or Tamil) into a single SQLite SELECT query over the "
          "given schema. Return only the SQL in a ```sql code block. Return exactly the columns the question asks "
          "for, in the order asked; include values when the question asks to show them.")


def extract_sql(text: str) -> str | None:
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    sql = (m.group(1) if m else text).strip().rstrip(";").strip()
    return sql or None


class LLMBaseline:
    """Single-shot Text-to-SQL with schema + conventions in the prompt (backend: gemini | ollama)."""

    def __init__(self, con, train_rows: list, model: str | None = None, few_shot: int = 0, patient: bool = False,
                 backend: str = "gemini"):
        schema = json.loads((ROOT / "data/schema/schema.json").read_text(encoding="utf-8"))
        self.client = make_client(backend, model, patient)
        self.model = self.client.model
        self.few_shot = few_shot
        # the full schema dump (~9k tokens) overflows small local context windows -> compact rendering for ollama
        self.schema_text = compact_schema_prompt(schema, con) if backend == "ollama" else schema_prompt(schema)
        self.examples = ""
        if few_shot:  # fixed, diverse English examples from TRAIN (one per difficulty), not retrieved per question
            import random
            rng, picked = random.Random(0), []
            for d in ("simple_lookup", "filtered_aggregate", "cross_year", "multi_hop"):
                cand = [r for r in train_rows if r["difficulty"] == d and r["language"] == "english"]
                picked.append(rng.choice(cand))
            self.examples = "\n\n".join(f"Question: {r['question']}\nSQL:\n```sql\n{r['sql']}\n```" for r in picked[:few_shot])
        safe = re.sub(r"[^A-Za-z0-9]+", "_", self.model).strip("_")
        self.name = f"D_{safe}" + (f"_fewshot{few_shot}" if few_shot else "_zeroshot")
        self.config = {"backend": backend, "model": self.model, "temperature": 0.0, "few_shot": few_shot,
                       "prompt": "compact_schema+conventions" if backend == "ollama" else "schema+conventions"}

    @property
    def usage(self):
        return self.client.usage

    def prompt(self, question: str, hints: list[str] | None = None, examples: str | None = None, places: str = "") -> str:
        # schema first; conventions/rules and examples next to the question (small models attend to recent context)
        prompt = f"SCHEMA:\n{self.schema_text}\n\n{CONVENTIONS}\n\n"
        examples = self.examples if examples is None else examples
        if examples:
            prompt += f"EXAMPLES:\n{examples}\n\n"
        if hints:   # top-k columns from a schema linker (tokenization / schema-linking ablations)
            prompt += "Likely relevant columns (from a schema linker, may be incomplete): " + ", ".join(hints) + "\n"
        if places:  # resolved place names (Phase 9 pipeline)
            prompt += places + "\n"
        return prompt + f"Question: {question}\nSQL:"

    def predict(self, question: str, hints: list[str] | None = None) -> dict:
        out = self.client.generate(self.prompt(question, hints), SYSTEM)
        return {"sql": extract_sql(out["text"]), "api_latency_s": out["latency_s"], "prompt_tokens": out["prompt_tokens"],
                "output_tokens": out["output_tokens"], "model_version": out["model_version"]}


GeminiBaseline = LLMBaseline  # backwards-compatible name
