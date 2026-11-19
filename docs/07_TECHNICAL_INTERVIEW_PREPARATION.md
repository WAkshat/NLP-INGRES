# INGRES — Technical Interview Preparation

46 questions a knowledgeable interviewer or examiner could ask about this project, with answers grounded in the code
and the stored results. Numbers: see `docs/09_CHANGELOG_AND_EVIDENCE.md` for their sources.

## A. Problem and data

**1. What exactly does INGRES do?**
It answers questions about India's official groundwater assessments, asked in English, Hindi, Hinglish or Tamil. It
translates each question into one read-only SQL query over a local copy of the INGRES data, runs it, and writes a
one-sentence answer whose numbers are checked against the query result. It is Text-to-SQL, not a chatbot over documents.

**2. Where does the data come from, and how do you know it is right?**
From the INGRES portal's public JSON endpoint, found by reading the portal's JavaScript: 5,299 requests, 0 failures. The
database reproduces the government's published national totals within 0.07% for four cycles (for example GWRA 2025
extraction 247.22 vs 247.22 BCM). An automated test checks this. The UI's Explore page shows 60.6% stage of extraction
for 2024-25, against 60.63% published.

**3. Why was 2016-17 excluded?**
Four states were missing and national totals came out about twice the published values.

**4. Why do you need a cross-year crosswalk?**
INGRES re-issues unit IDs in some cycles: only 14% of unit IDs survive from 2019-20 to 2021-22. A four-stage matcher
(ID → name in district → name in state → guarded fuzzy) links them. A hand check of 40 fuzzy links found 37 correct.

**5. What is the benchmark, and how did you prevent leakage?**
INGRES-Bench v1: 371 questions × 4 languages = 1,484 instances, 38 question types, 4 difficulty levels. Splits are by
item (all languages of a question together), test places are mostly unseen, and one phrasing per type is held out of
train/dev. QC verifies that no SQL or question text crosses splits.

**6. The questions were written with an LLM. Is that valid?**
The SQL and answers come from the real database, and the 4 language versions share the same slots, so meaning cannot
drift between languages. QC had 0 failures, and the slot checker catches 97.1% of deliberately corrupted questions. The
limitation is real: the wording is template-like, and no native speaker has checked it.

## B. Models and parameters

**7. Which models does the system use?**
(1) qwen3:8b via Ollama: writes SQL and answer sentences. (2) multilingual-e5-small, fine-tuned: schema linking and
example retrieval. (3) multilingual-e5-small, off-the-shelf: an embedding feature for place resolution. (4) A logistic
regression with 13 parameters: ranks place candidates. Plus char-n-gram TF-IDF indexes for candidate generation.

**8. How many parameters does the LLM have, and how do you know?**
8,190,735,360, counted from the shapes of all 399 tensors in the GGUF file Ollama loads (`scripts/model_forensics.py`):
622,329,856 for the token embedding, 6,946,071,552 in 36 blocks, and 622,333,952 for the separate output head plus
final norm. It is not taken from a model card.

**9. How is it quantised?**
Q4_K_M: 79.5% of parameters in 4-bit k-quants and 18.7% in 6-bit (Q6_K: the output head, 622.3 M, plus half the
FFN down-projections, 18 of 36 layers, 906.0 M). The attention value projections of all 36 layers (151.0 M, 1.8%) are
F16, and norms are F32. The file is 5,225,374,496 bytes, about 5.10 bits per weight. With an 8,192-token context it uses
6.2 GB on the 8 GB RTX 5060.

**10. Describe the LLM's architecture.**
Decoder-only, 36 layers, hidden size 4,096, FFN 12,288. Grouped-query attention with 32 query heads and 8 key/value
heads (head dim 128), which shrinks the KV cache 4×. RoPE with base 10⁶, RMSNorm, vocabulary 151,936, maximum context
40,960. We use 8,192 so the model and KV cache fit in VRAM.

