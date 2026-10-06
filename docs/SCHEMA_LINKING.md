# Learned Schema Linking (Phase 5)

Code: `src/schema_linking/{retrieval,train}.py`. Run: `python scripts/train_schema_linker.py` (and
`--intent-holdout 0.25 --seed N`). Results: `experiments/schema_linking/{finetuned.json, ablation_by_language.csv,
intent_holdout.json, per_question.csv}`. Checkpoint: `experiments/schema_linking/checkpoints/` (git-ignored, ~470 MB).

## Method
Bi-encoder `intfloat/multilingual-e5-small` fine-tuned contrastively (InfoNCE / multiple-negatives ranking, scale 20,
lr 2e-5, batch 16, 3 epochs, seed 0, CPU, 386 s) on **TRAIN-split questions only**: 712 (question, gold column) pairs,
each with 3 **hard negatives**: semantically adjacent columns (recharge vs extractable resource vs natural discharge;
extraction vs stage of extraction vs its irrigation/domestic/industrial parts; stage of extraction vs category;
rainfall vs rainfall recharge; unit type vs category) and the **same column at another administrative level**
(unit vs district vs state assessments). Random negatives only pad when fewer hard negatives exist.

## Ablation (column retrieval, dev + test + hard_test, 864 questions with content columns)

| Method | English | Hindi | Hinglish | Tamil | Overall R@3 |
|---|---:|---:|---:|---:|---:|
| 1. No schema linking (random) | 0.025 | 0.033 | 0.041 | 0.012 | 0.028 |
| 2. BM25 | 0.447 | 0.009 | 0.603 | 0.009 | 0.267 |
| 3. Off-the-shelf multilingual-e5-small | 0.600 | 0.339 | 0.421 | 0.276 | 0.409 |
| 4. Fine-tuned multilingual-e5-small (ours) | 0.954 | 0.913 | 0.872 | 0.846 | **0.896** |

| Method | R@1 | R@3 | R@5 | MRR | R@3 test | R@3 hard_test |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 0.161 | 0.267 | 0.307 | 0.230 | 0.287 | 0.260 |
| Off-the-shelf | 0.221 | 0.409 | 0.499 | 0.353 | 0.432 | 0.425 |
| Fine-tuned | 0.710 | 0.896 | 0.943 | 0.809 | 0.896 | 0.903 |

Held-out phrasings (the phrasing never used in train/dev): fine-tuned R@3 0.905 vs 0.896 overall, so no drop.

## Generalisation to unseen question types (leave-intents-out)
Train and test share question types, so part of the gain could be learning "this question type uses column X".
We retrained while removing 25% of the 38 intents entirely, and evaluated only on those unseen intents:

| Seed | Held-out-intent questions | Off-the-shelf R@3 | Fine-tuned R@3 |
|---|---:|---:|---:|
| 0 | 300 | 0.391 | 0.750 |
| 1 | 232 | 0.519 | 0.914 |
| 2 | 248 | 0.450 | 0.890 |
| Mean | | 0.454 | **0.851** |

The gain largely survives on unseen question types (seed 0 is lowest; Tamil drops most, to 0.62 in that seed).

## Caveats
- One schema, one domain: this measures in-domain linking, not transfer to new databases.
- Gold excludes join keys and name columns; values (place names) are handled by the entity resolver (Phase 6).
- Single training seed for the main model; the leave-intents-out runs give a sense of variance (0.75-0.91).
- The effect of better linking on **execution accuracy** (linker hints in the LLM prompt) is not yet measured.
