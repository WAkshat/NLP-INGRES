"""Tokenization mitigation methods.

Method 1  translate-then-parse: the local LLM translates the question into English, then the same Text-to-SQL prompt.
Method 2  direct multilingual parsing (the zero-shot baseline D).
Method 3  vocabulary adaptation of the small encoder (schema linker): frequent, heavily fragmented TRAIN words are
          added to the XLM-R tokenizer as whole tokens; each new embedding is initialised to the mean of its old
          sub-token embeddings; then the same contrastive fine-tuning as Phase 5.
"""
from __future__ import annotations

from collections import Counter

import torch

from src.tokenization.metrics import words

TRANSLATE_SYSTEM = ("Translate the user's question into English. Keep every place name (state, district, block, "
                    "taluk, mandal) as it is, written in Latin letters. Keep all numbers, percentages and years exactly "
                    "as written. Output only the English translation, nothing else.")


def translate(client, question: str, language: str) -> dict:
    if language == "english":
        return {"text": question, "latency_s": 0.0, "prompt_tokens": 0, "output_tokens": 0}
    out = client.generate(question, TRANSLATE_SYSTEM)
    return {**out, "text": out["text"].strip().strip('"')}


def select_new_tokens(train_rows: list[dict], tok, n: int = 400, min_count: int = 3, min_pieces: int = 3) -> list[str]:
    """Most frequent non-English TRAIN words that the tokenizer splits into >= min_pieces pieces."""
    cnt = Counter(w for r in train_rows if r["language"] != "english" for w in words(r["question"]))
    scored = []
    for w, c in cnt.items():
        if c < min_count or any(ch.isdigit() for ch in w):
            continue
        k = len(tok(w, add_special_tokens=False)["input_ids"])
        if k >= min_pieces:
            scored.append((c * (k - 1), w))          # tokens saved over the training corpus
    return [w for _, w in sorted(scored, reverse=True)[:n]]


def adapt_vocabulary(st_model, new_words: list[str]) -> int:
    """Add words to a SentenceTransformer's tokenizer; mean-of-subtokens initialisation. Returns #tokens added."""
    tf = st_model[0]                                  # Transformer module
    tok, enc = tf.tokenizer, tf.auto_model
    old_ids = {w: tok(w, add_special_tokens=False)["input_ids"] for w in new_words}
    # XLM-R SentencePiece marks word starts with '▁'; add both forms so the word matches with and without a leading space
    added = tok.add_tokens([w for w in new_words])
    enc.resize_token_embeddings(len(tok))
    emb = enc.get_input_embeddings().weight
    with torch.no_grad():
        for w in new_words:
            nid = tok.convert_tokens_to_ids(w)
            if nid is not None and nid >= emb.shape[0] - added and old_ids[w]:
                emb[nid] = emb[old_ids[w]].mean(dim=0)
    return added
