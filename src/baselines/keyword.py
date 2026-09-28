"""Baseline A: keyword / template retrieve-and-fill Text-to-SQL.

1. Retrieve the lexically closest TRAIN question (char 2-4-gram TF-IDF, digits masked) and take its SQL as a skeleton.
2. Extract slots from the new question with rules: years, category words (4-language lexicon), numbers,
   and place names matched against a gazetteer built from database names only. Devanagari / Tamil text is
   romanised generically (ISO -> ASCII fold) before matching; the benchmark's own transliteration table is NOT used.
3. Replace the skeleton's literals (years, categories, numbers, state / district / unit names) with the extracted ones.
No learning beyond nearest-neighbour retrieval; no LLM.
Caveat: the category / metric keyword lexicon is the benchmark's own (src/benchmark/lexicon.py), so this is an
optimistic keyword system (it knows every surface form the benchmark uses).
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from indic_transliteration import sanscript
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

from src.benchmark import lexicon as L
from src.utils.safe_sql import execute

CAT_RE = r"'(Safe|Semi-Critical|Critical|Over-Exploited)'"
NUM_WORDS = {"three": 3, "five": 5, "fifty": 50, "seventy": 70, "ninety": 90, "hundred": 100, "teen": 3, "paanch": 5,
             "pachaas": 50, "sattar": 70, "nabbe": 90, "sau": 100, "तीन": 3, "पाँच": 5, "पचास": 50, "सत्तर": 70,
             "नब्बे": 90, "सौ": 100, "மூன்று": 3, "ஐந்து": 5, "ஐம்பது": 50, "எழுபது": 70, "தொண்ணூறு": 90, "நூறு": 100}


def romanise(text: str) -> str:
    out = text
    if re.search(r"[ऀ-ॿ]", out):
        out = sanscript.transliterate(out, sanscript.DEVANAGARI, sanscript.ISO)
    if re.search(r"[஀-௿]", out):
        out = sanscript.transliterate(out, sanscript.TAMIL, sanscript.ISO)
    return unicodedata.normalize("NFKD", out).encode("ascii", "ignore").decode()


def fold(s: str) -> str:
    s = re.sub(r"[^a-z0-9 ]", " ", romanise(s).lower())
    for a, b in (("aa", "a"), ("ee", "i"), ("oo", "u"), ("sh", "s"), ("w", "v"), ("ph", "f"), ("kh", "k"), ("gh", "g"),
                 ("dh", "d"), ("th", "t"), ("bh", "b"), ("ch", "c"), ("jh", "j"), ("z", "j")):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s).strip()


class Gazetteer:
    """DB names only. Each entry: folded name -> list of (type, db_name, state, district)."""

    def __init__(self, con):
        self.entries = {}
        q = lambda s: execute(con, s).rows  # noqa: E731
        for (st,) in q("SELECT state_name FROM states"):
            self._add(st, ("state", st, st, None))
        for d, st in q("SELECT d.district_name, s.state_name FROM districts d JOIN states s ON s.state_id = d.state_id"):
            self._add(d, ("district", d, st, d))
        for u, d, st in q("SELECT u.unit_name, d.district_name, s.state_name FROM assessment_units u "
                          "JOIN districts d ON d.district_id = u.district_id JOIN states s ON s.state_id = u.state_id"):
            self._add(u, ("unit", u, st, d))
        self.by_len = sorted(self.entries, key=len, reverse=True)

    def _add(self, name, entry):
        k = fold(name.replace("_", " "))
        if k:
            self.entries.setdefault(k, []).append(entry)
        if entry[0] == "state" and k == "tamilnadu":
            self.entries.setdefault("tamil nadu", []).append(entry)

    def find(self, text: str, fuzzy: float = 0.84):
        """Return [(position, entry_list)] of non-overlapping name mentions, exact first then fuzzy."""
        t = f" {fold(text)} "
        hits, taken = [], [False] * len(t)
        for k in self.by_len:
            for m in re.finditer(rf"(?<= ){re.escape(k)}(?= )", t):
                if not any(taken[m.start():m.end()]):
                    hits.append((m.start(), self.entries[k]))
                    taken[m.start():m.end()] = [True] * (m.end() - m.start())
        # fuzzy single/double-token matches for leftover words (typos)
        words = [(m.start(), m.group()) for m in re.finditer(r"[a-z][a-z0-9]{3,}", t)]
        for i, (pos, w) in enumerate(words):
            if taken[pos]:
                continue
            for cand in (w, w + " " + words[i + 1][1] if i + 1 < len(words) else None):
                if not cand:
                    continue
                best = max(((SequenceMatcher(None, cand, k).ratio(), k) for k in self.by_len if abs(len(k) - len(cand)) <= 2),
                           default=(0, None))
                if best[0] >= fuzzy:
                    hits.append((pos, self.entries[best[1]]))
                    taken[pos:pos + len(cand)] = [True] * len(cand)
                    break
        return sorted(hits, key=lambda h: h[0])


def extract_years(text: str) -> list[str]:
    t = romanise(text)
    found = []
    for m in re.finditer(r"(20\d\d)\s*-\s*(20\d\d|\d\d)\b|(20\d\d)\s*(?:assessment|ke assessment|ke akalana|ka akalana|matippitt|mat)", t, re.I):
        if m.group(1):
            a = int(m.group(1))
            y = f"{a}-{a + 1}"
        else:
            b = int(m.group(3))
            y = f"{b - 1}-{b}"
        if y in L.YEARS and y not in found:
            found.append(y)
    return found


def extract_categories(text: str) -> list[str]:
    t = text.lower()
    hits = []
    for c, forms in L.CATEGORIES.items():
        for lang_forms in forms.values():
            for f in lang_forms:
                for m in re.finditer(re.escape(f.lower()), t):
                    hits.append((m.start(), m.end(), c))
    hits.sort(key=lambda h: (h[0], -(h[1] - h[0])))
    out, end = [], -1
    for s, e, c in hits:                       # longest non-overlapping ("semi-critical" beats "critical")
        if s >= end:
            out.append(c)
            end = e
    return out


def extract_metric(text: str) -> str | None:
    """Longest metric surface form (any language) found in the text -> column name."""
    t = text.lower()
    best = max(((len(f), col) for col, langs in L.METRICS.items() for forms in langs.values() for f, _ in forms
                if f.lower() in t), default=None)
    return best[1] if best else None


def extract_numbers(text: str) -> list[int]:
    t = re.sub(r"20\d\d\s*-\s*(20)?\d\d|20\d\d", " ", text)   # drop years
    nums = [(m.start(), int(m.group())) for m in re.finditer(r"\b\d{1,3}\b", t)]
    nums += [(m.start(), v) for w, v in NUM_WORDS.items() for m in re.finditer(re.escape(w), t.lower())]
    return [v for _, v in sorted(nums)]


class KeywordBaseline:
    name = "A_keyword_template"

    def __init__(self, con, train_rows: list[dict]):
        self.con = con
        self.gaz = Gazetteer(con)
        self.state_names = {r[0] for r in execute(con, "SELECT state_name FROM states").rows}
        self.train = train_rows
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True)
        self.X = self.vec.fit_transform([self._mask(r["question"]) for r in train_rows])

    @staticmethod
    def _mask(q: str) -> str:
        return re.sub(r"\d", "0", q.lower())

    def neighbour(self, question: str) -> dict:
        sims = linear_kernel(self.vec.transform([self._mask(question)]), self.X).ravel()
        return self.train[int(sims.argmax())]

    def predict(self, question: str) -> dict:
        nb = self.neighbour(question)
        sql = nb["sql"]
        years, cats, nums = extract_years(question), extract_categories(question), extract_numbers(question)
        # --- years: replace skeleton years in order of first appearance
        sk_years = list(dict.fromkeys(re.findall(r"'(20\d\d-20\d\d)'", sql)))
        for old, new in zip(sk_years, years):
            sql = sql.replace(f"'{old}'", f"'@Y{new}'")
        sql = sql.replace("'@Y", "'")
        # --- categories outside the CASE ranking
        case = re.findall(r"CASE .*? END", sql)
        body = re.sub(r"CASE .*? END", "@CASE@", sql)
        sk_cats = list(dict.fromkeys(re.findall(CAT_RE, body)))
        for old, new in zip(sk_cats, cats):
            body = body.replace(f"'{old}'", f"'@C{new}'")
        body = body.replace("'@C", "'")
        for c in case:
            body = body.replace("@CASE@", c, 1)
        sql = body
        # --- metric column (only when the skeleton uses exactly one parameterised metric)
        metric = extract_metric(question)
        sk_metrics = {c for c in L.METRICS if re.search(rf"\b{c}\b", sql)}
        if metric and len(sk_metrics) == 1:
            sql = re.sub(rf"\b{sk_metrics.pop()}\b", metric, sql)
        # --- numbers after LIMIT / > / BETWEEN .. AND
        sk_nums = [m for m in re.finditer(r"(LIMIT|>|BETWEEN|AND) (\d+)\b(?! \*)", sql) if m.group(2) not in ("1",)]
        for m, new in zip(reversed(sk_nums), reversed(nums[:len(sk_nums)])):
            sql = sql[:m.start(2)] + str(new) + sql[m.end(2):]
        # --- place names
        ents = self.gaz.find(question)
        states = [e for _, es in ents for e in es if e[0] == "state"]
        dists = [e for _, es in ents for e in es if e[0] == "district"]
        units = [e for _, es in ents for e in es if e[0] == "unit"]
        sk_states = list(dict.fromkeys(re.findall(r"state_name (?:= |IN \()'([^']+)'", sql)))
        sk_states += [s for s in re.findall(r", '([^']+)'\)", sql) if s not in sk_states and s in self.state_names]
        new_states = list(dict.fromkeys(e[1] for e in states))
        for old, new in zip(sk_states, new_states):
            sql = sql.replace(f"'{old}'", f"'@S{new}'")
        sql = sql.replace("'@S", "'")
        st = new_states[0] if new_states else None
        m = re.search(r"district_name = '([^']+)'", sql)
        if m and dists:
            pick = next((d for d in dists if d[2] == st), dists[0])
            sql = sql.replace(f"district_name = '{m.group(1)}'", f"district_name = '{pick[1]}'")
        m = re.search(r"unit_name = '([^']+)'", sql)
        if m and units:
            pick = next((u for u in units if u[2] == st), units[0])
            sql = sql.replace(f"unit_name = '{m.group(1)}'", f"unit_name = '{pick[1].replace(chr(39), chr(39) * 2)}'")
        return {"sql": sql, "neighbour_id": nb["id"], "intent_guess": nb["intent"]}
