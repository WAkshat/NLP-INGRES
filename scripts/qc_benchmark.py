"""INGRES-Bench quality control. Exit code 1 if any hard check fails.

Checks per instance:
  1 sql_executes     SQL runs through the read-only executor (parses + executes, no write access)
  2 gold_reproduces  re-executed result == stored gold_result
  3 schema_refs      listed tables/columns exist in data/schema/schema.json
  4 slots_in_text    every SQL literal (years, categories, numbers, entities, metric) is expressed in the question
                     (language-specific surface forms; fuzzy for noisy hard-test entities)
  5 translation      all language versions of an item share the SQL and all pass check 4
Benchmark-level: no SQL / question text shared across splits; held-out phrasings absent from train/dev.
"""
import json
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.benchmark import lexicon as L  # noqa: E402
from src.benchmark.intents import INTENTS  # noqa: E402
from src.utils.safe_sql import connect_ro, execute  # noqa: E402

SCHEMA = json.loads((ROOT / "data/schema/schema.json").read_text(encoding="utf-8"))
TR = json.loads((ROOT / "data/benchmark/transliterations.json").read_text(encoding="utf-8"))
NUMS = json.loads(json.dumps({  # keep in sync with scripts/build_benchmark.py NUM_WORDS
    "english": {3: "three", 5: "five", 50: "fifty", 70: "seventy", 90: "ninety", 100: "one hundred", 150: "one hundred fifty"},
    "hindi": {3: "तीन", 5: "पाँच", 50: "पचास", 70: "सत्तर", 90: "नब्बे", 100: "सौ", 150: "डेढ़ सौ"},
    "hinglish": {3: "teen", 5: "paanch", 50: "pachaas", 70: "sattar", 90: "nabbe", 100: "sau", 150: "dedh sau"},
    "tamil": {3: "மூன்று", 5: "ஐந்து", 50: "ஐம்பது", 70: "எழுபது", 90: "தொண்ணூறு", 100: "நூறு", 150: "நூற்றைம்பது"}}))


def close(a, b, tol=1e-9):
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and abs(float(a) - float(b)) <= tol * max(1.0, abs(float(b)))
    return a == b


def fuzzy_in(needle: str, text: str, thr: float = 0.7) -> bool:
    needle, text = needle.lower(), text.lower()
    if needle in text:
        return True
    n = len(needle)
    return any(SequenceMatcher(None, needle, text[i:i + n + d]).ratio() >= thr
               for i in range(0, max(1, len(text) - n + 1)) for d in (-1, 0, 1))


def slot_problems(r: dict) -> list[str]:
    lang, text, sql = r["language"], r["question"], r["sql"]
    t_low = text.lower()
    probs = []
    # years
    for y in sorted(set(re.findall(r"'(20\d\d-20\d\d)'", sql))):
        adv, bare = L.year_forms(y, lang)
        forms = set(bare) | {f.split(" ", 1)[-1] if lang == "english" else f for f in adv}
        forms |= {re.sub(r"^(in the |in )", "", f) for f in adv}
        if not any(f.lower().replace("वर्ष ", "") in t_low for f in forms):
            probs.append(f"year {y}")
    # every category literal in the SQL (outside the CASE ranking used by improved/worsened intents) must be named
    sql_no_case = re.sub(r"CASE .*? END", "", sql)
    for c in sorted(set(re.findall(r"'(Safe|Semi-Critical|Critical|Over-Exploited)'", sql_no_case))):
        forms = L.CATEGORIES[c][lang] + (["over-exploited", " oe "] if c == "Over-Exploited" else [])
        if not any(f.lower() in f" {t_low} " for f in forms):
            probs.append(f"category {c}")
    # numbers (k, thresholds)
    for num in re.findall(r"(?:LIMIT|>|BETWEEN|AND) (\d+)\b", sql):
        n = int(num)
        if n in (1,) or (n == 2 and "* 2 >" in sql):
            continue
        if num not in text and NUMS[lang].get(str(n), NUMS[lang].get(n, "@@")) not in text:
            probs.append(f"number {n}")
    # entities
    for e in r["entities"]:
        forms = [e["display"], e["display"].lower()]
        if e["display"] in TR:
            forms += [TR[e["display"]]["hi"], TR[e["display"]]["ta"]]
        noisy = bool(r["noise"])
        if not any(f.lower() in t_low for f in forms) and not (noisy and any(fuzzy_in(f, text, thr=0.6) for f in forms[:1])):  # thr 0.6: deliberate typos in short names
            probs.append(f"entity {e['display']}")
    # metric column named in SELECT/ORDER (only for metric-parameterised intents)
    for col, surfaces in L.METRICS.items():
        if re.search(rf"\.{col}\b", sql) and r["intent"] in METRIC_INTENTS:
            if not any(s.lower() in t_low for s, _ in surfaces[lang]):
                probs.append(f"metric {col}")
    return probs


