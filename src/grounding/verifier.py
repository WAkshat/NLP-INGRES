"""Numeric grounding (Phase 8): every number in a natural-language answer must be supported by the SQL result.

A number is supported if it equals (up to the rounding implied by its own written precision, or 0.5% relative) a value
in the result, a unit conversion of one (ham <-> BCM, fraction <-> percent), the row count, a list position, or a
number written in the question. Years / assessment-year labels are exempt (not measurements).
Indian digit scripts (Devanagari, Tamil) and lakh / crore multipliers are normalised first.
"""
from __future__ import annotations

import re

DIGITS = str.maketrans("०१२३४५६७८९௦௧௨௩௪௫௬௭௮௯", "01234567890123456789")
YEAR = re.compile(r"\b(?:19|20)\d\d(?:\s*[-–/]\s*(?:(?:19|20)\d\d|\d\d))?\b")
NUM = re.compile(r"(?<![\w.])\d+(?:,\d+)*(?:\.\d+)?")
MULT = re.compile(r"\s*(lakh|lac|लाख|இலட்சம்|லட்சம்|crore|करोड़|கோடி)", re.I)
MULT_VAL = {"lakh": 1e5, "lac": 1e5, "लाख": 1e5, "இலட்சம்": 1e5, "லட்சம்": 1e5, "crore": 1e7, "करोड़": 1e7, "கோடி": 1e7}


def mask(text: str) -> str:
    """ASCII digits, years blanked; same length as text, so match offsets apply to the original."""
    return YEAR.sub(lambda m: " " * len(m.group(0)), str(text).translate(DIGITS))


def numbers(text: str) -> list[tuple[str, float, int]]:
    """(surface, value, decimals) for each non-year number in text."""
    t = mask(text)
    out = []
    for m in NUM.finditer(t):
        s = m.group(0)
        v = float(s.replace(",", ""))
        dec = len(s.split(".")[1]) if "." in s else 0
        mm = MULT.match(t, m.end())
        if mm:
            mult = MULT_VAL[mm.group(1).lower()]
            v *= mult
            dec -= 5 if mult == 1e5 else 7       # "1.2 lakh" is precise only to 0.1 lakh
        out.append((s, v, dec))
    return out


def reference_values(rows: list, question: str = "", columns: list[str] = ()) -> set[float]:
    vals = {v for c in columns for _, v, _ in numbers(c)}       # result headers can be SQL expressions ("100.0 * ...")
    for r in rows:
        for c in (r if isinstance(r, (list, tuple)) else [r]):
            if isinstance(c, (int, float)) and not isinstance(c, bool):
                vals |= {abs(float(c)), abs(c) / 1e5, abs(c) * 100, abs(c) / 100}     # ham->BCM, fraction<->percent
            elif isinstance(c, str):
                vals |= {v for _, v, _ in numbers(c)}
    vals |= {float(len(rows))} | {float(i) for i in range(1, min(len(rows), 50) + 1)}
    vals |= {v for _, v, _ in numbers(question)}
    return vals


def supported(v: float, dec: int, refs: set[float]) -> bool:
    tol = 0.5 * 10 ** (-dec)
    return any(abs(v - r) <= max(tol, 0.005 * abs(r), 1e-9) for r in refs)


def verify(answer: str, rows: list, question: str = "", columns: list[str] = ()) -> dict:
    refs = reference_values(rows, question, columns)
    nums = numbers(answer)
    bad = [s for s, v, d in nums if not supported(v, d, refs)]
    return {"n_numbers": len(nums), "unsupported": bad, "grounded": not bad}


def fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def template_answer(columns: list[str], rows: list, max_rows: int = 20) -> str:
    """Deterministic, grounded-by-construction rendering of a result (the fallback answer)."""
    if not rows:
        return "No matching records."
    if len(rows) == 1 and len(rows[0]) == 1:
        return f"{columns[0] if columns else 'value'}: {fmt(rows[0][0])}"
    lines = [", ".join(f"{c}: {fmt(v)}" for c, v in zip(columns or [f"col{i}" for i in range(len(rows[0]))], r))
             for r in rows[:max_rows]]
    more = f"\n... ({len(rows)} rows in total)" if len(rows) > max_rows else ""
    return "\n".join(lines) + more


ANSWER_SYSTEM = ("You answer a user's question about Indian groundwater data using ONLY the SQL result given. "
                 "Reply in the same language as the question (Hinglish -> Hinglish), in one or two sentences. "
                 "Copy numbers from the result (you may round to 2 decimals); never invent or compute new numbers. "
                 "Volumes are in hectare-metres (ham). If the result is empty, say no records matched.")


def llm_answer(client, question: str, columns: list[str], rows: list, max_rows: int = 20) -> dict:
    shown = "\n".join(" | ".join(map(str, r)) for r in rows[:max_rows])
    prompt = (f"Question: {question}\nSQL result columns: {' | '.join(columns)}\n{shown}"
              + (f"\n... ({len(rows)} rows in total)" if len(rows) > max_rows else "") + "\nAnswer:")
    out = client.generate(prompt, ANSWER_SYSTEM)
    return {**out, "text": out["text"].strip()}


def grounded_answer(client, question: str, columns: list[str], rows: list) -> dict:
    """LLM answer if all its numbers are grounded, else the deterministic template answer."""
    a = llm_answer(client, question, columns, rows)
    v = verify(a["text"], rows, question, columns)
    if v["grounded"]:
        return {"answer": a["text"], "source": "llm", "llm_answer": a["text"], "verification": v}
    return {"answer": template_answer(columns, rows), "source": "template_fallback", "llm_answer": a["text"], "verification": v}