**11. How many parameters does the encoder have, and where are they?**
117,653,760. 96,014,208 (82%) are the word-embedding table (250,037 × 384, multilingual vocabulary). 21,293,568 are in 12
transformer layers, 196,608 are position embeddings, 1,536 are token-type embeddings and LayerNorm, and 147,840 are a
pooler that is loaded but unused because we mean-pool.

**12. What was fine-tuned, and what was not?**
All 117.65 M encoder parameters were fine-tuned for schema linking (none frozen). The 13-parameter ranker was trained.
The LLM was only prompted. No LoRA, adapters or distillation.

**13. Why a 4-bit 8B model and not GPT/Claude/Gemini?**
The Gemini free tier allowed 20 requests per day (logged), and one evaluation pass is 872 requests. A local model is
free, private, and reproducible within an environment. The cost is accuracy: the frontier upper bound is not measured.

## C. Algorithms

**14. How does schema linking work?**
The question and each of 115 schema elements (106 columns, 9 tables, described in English) are embedded by the encoder.
Elements are ranked by cosine similarity, and the top 5 columns go into the prompt as hints.

**15. How was the schema linker trained, and what is a hard negative?**
InfoNCE (multiple-negatives ranking) with similarity scale 20 on 712 TRAIN (question, column) pairs. Each pair gets 3
hard negatives: columns easy to confuse with the right one (extraction vs stage of extraction; recharge vs extractable
resource) and the same column at another level (unit vs district vs state table). AdamW, lr 2e-5, batch 16, 3 epochs,
386 s on CPU.

**16. How do you know it didn't just memorise question types?**
We removed 25% of question types from training and tested only on those: recall@3 0.851 (3 seeds, range 0.75–0.91)
versus 0.454 off-the-shelf.

**17. How does place resolution work?**
Fold the mention (romanise, lowercase, normalise digraphs, collapse doubled letters, drop the final inherent "a") and
retrieve 30 candidates by character 2–4-gram TF-IDF. Score each candidate with logistic regression over 12 features:
TF-IDF cosine, edit ratio, consonant-skeleton ratio, exact match, e5 cosine, whether the candidate's state/district is
mentioned, state conflict, level, and length difference.

**18. How do you handle a name like "Ramnagar" that exists in 10 states?**
Hierarchy context. If the question mentions a state, candidates in that state get a strong positive feature and
candidates elsewhere a strong negative one (−14.9). Top-1 on ambiguous names: 0.447 without context, 0.973 with it.

**19. What was the Tamil bug, and how did you find it?**
The transliteration library's Tamil→ISO scheme reads Tamil stops as voiced aspirates: கர்நாடகா became "gharnadhagha".
Probing the resolver with Tamil state names, scores were 0.03–0.32, far below the 0.9 threshold. The fix is a small
Tamil romaniser (unvoiced reading) plus a "devoiced" comparison space for Tamil-script mentions, because Tamil writes
k/g, t/d and p/b with one letter. Hand-written Tamil top-1 went 0.568 → 0.806 (128 fixed, 5 broken, p = 6e-32).

**20. What is value snapping?**
After the LLM writes SQL, every literal compared with state_name, district_name or unit_name is checked against that
column. An exact value is kept. A case variant is replaced by the stored spelling. A close misspelling (folded
similarity ≥ 0.80, clearly better than the runner-up) is replaced by the stored name. It exists because the model
rewrote correct spellings it was given ('Mahabubabad' → 'MAHABUBABAD'), and a COUNT over zero rows returns 0, so the
repair loop never saw the error. Replayed on dev outputs: 12 errors fixed, 0 correct answers broken.

**21. Why is the year rule a hint and not an SQL rewrite?**
Some questions compare two years, and the model still has to decide where each year goes. The rule only states which
cycle labels the question means; for example "the 2025 assessment" is `2024-2025`. It is 100% correct on TRAIN and DEV.

