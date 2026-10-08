# Numeric grounding (Phase 8)

Code: `src/grounding/verifier.py`. Run: `python scripts/run_grounding.py`. Results: `experiments/grounding/{results.json,
answers.jsonl, flagged_audit.csv}`. Tests: `tests/test_grounding.py`.

## 1. Problem
After the SQL runs, a person wants a sentence, not a table: *"Ludhiana extracted 1,23,456 ham in 2024-25."* An LLM
writing that sentence can **invent, mis-copy or mis-scale numbers** (a wrong count, a decimal shift, ham written as BCM).
For official water data, a fluent wrong number is worse than no answer.

## 2. Method
1. **Answer writer** (`llm_answer`). qwen3:8b gets the question, the result columns and up to 20 result rows. It is told to
   answer in the question's language using only numbers from the result.
2. **Verifier** (`verify`). Every number in the answer is extracted and must be *supported* by the result:
   - Number extraction normalises Devanagari (०-९) and Tamil (௦-௯) digits, Indian grouping (1,23,456) and
     **lakh / crore** words in English, Hindi and Tamil.
   - A number is supported if it equals a reference value up to the precision it is written with (for example, 49.2
     covers 49.15–49.25) or within 0.5% relative.
   - Reference values are every numeric cell plus its unit conversions (ham ↔ BCM ÷10⁵, fraction ↔ percent ×100),
     numbers inside text cells or column headers, the row count, list positions 1..n, and numbers written in the question.
   - **Years and assessment-year labels are exempt** (2024-25, 2025): they are labels, not measurements.
3. **Fallback** (`grounded_answer`). If any number is unsupported, the LLM sentence is replaced by a deterministic
   rendering of the result table (`template_answer`), which is grounded by construction. The UI shows a warning when this happens.

## 3. Evaluation (TEST split, 384 questions)
Gold SQL is executed, so answer writing is evaluated on its own, separately from SQL errors.

| Measure | Result |
|---|---|
| Answers containing numbers | 242 / 384 |
| **Raw LLM answers with an unsupported number** | **0.83%** (2/242), 95% CI [0.0, 2.1] |
| — by language | English 0, Hindi 0, Hinglish 1.6%, Tamil 1.6% |
| **Manual audit of the flagged answers** | **2/2 are real hallucinations**: "8 blocks" for a 7-row result (Hinglish); "82.69%" for a true value of 8.27% (Tamil, decimal shift) |
| **Verifier sensitivity:** one number per grounded answer changed by ×0.5…×2 (215 real changes) | **98.1%** detected (100% at ×0.8, ×0.9, ×0.95, ×1.05; 96–97% at ×0.5, ×1.1, ×1.25, ×2) |
| False alarms on grounded-by-construction answers (template rendering, 384) | **0%** |
| False alarms on unit-converted renderings (BCM, lakh, rounded, Indian grouping) | **0%** |
| Unsupported numbers after the fallback | **0%** (0.5% of answers replaced by the table rendering) |
| Cost | 1 extra LLM call per question, mean 2.36 s on the RTX 5060 |

The 4 missed perturbations all produced a value between 1900 and 2099 (for example 1005 × 2 = 2010), which the
verifier exempts as a year. 25 perturbations were skipped because rounding left the text unchanged (0 × 1.1 = 0).

## 4. Bugs found by this evaluation (fixed before the numbers above)
- **Column headers are SQL expressions.** A result column named `100.0 * sa.extraction_irrigation_ham / ...` made
  "100.0" look unsupported (9.4% false alarms on template answers). Header numbers are now reference values.
- **Lakh precision.** "0.9 lakh" for 88,788 ham was flagged because the precision reduction only applied to values ≥ 1 lakh.
  Both cases have regression tests.

## 5. Conclusions
- With the result in front of it, qwen3:8b rarely invents numbers (under 1%). But when it does, the errors are serious
  (a 10× decimal shift, a wrong count). Both cases were in Hinglish and Tamil answers.
- A deterministic verifier catches nearly all numeric errors with no false alarms, and costs no extra model call.
  It is cheap insurance for official data.

## 6. Limitations
- The verifier checks that a number **exists in the result**, not that the sentence uses it correctly. A right number for the
  wrong place, or a swapped pair of values, passes.
- Years are not checked. Numbers written as words ("seventy", "सत्तर") are not extracted.
- Small integers are often supported by chance (list positions, row counts), so a wrong small count can pass.
  The "8 vs 7" case was caught only because 8 exceeded the row count.
- Perturbations are synthetic. Real hallucinations were few (2), so precision on real errors rests on a small sample.
