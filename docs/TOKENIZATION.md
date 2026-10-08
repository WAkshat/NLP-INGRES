# Tokenization and code-mixing study (Phase 7)

Scripts: `scripts/run_tokenization_study.py` (descriptive + correlational), `scripts/run_tokenization_mitigation.py`
(mitigation). Code: `src/tokenization/`. Outputs: `experiments/tokenization/`. All numbers below are read from those files.

## 1. Questions
1. How much more do the tokenizers in this system fragment Hindi, Hinglish and Tamil than English?
2. Does fragmentation (fertility) explain the per-language accuracy drop, once we control for confounds?
3. How code-mixed is Hinglish, and does mixing change fragmentation?
4. Do mitigations help: translate-first (Method 1) vs direct multilingual (Method 2) vs vocabulary adaptation (Method 3)?

## 2. Measures
- **Fertility** = subword tokens / words (Rust et al., 2021); **fragmentation** = share of words split into >= 2 tokens.
  Words are whitespace tokens with punctuation stripped. Python's `\w` would split Indic words at vowel signs, so it is not used.
- **CMI** (Gambäck & Das, 2016): word-level language tags. Script decides Devanagari and Tamil words. Latin words are
  tagged English or romanised Hindi using lexicons built from TRAIN questions plus a char n-gram classifier. Place names
  and numbers count as language-independent.
- Tokenizers (pre-declared): XLM-R / multilingual-e5-small (the schema linker), Qwen3 (the LLM), mBERT, MuRIL (Indic),
  GPT-4o o200k.

## 3. Fertility (all 1,484 instances; 95% bootstrap CIs in `fertility_by_language.csv`)

| Tokenizer | English | Hindi | Hinglish | Tamil |
|---|---|---|---|---|
| XLM-R (schema linker) | 1.65 | 1.67 | 1.67 | 2.27 |
| **Qwen3 (LLM)** | 2.04 | **5.01** | 2.25 | **8.96** |
| mBERT | 1.67 | 2.30 | 1.77 | 3.27 |
| MuRIL (Indic) | 1.45 | 1.38 | 1.47 | 1.67 |
| GPT-4o o200k | 1.70 | 2.09 | 1.83 | 3.05 |

Qwen3 breaks 99% of Hindi and Tamil words into several pieces. A Tamil question costs it 111 tokens, against 28 for the same
question in English (3.9x). MuRIL, trained on Indian languages, is nearly flat across languages.
Figures: `fig/fertility_by_language.png`, `fig/fragmentation_by_language.png`.

## 4. Code-mixing
| | English | Hindi | Hinglish | Tamil |
|---|---|---|---|---|
| mean CMI | 0.7 | 0.6 | **33.0** | 1.4 |
| share of questions mixed | 7.8% | 6.5% | **96.2%** | 12.9% |

Within Hinglish, more mixing goes with **lower** fertility for every tokenizer (Spearman ρ from −0.23 for XLM-R to
−0.35 for Qwen3; all CIs exclude 0). Mixing in English words such as *assessment*, *blocks* or *over-exploited* replaces
romanised Hindi words that these tokenizers split more.

## 5. Does fertility explain accuracy? (dev + test + hard_test)

| Outcome ~ fertility | pooled ρ | within-item r (same question, 4 languages) |
|---|---|---|
| Schema linking R@3, off-the-shelf ~ XLM-R | −0.07 [−0.14, −0.01] | −0.20 [−0.27, −0.13] |
| Schema linking R@3, fine-tuned ~ XLM-R | −0.07 [−0.14, −0.01] | −0.11 [−0.17, −0.05] |
| EX, qwen3:8b zero-shot ~ Qwen3 | −0.09 [−0.16, −0.03] | −0.13 [−0.21, −0.05] |
| **Placebo:** EX, keyword baseline A ~ Qwen3 | **−0.18 [−0.25, −0.12]** | **−0.22 [−0.29, −0.15]** |

**The placebo check fails.** Baseline A uses no subword tokenizer at all. Its accuracy still correlates with Qwen3
fertility, and more strongly than the LLM's accuracy does. So the fertility–accuracy correlation here is driven by
something both share: the language and the item, i.e. how hard the question is to match. It is not evidence that
fragmentation itself causes errors. Within one language, the LLM shows no consistent link: ρ is −0.18 in Hinglish and
near 0 in English, Hindi and Tamil. Figure: `fig/outcome_vs_fertility.png`.

