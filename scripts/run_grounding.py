"""Numeric grounding evaluation (Phase 8).

    python scripts/run_grounding.py

On the TEST split, gold SQL is executed (isolating answer generation from SQL errors) and qwen3:8b writes a short
answer in the question's language. Measures:
  1. unsupported-number rate of raw LLM answers (verifier flags)
  2. verifier sensitivity: one number in each grounded answer is perturbed (x0.5 .. x2) -> share detected
     (perturbations that leave the text unchanged after rounding, e.g. 0 x 1.1, are skipped)
  3. verifier false alarms on answers that are grounded by construction (template answers, also rendered in BCM / lakh)
  4. after the fallback (flagged answer -> template answer): unsupported-number rate
Flagged LLM answers are written to flagged_audit.csv for manual labelling (real hallucination vs verifier false alarm).
"""
import json
import random
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.baselines.llm import OllamaClient  # noqa: E402
from src.evaluation.report import bootstrap_ci  # noqa: E402
from src.grounding.verifier import NUM, llm_answer, mask, template_answer, verify  # noqa: E402
from src.utils.safe_sql import connect_ro, execute  # noqa: E402

OUT = ROOT / "experiments/grounding"
FACTORS = (0.5, 0.8, 0.9, 0.95, 1.05, 1.1, 1.25, 2.0)


def perturb(text: str, rng: random.Random):
    m = rng.choice(list(NUM.finditer(mask(text))))
    s = m.group(0)
    v, dec = float(s.replace(",", "")), len(s.split(".")[1]) if "." in s else 0
    f = rng.choice(FACTORS)
    new = f"{v * f:,.{dec}f}" if "," in s else f"{v * f:.{dec}f}"
    return text[:m.start()] + new + text[m.end():], f, s, new


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(0)
    rows = [json.loads(x) for x in (ROOT / "data/benchmark/ingres_bench_v1.jsonl").read_text(encoding="utf-8").splitlines()]
    test = [r for r in rows if r["split"] == "test"]
    con = connect_ro(ROOT / "data/processed/ingres.db")
    client = OllamaClient("qwen3:8b", max_tokens=256)
    recs = []
    for i, r in enumerate(test, 1):
        res = execute(con, r["sql"])
        a = llm_answer(client, r["question"], res.columns, res.rows)
        v = verify(a["text"], res.rows, r["question"], res.columns)
        t = template_answer(res.columns, res.rows)
        rec = {"id": r["id"], "language": r["language"], "difficulty": r["difficulty"], "n_rows": len(res.rows),
               "answer": a["text"], "n_numbers": v["n_numbers"], "unsupported": v["unsupported"], "grounded": v["grounded"],
               "template_grounded": verify(t, res.rows, r["question"], res.columns)["grounded"], "latency_s": a["latency_s"]}
        # grounded-by-construction renderings with unit conversions (false-alarm check)
        nums = [c for row in res.rows[:5] for c in row if isinstance(c, (int, float)) and not isinstance(c, bool)]
        if nums:
            x = nums[0]
            alt = f"{x / 1e5:.2f} BCM; {x / 1e5:.1f} lakh; {round(x)}; {x:,.1f}"
            rec["conversion_grounded"] = verify(alt, res.rows, r["question"], res.columns)["grounded"]
        if v["grounded"] and v["n_numbers"]:
            ptext, f, old, new = perturb(a["text"], rng)
        if v["grounded"] and v["n_numbers"] and ptext != a["text"]:      # skip no-op perturbations (0 x 1.1 = 0)
            rec.update(perturb_factor=f, perturbed=ptext, perturb_detected=not verify(ptext, res.rows, r["question"], res.columns)["grounded"])
        recs.append(rec)
        if i % 100 == 0:
            print(f"  {i}/{len(test)}", flush=True)
    df = pd.DataFrame(recs)
    df.to_json(OUT / "answers.jsonl", orient="records", lines=True, force_ascii=False)
    with_nums = df[df.n_numbers > 0]
    flagged = df[~df.grounded]
    pert = df.dropna(subset=["perturb_factor"])
    out = {
        "n": len(df), "model": "qwen3:8b", "answers_with_numbers": len(with_nums),
        "raw_llm_flagged_rate": round(1 - with_nums.grounded.mean(), 4),
        "raw_llm_flagged_rate_ci95": [round(1 - b, 4) for b in bootstrap_ci(with_nums.grounded)[::-1]],
        "raw_llm_flagged_by_language": (1 - with_nums.groupby("language").grounded.mean()).round(4).to_dict(),
        "raw_llm_flagged_by_difficulty": (1 - with_nums.groupby("difficulty").grounded.mean()).round(4).to_dict(),
        "verifier_detection_rate_perturbed": round(pert.perturb_detected.mean(), 4),
        "verifier_detection_by_factor": pert.groupby("perturb_factor").perturb_detected.agg(["mean", "size"]).round(4).to_dict(orient="index"),
        "false_alarm_template_answers": round(1 - df.template_grounded.mean(), 4),
        "false_alarm_unit_conversions": round(1 - df.conversion_grounded.dropna().astype(bool).mean(), 4),
        "after_fallback_flagged_rate": 0.0 if df.template_grounded.all() else None,
        "share_answers_replaced_by_fallback": round(len(flagged) / len(df), 4),
        "latency_mean_s": round(df.latency_s.mean(), 3),
    }
    (OUT / "results.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    flagged[["id", "language", "answer", "unsupported", "n_rows"]].assign(label="").to_csv(OUT / "flagged_audit.csv", index=False, encoding="utf-8")
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
