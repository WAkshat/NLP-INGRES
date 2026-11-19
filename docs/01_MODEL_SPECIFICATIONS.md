# INGRES — Model Specifications

Every number in this document is produced by `python scripts/model_forensics.py` and stored in
`experiments/forensics/models.json` (label `RUNTIME-VERIFIED`), unless another label is given. Encoder counts come from
enumerating `named_parameters()` in PyTorch. LLM counts come from parsing the GGUF file that Ollama actually loads
(every tensor's shape), not from a model card.

## 1. Inventory

| # | Model | Role in INGRES | Hosting | Trained here? | Used at inference? |
|---|---|---|---|---|---|
| M1 | **qwen3:8b** (Qwen3 8B, GGUF Q4_K_M) | Writes SQL; writes the answer sentence; translation in one experiment | Local, Ollama 0.35.1, GPU | No (prompted) | Yes |
| M2 | **Schema linker**: `multilingual-e5-small`, fine-tuned | Ranks schema columns; retrieves similar train questions | Local, CPU, sentence-transformers | **Yes**, full fine-tune | Yes |
| M3 | **Mention embedder**: `intfloat/multilingual-e5-small`, off-the-shelf | Embedding-similarity feature of the place resolver | Local, CPU | No | Yes |
| M4 | **Entity ranker**: logistic regression | Scores (mention, candidate place) pairs | Local, scikit-learn | **Yes** | Yes |
| M5 | Vocabulary-adapted linker (M2 + 78 tokens) | Tokenization-mitigation experiment | Local | Yes | **No** (experiment only) |
| M6 | TF-IDF char n-gram indexes | Candidate generation (resolver); keyword baseline | Local | Fitted | Yes (resolver) |
| M7 | MultinomialNB language tagger | Code-mixing index in the tokenization study | Local | Fitted | No (study only) |
| M8 | `gemini-3.6-flash` | Intended frontier baseline | Google API | No | **No** — 1 successful call in total; free tier = 20 requests/day |

No LoRA/PEFT adapters exist anywhere in the project.

## 2. M1 — qwen3:8b (the LLM)

### Identity
| Field | Value | Evidence |
|---|---|---|
| Name / family | Qwen3 8B, decoder-only transformer (`general.architecture = qwen3`) | GGUF metadata |
| Authors | Alibaba Cloud (Qwen team) | EXTERNALLY-SOURCED |
| Licence | Apache-2.0 | GGUF `general.license` |
| Ollama tag / ID | `qwen3:8b`, ID `500a1f067a9f` (identical in October and after re-download on 2026-11-17) | RUNTIME (`ollama list`) |
| Weights blob | `sha256:a3de86cd1c132c822487ededd47a324c50491393e6565cd14bafa40d0b8e686f`, 5,225,374,496 bytes, GGUF v3, 399 tensors | RUNTIME |
| Runtime | Ollama 0.35.1 (llama.cpp backend), 100% on GPU (RTX 5060) | RUNTIME (`ollama ps`) |
| How used | Prompted only; no fine-tuning | CODE (`src/baselines/llm.py`) |

### Parameters (exact, from tensor shapes)
| Group | Parameters |
|---|---|
| Token embedding (`token_embd.weight`, 151,936 × 4,096) | 622,329,856 |
| 36 transformer blocks | 6,946,071,552 |
| Output head (`output.weight` 151,936 × 4,096 + final norm 4,096) | 622,333,952 |
| **Total stored** | **8,190,735,360** |

- The output projection is stored as a separate tensor (not tied to the input embedding in this file), so both are counted.
- Trainable in INGRES: **0** (inference only).

| Storage type | Parameters | Share | Tensors |
|---|---|---|---|
| Q4_K (4-bit k-quant) | 6,511,132,672 | 79.5% | token embedding, Q/K/O projections, FFN gate/up, FFN down in 18 layers |
| Q6_K (6-bit k-quant) | 1,528,299,520 | 18.7% | output head (622,329,856) + FFN down in the other 18 layers (905,969,664) |
| F16 | 150,994,944 | 1.8% | attention V projection in all 36 layers |
| F32 | 308,224 | 0.004% | RMSNorm weights |

`general.file_type = 15` (llama.cpp "mostly Q4_K_M"). File size ÷ parameters = 5.10 bits per weight (includes vocabulary and metadata; derived).

### Architecture
| Field | Value |
|---|---|
| Layers (blocks) | 36 |
| Hidden size | 4,096 |
| Feed-forward size | 12,288 |
| Attention heads | 32 query heads, **8 key/value heads** (grouped-query attention), head dim 128 |
| Positional encoding | Rotary (RoPE), base frequency 1,000,000 |
| Normalisation | RMSNorm, ε = 1e-6 |
| Vocabulary | 151,936 tokens (byte-level BPE; GGUF tokenizer model `gpt2`, pre-tokenizer `qwen2`) |
| Special tokens | BOS/PAD id 151643, EOS id 151645 (`<|im_end|>`); chat markers `<|im_start|>`, `<|im_end|>`; no BOS auto-added |
| Maximum context | 40,960 tokens |

### Configuration used by INGRES (`OllamaClient`, `src/baselines/llm.py:127-141`) — CODE-VERIFIED
| Option | Value | Model default (`ollama show --modelfile`) |
|---|---|---|
| `num_ctx` | **8,192** | 40,960 max |
| `temperature` | **0.0** | 0.6 |
| `seed` | 0 | — |
| `num_predict` | 512 (SQL), 256 (answer sentence / translation) | — |
| `think` | **false** (Qwen3 reasoning mode off) | true |
| `top_k` / `top_p` / `repeat_penalty` | defaults 20 / 0.95 / 1 (irrelevant at temperature 0) | 20 / 0.95 / 1 |

Memory: 6.2 GB reported by `ollama ps` with the 8,192-token context; see `docs/04_BENCHMARKS_AND_PERFORMANCE.md` for measured VRAM.

## 3. M2 / M3 — multilingual-e5-small (fine-tuned and base)

### Identity
| Field | Base (M3) | Fine-tuned schema linker (M2) |
|---|---|---|
| Source | `intfloat/multilingual-e5-small`, HF revision `614241f622f53c4eeff9890bdc4f31cfecc418b3` | `experiments/schema_linking/checkpoints/finetuned_e5` (local, git-ignored) |
| Authors | Wang et al., Microsoft (E5 family) — EXTERNALLY-SOURCED | this project |
| Architecture | `BertModel` encoder (MiniLM-style) + mean pooling + L2 normalisation | same |
| Framework | sentence-transformers 3.1.0, transformers 4.57.6, torch 2.14.0+cpu | same |
| Precision | float32 | float32 |
| Licence | MIT — EXTERNALLY-SOURCED | — |

### Parameters (exact)
| Group | Base / fine-tuned | Vocabulary-adapted (M5) |
|---|---|---|
| Word embeddings (rows × 384) | 96,014,208 (250,037 rows) | 96,030,720 (250,080 rows) |
| Position embeddings (512 × 384) | 196,608 | 196,608 |
| Token-type embeddings + embedding LayerNorm | 1,536 | 1,536 |
| 12 encoder layers | 21,293,568 | 21,293,568 |
| Pooler (loaded, **unused**: mean pooling is applied instead) | 147,840 | 147,840 |
| **Total** | **117,653,760** | **117,670,272** |

- 199 parameter tensors, no shared/tied tensors. **82%** of the parameters are the word-embedding table.
- Trainable during fine-tuning: all 117,653,760 (no layers frozen; `requires_grad` true everywhere). Frozen: 0.
- The tokenizer has 250,002 entries but the embedding matrix has 250,037 rows: 35 rows can never be selected.
- M5 adds 78 tokens (tokenizer 250,002 → 250,080) but only 43 new rows (16,512 parameters), because the first 35 new tokens occupy the previously unused rows.

### Architecture and configuration
| Field | Value |
|---|---|
| Layers / heads | 12 / 12 (head dim 32) |
| Hidden size / feed-forward | 384 / 1,536, GELU |
| Dropout (training) | 0.1 hidden, 0.1 attention |
| Positional encoding | Learned absolute, 512 positions |
| Max sequence length (model and configured) | 512 / 512 |
| Actual input length | mean 23.9 tokens per question (BENCH); schema element texts are one line each |
| Sentence embedding | 384-dim, mean-pooled, L2-normalised (norm 1.0 verified) |
| Tokenizer | `XLMRobertaTokenizerFast` (SentencePiece unigram); specials `<s>`, `</s>`, `<pad>`, `<unk>`, `<mask>` |
| Input prefixes | `"query: "` for questions and mentions, `"passage: "` for schema elements and aliases |
| Weights in memory | 470,615,040 bytes (448.8 MiB) per copy |
| Weights file | 470,637,416 bytes (`model.safetensors`); checkpoint directory 488 MB |

### Tensor shapes for one question (fine-tuned linker)
Question: "2024-25 में लुधियाना जिले में कुल भूजल निकासी कितनी थी?"

| Stage | Shape |
|---|---|
| `input_ids`, `attention_mask` | `[1, 23]` |
| Token embeddings (last hidden state) | `[1, 23, 384]` |
| Mean-pooled sentence embedding | `[1, 384]` |
| Schema matrix `E` (106 columns + 9 tables) | `[115, 384]` |
| Scores `q @ E.T` | `[1, 115]` → top-5 over the 106 column rows |
| Train-question matrix `TQ` | `[612, 384]` → 3 nearest examples |

### Fine-tuning of M2 (`src/schema_linking/train.py`, `experiments/schema_linking/finetuned.json`) — CONFIG + CODE
| Item | Value |
|---|---|
| Data | 712 (question, gold column) pairs from the TRAIN split only |
| Negatives | 3 hard negatives per pair + in-batch negatives |
| Loss | InfoNCE / multiple-negatives ranking, similarity scale 20 |
| Optimiser | AdamW, lr 2e-5, linear warm-up over the first 10% of steps, then constant |
| Batch / epochs / steps | 16 / 3 / 135 |
| Seed | 0 |
| Hardware / time | CPU (Ryzen 7 9700X), 386 s |
| Final loss (mean of last 10 steps) | 1.85 |

## 4. M4 — entity ranker (logistic regression)

| Field | Value |
|---|---|
| Class | `sklearn.linear_model.LogisticRegression` (scikit-learn 1.9.1) |
| Parameters | **13** (12 coefficients + 1 intercept) |
| Settings | `C = 1.0`, L2, `class_weight = "balanced"`, `max_iter = 2000`, `random_state = 0` |
| Training data | 18,283 synthetic noisy mentions of 70% of the 9,558 gazetteer entities; pointwise over ≤ 30 candidates each |
| File | `experiments/entity_resolution/ranker.pkl` (812 bytes) |

Coefficients after the 2026-11-17 retraining (with the Tamil fix; baseline-v1 values in brackets):

| Feature | Weight | Feature | Weight |
|---|---|---|---|
| TF-IDF cosine | −2.12 (−1.99) | context: state matches | +0.31 (+0.36) |
| edit ratio (folded) | **+18.95** (+21.47) | context: district matches | +1.87 (+2.09) |
| skeleton ratio | +7.91 (+1.85) | context: state conflict | **−14.88** (−8.78) |
| exact folded match | −0.33 (−0.83) | level = state / district / unit | −6.39 / −7.67 / −8.59 |
| embedding similarity (M3) | **+13.79** (+10.62) | length difference | −1.07 (−4.07) |

## 5. M6 — TF-IDF indexes
| Index | Settings | Size |
|---|---|---|
| Resolver candidates | `TfidfVectorizer(analyzer="char_wb", ngram_range=(2,4), sublinear_tf=True)` over folded aliases; a second index over voicing-neutral forms for Tamil-script mentions (added 2026-11-17) | one row per alias of 9,558 entities |
| Keyword baseline | char 2–4-gram TF-IDF over the 612 train questions | 612 rows |

## 6. Tokenizers compared in the tokenization study (no model weights loaded)
`intfloat/multilingual-e5-small` (XLM-R SentencePiece), `Qwen/Qwen3-8B` (BPE), `bert-base-multilingual-cased` (WordPiece),
`google/muril-base-cased` (WordPiece), `Xenova/gpt-4o` (o200k BPE). Source: `scripts/run_tokenization_study.py:26`.

## 7. What is not known
| Item | Status |
|---|---|
| Parameter count / architecture of `gemini-3.6-flash` | NOT PUBLICLY DISCLOSED — CANNOT VERIFY |
| Training data and procedure of Qwen3 and E5 | EXTERNALLY-SOURCED only; not verified here |
| Accuracy loss of Q4_K_M vs full precision for this task | NOT MEASURED (needs ≥16 GB VRAM for the F16 model) |