**22. How does the repair loop work, and what doesn't it catch?**
If the SQL fails, returns no rows, or returns one all-NULL row, the error text goes back to the model (at most 2 times;
it stops if the model repeats itself). It cannot catch a wrong but non-empty result, such as a COUNT of 0 caused by a
misspelled place. That is why value snapping exists.

**23. How does the numeric verifier work?**
Every number in the answer sentence must equal a value in the result, within the precision it is written with or 0.5%,
after unit conversions (ham ↔ BCM, fraction ↔ percent), Indian digit scripts, 1,23,456 grouping and lakh/crore. Row
counts, list positions and numbers from the question are also allowed; years are exempt. If any number fails, the
sentence is replaced by a plain rendering of the table.

**24. How good is the verifier?**
It caught 98.1% of 215 deliberately planted numeric errors, with 0% false alarms on 384 grounded answers. The LLM put an
unsupported number in 0.83% of answers (2 of 242), both real errors, both caught.

**25. Why execution accuracy rather than exact SQL match?**
Many SQL strings are correct for the same question. EX compares results: multisets of rows, order only when the gold SQL
sorts, numbers within 1e-6 relative, same number of columns.

**26. How do you test significance?**
Paired McNemar exact tests on the same questions, counting questions one system gets right and the other wrong.
95% bootstrap CIs with 2,000 resamples. CIs are optimistic, because the 4 language versions of an item are correlated.

## D. Results and ablations

**27. What are the headline results?**
Test EX (384): keyword baseline 32.6%, LLM zero-shot 18.0%, original pipeline 72.1% (re-run in November;
71.9% in October), improved pipeline v3 **81.3%**. hard_test (260): 58.8% → **70.4%**.
Paired v3 vs original (test): 51 wins / 16 losses, McNemar p = 2e-05.

**28. Which component matters most?**
Retrieved examples: removing them from the original pipeline dropped test EX from 71.9% to 35.4% (p = 2e-30). Next are
the deterministic fixes around the LLM, measured step by step in one environment. TEST: original 72.1% → Tamil-fixed
resolver 74.7% (12/2, p = 0.013) → + year rule 78.4% (21/7, p = 0.013) → + value snapping and metric definitions 81.3%
(24/13, p = 0.099). On DEV the last step looked much larger (83.3 → 92.1%), so part of its DEV gain did not transfer.

**29. Isn't the accuracy inflated by retrieved examples of the same question type?**
Partly, and it was measured. With every training example of the question's own type hidden (`v3_loio`), test EX is
51.0% versus 81.3%. The remaining gap is what the model gains from seeing the same SQL pattern. The keyword
baseline has the same advantage and scores 32.6%.

**30. Why did translating to English first not help?**
The 8B model mistranslated domain terms: अति-दोहित ("over-exploited") became "extremely undernourished", and
எடுப்பு நிலை ("stage of extraction") became "attendance level". The result was 16.4% vs 18.2% direct.

**31. Does tokenizer fragmentation explain worse Hindi/Tamil accuracy?**
No. Qwen3 uses 8.96 tokens per Tamil word against 2.04 for English, but fertility correlates with accuracy only weakly
(ρ ≈ −0.09). A placebo (the keyword baseline, which has no subword tokenizer) correlates more strongly (−0.18), so the
correlation reflects language and item difficulty. Vocabulary adaptation cut Tamil fragmentation 0.63 → 0.43 with no
accuracy gain.

**32. Where does v3 still fail?**
v3 errors on test + hard_test: 149 errors: other (filters, joins, output shape) 62; gold place literal missing from SQL 37; wrong metric / column 22; wrong assessment year 12; wrong aggregation 11; no SQL / execution error 5. Categories are assigned by rules on the predicted SQL (first match wins).

**33. Why did you re-run the original system?**
Re-installing the same model ID with a newer GPU driver reproduced only 24 of 39 October answers exactly, while two
runs in one environment matched 39/39. Comparing October numbers with November numbers would mix environments, so the
original code (tag `baseline-v1`) was re-run with an empty cache in the same environment as v3.

