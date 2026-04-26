#!/usr/bin/env python3

from scoring import _canonical_eval_en, _normalized_tokens_en


def test_normalized_tokens_en_match_librispeech_case_and_punctuation():
    ref = "THERE'S IRON THEY SAY IN ALL OUR BLOOD"
    hyp = "There's iron, they say, in all our blood."

    assert _normalized_tokens_en(ref) == _normalized_tokens_en(hyp)


def test_normalized_tokens_en_splits_hyphenated_words():
    assert _normalized_tokens_en("self-indulgent") == ["SELF", "INDULGENT"]


def test_canonical_eval_en_normalizes_unicode_apostrophes():
    assert _canonical_eval_en("it’s “fine”") == "IT'S FINE"


if __name__ == "__main__":
    test_normalized_tokens_en_match_librispeech_case_and_punctuation()
    test_normalized_tokens_en_splits_hyphenated_words()
    test_canonical_eval_en_normalizes_unicode_apostrophes()
    print("ok")