## 6. Mitigation

All runs use qwen3:8b, temperature 0, with the same prompt (`experiments/tokenization/mitigation.json`). Significance is a
paired McNemar exact test on the same instances.

| Method (dev+test+hard_test, n=872) | EX [95% CI] | English | Hindi | Hinglish | Tamil | latency |
|---|---|---|---|---|---|---|
| Method 2: direct multilingual (baseline D) | 0.182 [0.156, 0.208] | 0.225 | 0.165 | 0.197 | 0.142 | 2.5 s |
| Method 1: translate → English → SQL | 0.164 [0.140, 0.189] | 0.225 | 0.128 | 0.165 | 0.138 | 3.0 s |

Translating first **does not help**. It loses 1.8 points overall (30 wins vs 46 losses, p = 0.08, not significant)
and loses in every non-English language. Reading the instances where translation flipped a correct answer to a wrong one,
the main failure is **domain terms mistranslated into everyday meanings**. Examples: अति-दोहित (over-exploited) →
"extremely undernourished"; गंभीर (critical) → "severe"; अर्ध-गंभीर (semi-critical) → "moderate"; பாதுகாப்பான (safe) → "protected";
எடுப்பு நிலை (stage of extraction) → "attendance level"; आकलन (assessment) → "projection". Place names are occasionally
dropped too. The direct prompt keeps the original terms, which the schema conventions then anchor.

| Schema-linker hints (top-5 columns in the prompt; TEST, n=384) | EX [95% CI] | English | Hindi | Hinglish | Tamil |
|---|---|---|---|---|---|
| direct, no hints (baseline D) | 0.180 | 0.229 | 0.177 | 0.188 | 0.125 |
| + fine-tuned linker hints (Phase 5) | **0.232** [0.193, 0.274] | 0.313 | 0.198 | 0.229 | 0.188 |
| + vocabulary-adapted linker hints (Method 3) | 0.232 [0.190, 0.273] | 0.292 | 0.198 | 0.219 | 0.219 |

The fine-tuned linker's hints add **+5.2 points EX** (36 wins vs 16 losses, McNemar p = 0.008). This is the first measured
end-to-end gain from a learned component. Vocabulary-adapted hints give exactly the same overall EX.

**Method 3, vocabulary adaptation of the schema linker.** 78 frequent, heavily split TRAIN words were added as whole tokens,
for example आकलन, इकाइयाँ, நிலத்தடி, ஒன்றியங்கள், अति-दोहित and over-exploited. Each new embedding starts as the mean of its old
pieces, followed by the same contrastive fine-tuning as Phase 5.

| | fertility (all) | Tamil frag. | R@3 overall | English | Hindi | Hinglish | Tamil |
|---|---|---|---|---|---|---|---|
| fine-tuned (Phase 5) | 1.84 | 0.63 | 0.896 [0.879, 0.913] | 0.955 | 0.913 | 0.872 | 0.846 |
| + vocabulary adaptation | 1.70 | 0.43 | 0.897 [0.879, 0.914] | 0.924 | 0.944 | 0.871 | 0.850 |

Adaptation cuts fragmentation a lot (Tamil 0.63 → 0.43) but leaves overall recall unchanged. Hindi gains 3 points,
English loses 3 and Tamil is flat. This matches §5: in this system, fragmentation is not the bottleneck.

## 7. Conclusions
- The LLM's tokenizer is very unequal: Tamil costs about 4x the tokens of English, which matters for latency and cost.
- Fertility does not explain the accuracy gap once confounds are controlled. The placebo shows the raw correlation is confounded.
- Translating to English first does not help an 8B model, and vocabulary adaptation does not help the schema linker or
  end-to-end EX.
- What helps is better schema linking: fine-tuned linker hints add +5.2 EX points (p = 0.008), in every language.
- Hinglish questions that mix in more English words are tokenized more efficiently.

## 8. Limitations
- Benchmark questions are LLM-authored and template-based. They have not been checked by native speakers.
- Only one LLM (qwen3:8b) was evaluated end to end, and one vocabulary-adaptation setting (78 words) was tried.
- Language tags for romanised words come from lexicons. Measured on train templates, they are approximate for unseen words.