## E. Performance and engineering

**34. How fast is it?**
LLM request (100 test questions, cache bypassed): median 2.01 s, mean 2.18 s, p95 3.28 s; time to first token
median 285 ms; generation 51.8 tokens/s; prompt processing 8,697 tokens/s. End-to-end `Pipeline.sql` median 2.09 s.

**35. What is the bottleneck?**
The LLM: 97.6% of wall time. Before the LLM, place linking dominated: 107 ms of 116 ms per question
in the original code; now 39 ms of 48 ms.

**36. What did you optimize, and by how much?**
(a) All candidate spans embedded in one batched forward pass instead of one per span. (b) The 16,681 alias embeddings
cached on disk. Cold start 22.1 s → 8.3 s; pre-LLM mean 116 ms → 48 ms; pre-LLM throughput 8.6 → 20.9 questions/s.
End-to-end latency did **not** change (median 2,085 → 2,095 ms), because the LLM is 97.6% of it.

**37. How much memory does it use?**
Python process: 1,182 MB resident after loading (two float32 e5 copies at 470.6 MB each, the 24.4 MiB alias matrix,
TF-IDF indexes). Ollama: 6.2 GB for qwen3:8b with an 8,192-token context; GPU total in use during runs about 7.3–7.5 GB of 8.15 GB.

**38. Why not run the encoders on the GPU or with ONNX?**
They take about 9 ms of a request of about 2 s, and the GPU is full with the LLM. The best-case saving is under 1% end to end.

**39. How would you scale to many users?**
Ollama serves one request at a time by default, so throughput is about 0.5 questions per second on this GPU. Options:
`OLLAMA_NUM_PARALLEL` (more KV-cache VRAM per slot), a bigger GPU, or vLLM with continuous batching; the encoders can be
shared, and the SQL is cheap. None of these is measured here.

**40. How is the SQL kept safe?**
A read-only connection plus a SQLite authorizer callback that allows only SELECT/READ/FUNCTION/RECURSIVE, denies
`load_extension`/`readfile`/`writefile`, aborts after 10 s and caps results at 10,000 rows. It is enforced by SQLite
itself, not by string filtering. 13 injection and write attempts are tested.

**41. How do you make results reproducible?**
Seeds everywhere, temperature 0, a fixed model ID, a response cache keyed by the full request, a frozen baseline tag,
and the environment recorded in every benchmark file. Cross-environment GPU nondeterminism was measured (24/39) and is
handled by comparing within one environment.

**42. Why Streamlit?**
It was already a dependency. Chat components, Altair charts and tables are built in, so the whole UI is one Python
file. A FastAPI + React stack would add work without benefit for a single-user demo.

**43. What does the UI show besides the answer?**
A verification badge, the result table with CSV download, an automatic chart, the SQL with any value corrections, and a
trace (schema hints, resolved places, year labels, attempts, time per stage). There are switches to turn components off
live, an Explore page with dashboards straight from the database, and a Results page.

## F. Critical thinking

**44. What would you do next?**
Measure and improve generalisation to unseen question types (pattern-level examples, or QLoRA on TRAIN SQL), get native
speakers to check a sample of each language, measure a frontier-model upper bound on TEST, and add level words
("block", "ज़िला") as a resolver feature.

**45. What is the weakest part of your evaluation?**
The benchmark is template-generated and its test question types overlap with training. The leave-own-intent-out run
measures part of this; a truly held-out question-type split, plus real user questions, would be better evidence.

**46. What makes this project technically distinctive?**
A verified data layer (published totals reproduced within 0.07%), a four-language benchmark built for this domain, and
measured components with paired significance tests. Bugs found by measurement were fixed with regression tests (the
Tamil romanisation, a misleading error taxonomy). Deterministic safeguards wrap the LLM (year rule, value snapping,
numeric verifier, read-only execution), each justified by error analysis on dev and evaluated once on test.
