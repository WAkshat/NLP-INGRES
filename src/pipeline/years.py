"""Deterministic assessment-year normaliser.

INGRES labels a cycle 'YYYY-(YYYY+1)'. Users write "2024-25", "2024-2025", or name the published report:
"the 2025 assessment" / "2025 ke assessment" / "2025 के आकलन" / "2025 மதிப்பீட்டில்" = cycle '2024-2025'.
The LLM applied this convention wrongly in 55 of 644 baseline queries, so the labels are computed by rule and
passed to it as a hint. Patterns were written against TRAIN + DEV questions only.
"""
from __future__ import annotations

import re

YEARS = ("2019-2020", "2021-2022", "2022-2023", "2023-2024", "2024-2025")
_DIGITS = str.maketrans("०१२३४५६७८९௦௧௨௩௪௫௬௭௮௯", "01234567890123456789")
_RANGE = re.compile(r"(?<!\d)(20\d\d)\s*[-–/]\s*(20\d\d|\d\d)(?!\d)")
_REPORT = re.compile(r"(?<![\d-])(20\d\d)(?!\s*[-–/]\s*\d)\s*(?:के|की|का|ke|ki|ka)?\s*"
                     r"(?:assessment|gwra|आकलन|akalan|aaklan|மதிப்பீட்ட|மதிப்பீடு)", re.I)
_REPORT_PRE = re.compile(r"(?:assessment|gwra)\s+(?:of|for|year)?\s*(20\d\d)(?!\s*[-–/]\s*\d)", re.I)


def year_labels(question: str) -> list[str]:
    """Database assessment_year labels referred to in the question, in order of appearance."""
    t = question.translate(_DIGITS)
    hits = []
    for m in _RANGE.finditer(t):
        a, b = int(m.group(1)), m.group(2)
        if int(b) in (a + 1, (a + 1) % 100):
            hits.append((m.start(), f"{a}-{a + 1}"))
    for rx in (_REPORT, _REPORT_PRE):
        for m in rx.finditer(t):
            n = int(m.group(1))
            hits.append((m.start(), f"{n - 1}-{n}"))
    out = []
    for _, y in sorted(hits):
        if y in YEARS and y not in out:
            out.append(y)
    return out


def render(labels: list[str]) -> str:
    if not labels:
        return ""
    return "Assessment year label(s) for this question (computed by rule): " + ", ".join(f"'{y}'" for y in labels)
