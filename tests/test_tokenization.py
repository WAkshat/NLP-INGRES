from src.tokenization.metrics import LanguageTagger, tokenizer_stats, words
from src.tokenization.mitigation import select_new_tokens


class CharTok:
    """Fake tokenizer: one token per 2 characters of each whitespace word."""

    def __call__(self, text, add_special_tokens=False):
        return {"input_ids": [0] * sum((len(w) + 1) // 2 for w in text.split())}


def test_words_keeps_indic_words_whole():
    # Python's \w would split at vowel signs (matras); words() must not
    assert words("पंजाब में कितने ब्लॉक?") == ["पंजाब", "में", "कितने", "ब्लॉक"]
    assert words("எத்தனை ஒன்றியங்கள்?") == ["எத்தனை", "ஒன்றியங்கள்"]


def test_tokenizer_stats():
    st = tokenizer_stats(CharTok(), "ab abcd")
    assert st["n_words"] == 2 and st["n_tokens"] == 3 and st["fertility"] == 1.5 and st["frag_rate"] == 0.5


def test_cmi_pure_vs_mixed():
    t = LanguageTagger({"punjab"})
    assert t.cmi("How many blocks in Punjab were over-exploited?") == 0
    assert t.cmi("पंजाब में कितने ब्लॉक अति-दोहित थे?") == 0
    assert t.cmi("Punjab ke kitne blocks over-exploited the?") > 0
    assert t.tag("Punjab mein 2024-25")[0] == "u" and t.tag("Punjab mein 2024-25")[2] == "u"


def test_select_new_tokens_prefers_frequent_fragmented_words():
    rows = [{"language": "hindi", "question": "आकलनइकाइयाँ ab"}] * 5 + [{"language": "english", "question": "assessmentunits"}] * 9
    assert select_new_tokens(rows, CharTok(), n=5, min_count=3, min_pieces=3) == ["आकलनइकाइयाँ"]