METRIC_INTENTS = {"unit_metric", "district_metric", "state_metric", "state_volume_bcm", "top_k_units_state",
                  "state_extreme_metric", "unit_metric_change", "district_largest_increase"}


def main() -> int:
    rows = [json.loads(line) for line in (ROOT / "data/benchmark/ingres_bench_v1.jsonl").read_text(encoding="utf-8").splitlines()]
    con = connect_ro(ROOT / "data/processed/ingres.db")
    tables = {t["name"]: {c["name"] for c in t["columns"]} for t in SCHEMA["tables"]}
    fails = defaultdict(list, {k: [] for k in ("sql_executes", "gold_reproduces", "schema_refs", "slots_in_text", "translation")})
    cache = {}
    for r in rows:
        if r["sql"] not in cache:
            cache[r["sql"]] = execute(con, r["sql"])
        res = cache[r["sql"]]
        if res.error:
            fails["sql_executes"].append((r["id"], res.error))
            continue
        got = [list(x) for x in res.rows]
        if len(got) != len(r["gold_result"]) or not all(close(a, b) for ga, gb in zip(got, r["gold_result"]) for a, b in zip(ga, gb)):
            fails["gold_reproduces"].append(r["id"])
        if any(t not in tables for t in r["tables"]) or any(not any(c in tables[t] for t in r["tables"]) for c in r["columns"]):
            fails["schema_refs"].append(r["id"])
        p = slot_problems(r)
        if p:
            fails["slots_in_text"].append((r["id"], p, r["question"]))
    by_item = defaultdict(list)
    for r in rows:
        by_item[r["item_id"]].append(r)
    for iid, rs in by_item.items():
        if len({x["sql"] for x in rs}) != 1 or len(rs) != 4 or len({x["split"] for x in rs}) != 1:
            fails["translation"].append(iid)
    # leakage
    split_of_sql, split_of_q = defaultdict(set), defaultdict(set)
    for r in rows:
        split_of_sql[r["sql"]].add(r["split"])
        split_of_q[r["question"].lower()].add(r["split"])
    fails["leak_sql_across_splits"] = [s[:80] for s, sp in split_of_sql.items() if len(sp) > 1]
    fails["leak_question_across_splits"] = [q for q, sp in split_of_q.items() if len(sp) > 1]
    n_templates = {(i["id"], lang): len(t) for i in INTENTS for lang, t in i["templates"].items()}
    fails["heldout_template_in_train"] = sorted({r["template_id"] for r in rows if r["split"] in ("train", "dev")
                                                 and int(r["template_id"].rsplit("#", 1)[1]) == n_templates[(r["intent"], r["language"])] - 1})
    total = len(rows)
    report = {k: len(v) for k, v in fails.items()}
    print(f"instances: {total}, items: {len(by_item)}")
    for k, v in report.items():
        print(f"  {k:32s} failures: {v}")
    for k, v in fails.items():
        for x in v[:8]:
            print(f"    {k}: {x}")
    (ROOT / "reports").mkdir(exist_ok=True)
    (ROOT / "reports/benchmark_qc.json").write_text(json.dumps({"instances": total, "failures": report,
                                                                "examples": {k: v[:30] for k, v in fails.items()}},
                                                               ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if any(report.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
