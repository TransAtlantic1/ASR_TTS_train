#!/usr/bin/env python3

from scoring import _canonical_eval_en, _normalized_tokens_en, _normalized_tokens_zh


def test_normalized_tokens_en_match_librispeech_case_and_punctuation():
    ref = "THERE'S IRON THEY SAY IN ALL OUR BLOOD"
    hyp = "There's iron, they say, in all our blood."

    assert _normalized_tokens_en(ref) == _normalized_tokens_en(hyp)


def test_normalized_tokens_en_splits_hyphenated_words():
    assert _normalized_tokens_en("self-indulgent") == ["SELF", "INDULGENT"]


def test_canonical_eval_en_normalizes_unicode_apostrophes():
    assert _canonical_eval_en("it’s “fine”") == "IT'S FINE"


def test_normalized_tokens_zh_match_simplified_and_traditional_variants():
    ref = "台湾电脑里有两个文件"
    hyp = "臺灣電腦裡有兩個文件"

    assert _normalized_tokens_zh(ref) == _normalized_tokens_zh(hyp)


def test_normalized_tokens_zh_match_current_jellycat_variants():
    ref = "拼余券仿佛僵尸踪迹"
    hyp = "拚馀劵髣彿殭尸蹤跡"

    assert _normalized_tokens_zh(ref) == _normalized_tokens_zh(hyp)


if __name__ == "__main__":
    test_normalized_tokens_en_match_librispeech_case_and_punctuation()
    test_normalized_tokens_en_splits_hyphenated_words()
    test_canonical_eval_en_normalizes_unicode_apostrophes()
    test_normalized_tokens_zh_match_simplified_and_traditional_variants()
    test_normalized_tokens_zh_match_current_jellycat_variants()
    print("ok")
