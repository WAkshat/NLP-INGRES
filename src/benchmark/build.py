"""Build INGRES-Bench: sample real entities per intent, execute gold SQL, render 4 languages, split, add noise.

Every canonical item = one (intent, slots, gold SQL, gold result) rendered in english / hindi / hinglish / tamil.
All language versions of an item share one split (no cross-split paraphrase leakage).
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.benchmark import lexicon as L
from src.benchmark.intents import INTENTS
from src.utils.safe_sql import connect_ro, execute

YEAR_WEIGHTS = {"2019-2020": 1, "2021-2022": 1, "2022-2023": 1, "2023-2024": 1.5, "2024-2025": 3}
CATS = ["Safe", "Semi-Critical", "Critical", "Over-Exploited"]
TRANSITIONS = [("Semi-Critical", "Over-Exploited"), ("Critical", "Over-Exploited"), ("Safe", "Semi-Critical"),
               ("Over-Exploited", "Critical"), ("Semi-Critical", "Safe"), ("Critical", "Semi-Critical"),
               ("Over-Exploited", "Semi-Critical"), ("Semi-Critical", "Critical")]
DIR_WORDS = {"DESC": {"english": "highest", "hindi": "सबसे अधिक", "hinglish": "sabse zyada", "tamil": "மிக அதிகமாக"},
             "ASC": {"english": "lowest", "hindi": "सबसे कम", "hinglish": "sabse kam", "tamil": "மிகக் குறைவாக"}}
UNIT_REF = {  # mention level: 0 name only, 1 + state, 2 + district + state
    "english": ["{unit} {utype}", "{unit} {utype} in {state}", "{unit} {utype} of {district} district, {state}"],
    "hindi": ["{unit} {utype}", "{state} के {unit} {utype}", "{state} के {district} ज़िले के {unit} {utype}"],
    "hinglish": ["{unit} {utype}", "{state} ke {unit} {utype}", "{district} district ({state}) ke {unit} {utype}"],
    "tamil": ["{unit} {utype}", "{state} மாநிலத்தில் உள்ள {unit} {utype}", "{state}, {district} மாவட்டத்தில் உள்ள {unit} {utype}"],
}
MAX_LIST_ROWS = 20


def q(s: str) -> str:
    return s.replace("'", "''")


@dataclass
class Item:
    intent: dict
    slots: dict
    sql: str
    gold_columns: list
    gold_rows: list
    group: str = "A"                      # A: train/dev units, B: test/hard units
    flags: dict = field(default_factory=dict)


class Builder:
    def __init__(self, db: Path, pool_csv: Path, translit: Path, seed: int = 7):
        self.rng = random.Random(seed)
        self.con = connect_ro(db)
        self.pool = pd.read_csv(pool_csv)
        self.names = L.Names(translit)
        self.df = lambda s: pd.DataFrame(execute(self.con, s).rows, columns=execute(self.con, s).columns)  # noqa: E731
        self.gran = self.df("SELECT s.state_name, g.assessment_year, REPLACE(g.unit_type, 'MANDAL', 'BLOCK') AS t, g.n_units "
                            "FROM state_unit_granularity g JOIN states s ON s.state_id = g.state_id")
        au = self.df("SELECT u.unit_id, u.unit_name, d.district_name, s.state_name FROM assessment_units u "
                     "JOIN districts d ON d.district_id = u.district_id JOIN states s ON s.state_id = u.state_id")
        self.n_name = au.groupby(au.unit_name).size()
        self.n_name_state = au.groupby(["unit_name", "state_name"]).size()
        years_present = self.df("SELECT unit_id, assessment_year FROM unit_assessments")
        self.unit_years = years_present.groupby("unit_id").assessment_year.agg(set).to_dict()
        # entity partition: ambiguous / respelled units lean to the test side
        ids = sorted(self.pool.unit_id)
        prng = random.Random(seed + 1)
        self.unit_group = {u: ("B" if prng.random() < 0.4 else "A") for u in ids}
        for r in self.pool.itertuples():
            if r.is_ambiguous_name or r.has_respelling:
                self.unit_group[r.unit_id] = "B" if prng.random() < 0.75 else "A"
        self.states = sorted(self.pool.state_name.unique())
        self.districts = self.pool[["district_name", "state_name", "district_display", "state_display"]].drop_duplicates()
        self.state_display = dict(zip(self.pool.state_name, self.pool.state_display))

    # ---------------------------------------------------------------- helpers
    def year(self) -> str:
        return self.rng.choices(list(YEAR_WEIGHTS), weights=list(YEAR_WEIGHTS.values()))[0]

    def comparable(self, state: str, ya: str, yb: str) -> bool:
        g = self.gran[self.gran.state_name == state]
        a, b = g[g.assessment_year == ya], g[g.assessment_year == yb]
        if a.empty or b.empty or set(a.t) != set(b.t):
            return False
        na, nb = a.n_units.sum(), b.n_units.sum()
        return abs(na - nb) <= 0.1 * max(na, nb)

    def year_pair(self, state: str | None = None):
        pairs = [(a, b) for i, a in enumerate(L.YEARS) for b in L.YEARS[i + 1:]]
        self.rng.shuffle(pairs)
        for a, b in pairs:
            if state is None or self.comparable(state, a, b):
                return a, b
        return None

    def unit_type(self, state: str, year: str | None) -> str:
        g = self.gran[(self.gran.state_name == state) & ((self.gran.assessment_year == year) if year else True)]
        ts = set(g.t)
        return ts.pop() if len(ts) == 1 and next(iter(ts)) in L.UNIT_TYPES else "_UNIT"

    def unit_slots(self, r) -> dict:
        n_nat = self.n_name.get(r.unit_name, 0)
        n_state = self.n_name_state.get((r.unit_name, r.state_name), 0)
        if n_nat == 1:
            level = self.rng.choice([0, 1, 1, 2])
        elif n_state == 1:
            level = self.rng.choice([1, 1, 2])
        else:
            level = 2
        uf = f"u.unit_name = '{q(r.unit_name)}'"
        if level >= 1:
            uf += f" AND s.state_name = '{q(r.state_name)}'"
        if level == 2:
            uf += f" AND d.district_name = '{q(r.district_name)}'"
        return dict(unit_id=r.unit_id, unit=r.unit_name, unit_display=r.unit_display, district=r.district_name,
                    district_display=r.district_display, s=r.state_name, state_display=r.state_display,
                    level=level, uf=uf, unit_type=r.unit_type if r.unit_type in L.UNIT_TYPES else "_UNIT",
                    ambiguous=bool(r.is_ambiguous_name), respelled=bool(r.has_respelling))

    def pick_unit(self, need_years: set | None = None):
        rows = self.pool.sample(frac=1, random_state=self.rng.randint(0, 10**6))
        for r in rows.itertuples():
            if need_years and not need_years <= self.unit_years.get(r.unit_id, set()):
                continue
            return r
        return None

    # ---------------------------------------------------------------- samplers -> slot dicts
    def sample(self, name: str, intent: dict) -> dict | None:
        rng = self.rng
        m = rng.choice(intent["metrics"]) if "metrics" in intent else None
        if name in ("unit_year_metric", "unit_year"):
            y = self.year()
            r = self.pick_unit({y})
            return r and dict(self.unit_slots(r), y=y, m=m)
        if name == "unit_any":
            r = self.pick_unit()
            return r and self.unit_slots(r)
        if name in ("unit_two_years_metric", "unit_two_years"):
            r = self.pick_unit()
            pair = r and self.year_pair(r.state_name)
            if not pair or not set(pair) <= self.unit_years.get(r.unit_id, set()):
                return None
            return dict(self.unit_slots(r), ya=pair[0], yb=pair[1], m=m)
        if name == "unit_ever_category":
            r = self.pick_unit()
            return r and dict(self.unit_slots(r), c=rng.choice(["Over-Exploited", "Critical", "Semi-Critical"]))
        if name in ("district_year_metric", "district_year_category", "district_year"):
            d = self.districts.sample(1, random_state=rng.randint(0, 10**6)).iloc[0]
            return dict(d=d.district_name, district_display=d.district_display, s=d.state_name, state_display=d.state_display,
                        y=self.year(), m=m, c=rng.choice(CATS))
        s = rng.choice(self.states)
        base = dict(s=s, state_display=self.state_display[s], m=m)
        if name in ("state_year_metric", "state_year", "state_year_category", "state_year_oe_rich"):
            return dict(base, y=self.year(), c=rng.choice(CATS))
        if name == "state_year_metric_k":
            return dict(base, y=self.year(), k=rng.choice([3, 5]))
        if name == "state_year_threshold":
            return dict(base, y=self.year(), t=rng.choice([70, 90, 100]))
        if name == "state_year_range":
            t, t2 = rng.choice([(70, 90), (90, 100), (50, 70), (100, 150)])
            return dict(base, y=self.year(), t=t, t2=t2)
        if name in ("state_two_years_transition", "state_two_years_category", "state_two_years_comparable",
                    "state_two_years_metric", "state_two_years_any"):
            pair = self.year_pair(None if name == "state_two_years_any" else s)
            if not pair:
                return None
            c, c2 = rng.choice(TRANSITIONS)
            return dict(base, ya=pair[0], yb=pair[1], c=c if name != "state_two_years_category" else rng.choice(CATS), c2=c2)
        if name == "state_stable_all_years":
            return base if all(self.comparable(s, "2019-2020", y) for y in L.YEARS[1:]) else None
        if name == "two_states_year":
            s2 = rng.choice([x for x in self.states if x != s])
            return dict(base, s2=s2, state2_display=self.state_display[s2], y=self.year())
        if name == "year_metric_dir":
            return dict(y=self.year(), m=m, dir=rng.choice(["DESC", "ASC"]))
        if name in ("year_category_k", "year_category"):
            return dict(y=self.year(), c=rng.choice(CATS), k=rng.choice([3, 5]))
        if name == "category_only":
            return dict(c=rng.choice(CATS))
        if name == "two_years_any":
            pair = self.year_pair()
            return dict(ya=pair[0], yb=pair[1])
        raise KeyError(name)

    # ---------------------------------------------------------------- gold execution + validity
    def valid(self, intent: dict, slots: dict, res) -> bool:
        if res.error or res.truncated or not res.rows:
            return False
        shape = intent["shape"]
        if shape == "scalar":
            if len(res.rows) != 1 or len(res.rows[0]) != 1 or res.rows[0][0] is None:
                return False
            if intent["id"].startswith("count") and res.rows[0][0] == 0 and self.rng.random() < 0.8:
                return False  # keep a few zero answers, but mostly non-trivial counts
        elif any(v is None for row in res.rows for v in row):
            return False
        if shape == "list" and len(res.rows) > MAX_LIST_ROWS:
            return False
        if shape == "table" and intent["id"] == "count_category_two_years" and len(res.rows) != 2:
            return False
        if "uf" in slots:  # unit filter must identify exactly the target unit
            ids = execute(self.con, "SELECT u.unit_id FROM assessment_units u JOIN districts d ON d.district_id = u.district_id "
                                    f"JOIN states s ON s.state_id = u.state_id WHERE {slots['uf']}").rows
            if [r[0] for r in ids] != [slots["unit_id"]]:
                return False
        return True

    def generate(self) -> list[Item]:
        items, seen = [], set()
        for intent in INTENTS:
            made, tries = 0, 0
            while made < intent["n"] and tries < intent["n"] * 60:
                tries += 1
                slots = self.sample(intent["sampler"], intent)
                if not slots:
                    continue
                sql_params = {k: (q(v) if isinstance(v, str) and k in ("s", "s2", "d") else v) for k, v in slots.items()}
                sql = intent["sql"].format(**sql_params)
                if (intent["id"], sql) in seen:
                    continue
                res = execute(self.con, sql)
                if not self.valid(intent, slots, res):
                    continue
                seen.add((intent["id"], sql))
                group = self.unit_group.get(slots.get("unit_id"), None) or ("B" if self.rng.random() < 0.35 else "A")
                items.append(Item(intent, slots, sql, res.columns, [list(r) for r in res.rows], group))
                made += 1
            if made < intent["n"]:
                print(f"  warning: {intent['id']}: {made}/{intent['n']} valid items")
        return items

    # ---------------------------------------------------------------- rendering
    def render(self, item: Item, lang: str, template: str, rng: random.Random, force_latin: bool = False) -> str:
        s = item.slots
        name = (lambda disp: disp) if force_latin else (lambda disp: self.names(disp, lang, rng))
        v = {}
        if "m" in s and s["m"]:
            surf, g = rng.choice(L.METRICS[s["m"]][lang])
            v["metric"] = surf
            fem = g == "f"
            v["ka"] = {"hindi": "की" if fem else "का", "hinglish": "ki" if fem else "ka"}.get(lang, "")
            v["tha"] = {"hindi": "थी" if fem else "था", "hinglish": "thi" if fem else "tha"}.get(lang, "")
            v["kitna"] = {"hindi": "कितनी" if fem else "कितना", "hinglish": "kitni" if fem else "kitna"}.get(lang, "")
        else:
            v.update(ka={"hindi": "का", "hinglish": "ka"}.get(lang, ""), tha={"hindi": "था", "hinglish": "tha"}.get(lang, ""),
                     kitna={"hindi": "कितना", "hinglish": "kitna"}.get(lang, ""))
        if "s" in s:
            v["state"] = name(s["state_display"])
            ut = s.get("unit_type") or self.unit_type(s["s"], s.get("y") or s.get("yb"))
            v["utype"], v["utypes"] = L.UNIT_TYPES[ut][lang]
        else:
            v["utype"], v["utypes"] = L.UNIT_TYPES["_UNIT"][lang]
        if "s2" in s:
            v["state2"] = name(s["state2_display"])
        if "district_display" in s:
            v["district"] = name(s["district_display"])
        if "unit_display" in s:
            v["unit"] = name(s["unit_display"])
            v["unit_ref"] = UNIT_REF[lang][s["level"]].format(**v)
        if s.get("y"):
            v["year"] = rng.choice(L.year_forms(s["y"], lang)[0])
        if s.get("ya"):
            v["year_a"] = rng.choice(L.year_forms(s["ya"], lang)[1])
            v["year_b"] = rng.choice(L.year_forms(s["yb"], lang)[1])
        for k in ("c", "c2"):
            if s.get(k):
                v["cat" if k == "c" else "cat2"] = rng.choice(L.CATEGORIES[s[k]][lang])
        for k in ("k", "t", "t2"):
            if k in s:
                v[k] = s[k]
        if s.get("dir"):
            v["dir_word"] = DIR_WORDS[s["dir"]][lang]
        text = template.format(**v)
        text = re.sub(r"\s+", " ", text).strip()
        return text[0].upper() + text[1:] if lang in ("english", "hinglish") else text


def stable_hash(*parts) -> int:
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:8], 16)
