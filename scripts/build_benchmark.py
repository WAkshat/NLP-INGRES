"""Build INGRES-Bench v1 -> data/benchmark/ingres_bench_v1.jsonl (+ one file per split).

    python scripts/build_benchmark.py

Deterministic (seeded). See docs/INGRES_BENCH.md for the construction protocol.
"""
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.benchmark import lexicon as L  # noqa: E402
from src.benchmark.build import Builder, stable_hash  # noqa: E402
from src.ingestion.build_db import METHOD_CAVEAT  # noqa: E402

SEED = 7
VERSION = "v1"
OUT = ROOT / "data/benchmark"
LANG_CODE = {"english": "en", "hindi": "hi", "hinglish": "hing", "tamil": "ta"}
NUM_WORDS = {
    "english": {3: "three", 5: "five", 50: "fifty", 70: "seventy", 90: "ninety", 100: "one hundred", 150: "one hundred fifty"},
    "hindi": {3: "तीन", 5: "पाँच", 50: "पचास", 70: "सत्तर", 90: "नब्बे", 100: "सौ", 150: "डेढ़ सौ"},
    "hinglish": {3: "teen", 5: "paanch", 50: "pachaas", 70: "sattar", 90: "nabbe", 100: "sau", 150: "dedh sau"},
    "tamil": {3: "மூன்று", 5: "ஐந்து", 50: "ஐம்பது", 70: "எழுபது", 90: "தொண்ணூறு", 100: "நூறு", 150: "நூற்றைம்பது"},
}
PCT_WORD = {"english": " percent", "hindi": " प्रतिशत", "hinglish": " percent", "tamil": " சதவீதம்"}


def typo(name: str, rng: random.Random) -> str:
    """One realistic keyboard / phonetic slip in a Latin-script name."""
    ops = []
    vowels = [i for i, c in enumerate(name) if c.lower() in "aeiou" and 0 < i < len(name) - 1]
    if vowels:
        ops.append(lambda s: (lambda i: s[:i] + s[i + 1:])(rng.choice(vowels)))                    # drop a vowel
    if len(name) > 3:
        ops.append(lambda s: (lambda i: s[:i] + s[i + 1] + s[i] + s[i + 2:])(rng.randrange(1, len(s) - 2)))  # swap
    ops.append(lambda s: (lambda i: s[:i] + s[i] + s[i:])(rng.randrange(1, len(s))))              # double a letter
    for a, b in (("ee", "i"), ("oo", "u"), ("sh", "s"), ("w", "v"), ("v", "w"), ("ph", "f"), ("aa", "a"), ("i", "ee")):
        if a in name.lower():
            ops.append(lambda s, a=a, b=b: re.sub(a, b, s, count=1, flags=re.I))                  # phonetic spelling
    out = rng.choice(ops)(name)
    return out if out != name else name + name[-1]


def schema_refs(sql: str, schema: dict) -> tuple[list, list]:
    tables = [t["name"] for t in schema["tables"] if re.search(rf"\b{t['name']}\b", sql)]
    cols = sorted({c["name"] for t in schema["tables"] if t["name"] in tables for c in t["columns"]
                   if re.search(rf"\b{c['name']}\b", sql)})
    return tables, cols


def assign_split(item, rng) -> str:
    if item.group == "A":
        return "dev" if rng.random() < 0.23 else "train"
    s = item.slots
    hard_p = 0.8 if (s.get("ambiguous") or s.get("respelled")) else 0.55 if item.intent["difficulty"] in ("cross_year", "multi_hop") else 0.25
    return "hard_test" if rng.random() < hard_p else "test"


def main():
    schema = json.loads((ROOT / "data/schema/schema.json").read_text(encoding="utf-8"))
    b = Builder(ROOT / "data/processed/ingres.db", OUT / "entity_pool.csv", OUT / "transliterations.json", seed=SEED)
    items = b.generate()
    # historical INGRES respellings of pool units (old name -> canonical unit), natural noise for hard-test
    ren = pd.read_csv(ROOT / "reports/crosswalk_renames.csv")
    respell = ren[ren.level == "unit"].groupby("canonical_id").name_in_year.agg(lambda s: sorted(set(s))).to_dict()

    rng = random.Random(SEED)
    rows = []
    for n, it in enumerate(sorted(items, key=lambda i: (i.intent["id"], i.sql)), start=1):
        item_id = f"IB_{n:04d}"
        split = assign_split(it, rng)
        tables, cols = schema_refs(it.sql, schema)
        entities = []
        s = it.slots
        # entities = what the question actually mentions (a unit at mention level 0 is named without its state)
        level = s.get("level", 2)
        if "unit_id" in s:
            entities.append(dict(type="unit", db_name=s["unit"], display=s["unit_display"], id=s["unit_id"],
                                 mention_level=level, ambiguous_name=s["ambiguous"], has_respelling=s["respelled"]))
        if s.get("district_display") and level == 2:
            entities.append(dict(type="district", db_name=s.get("d", s.get("district")), display=s["district_display"]))
        for k in ("s", "s2"):
            if k in s and level >= 1:
                entities.append(dict(type="state", db_name=s[k], display=s["state_display" if k == "s" else "state2_display"]))
        for lang in L.LANGS:
            lrng = random.Random(stable_hash(item_id, lang, SEED))
            templates = it.intent["templates"][lang]
            if split in ("train", "dev"):
                t_idx = lrng.randrange(len(templates) - 1)                         # last phrasing held out
            else:
                t_idx = len(templates) - 1 if lrng.random() < 0.5 else lrng.randrange(len(templates))
            noise, force_latin = [], False
            if split == "hard_test":
                saved = dict(s)
                if "unit_display" in s and s["unit_id"] in respell and lrng.random() < 0.7:
                    s["unit_display"] = lrng.choice(respell[s["unit_id"]]).replace("_", " ")
                    noise.append("historical_respelling")
                    force_latin = True
                elif "unit_display" in s and lrng.random() < 0.6:
                    s["unit_display"] = typo(s["unit_display"], lrng)
                    noise.append("typo_entity")
                    force_latin = True
                elif "state_display" in s and lrng.random() < 0.4:
                    s["state_display"] = typo(s["state_display"], lrng)
                    noise.append("typo_entity")
                    force_latin = True
                if lang in ("hindi", "tamil") and not force_latin and lrng.random() < 0.5:
                    force_latin = True
                    noise.append("latin_script_entity")
                elif lang in ("hindi", "tamil") and force_latin:
                    noise.append("latin_script_entity")
                if any(k in s for k in ("t", "k")) and lrng.random() < 0.6:
                    for k in ("t", "t2", "k"):
                        if k in s:
                            s[k] = NUM_WORDS[lang][s[k]]
                    noise.append("number_words")
            text = b.render(it, lang, templates[t_idx], lrng, force_latin=force_latin)
            if split == "hard_test":
                it.slots = saved  # restore exact slots for the next language
                s = it.slots
                text = re.sub(r"(\D)%", lambda m: m.group(1) + PCT_WORD[lang], text) if "number_words" in noise else text
                if lang in ("english", "hinglish") and lrng.random() < 0.5:
                    text = text.lower().rstrip("?.")
                    noise.append("lowercase_no_punct")
            rows.append(dict(
                id=f"{item_id}_{LANG_CODE[lang]}", item_id=item_id, benchmark_version=VERSION, language=lang,
                script=L.SCRIPT[lang] if not (force_latin and lang in ("hindi", "tamil")) else L.SCRIPT[lang] + "+latin",
                split=split, difficulty=it.intent["difficulty"], intent=it.intent["id"], template_id=f"{it.intent['id']}#{lang}#{t_idx}",
                question=text, sql=it.sql, tables=tables, columns=cols, entities=entities,
                expected_result_shape=it.intent["shape"], gold_columns=it.gold_columns, gold_result=it.gold_rows,
                noise=noise, methodology_caveat=METHOD_CAVEAT if it.intent.get("caveat") else None,
                notes="LLM-authored template text; translations slot-aligned, not native-speaker verified"))
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / f"ingres_bench_{VERSION}.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    for sp in ("train", "dev", "test", "hard_test"):
        with open(OUT / f"{sp}.jsonl", "w", encoding="utf-8") as f:
            for r in rows:
                if r["split"] == sp:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
    df = pd.DataFrame(rows)
    print(f"{df.item_id.nunique()} items, {len(df)} instances")
    print(df.drop_duplicates("item_id").groupby(["split", "difficulty"]).size().unstack(fill_value=0))
    print("noise in hard_test:", Counter(n for ns in df[df.split == "hard_test"].noise for n in ns))


if __name__ == "__main__":
    main()
