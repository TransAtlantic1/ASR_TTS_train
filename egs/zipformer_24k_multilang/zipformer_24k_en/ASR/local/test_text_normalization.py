#!/usr/bin/env python3

from text_normalization import normalize_text, reference_tokens, tokenize_zh_text
from text_policy import canonical_sp_input


def test_normalize_zh_text():
    assert normalize_text("ＡＢＣ，１２3！你好\t世界", "zh") == "abc 123 你好 世界"


def test_tokenize_zh_text_preserves_lowercase():
    assert tokenize_zh_text("abc 123 你好 世界") == "abc 123 你 好 世 界"


def test_normalize_en_text():
    assert normalize_text("  Hello,\tWORLD! It's 2026.  ", "en") == "Hello, WORLD! It's 2026."


def test_normalize_en_text_preserves_hyphen_and_case():
    assert normalize_text(" you- No. ", "en") == "you- No."


def test_reference_tokens():
    assert reference_tokens("ＡＢＣ，１２3！你好", "zh") == ["abc", "123", "你", "好"]
    assert reference_tokens("Hello, WORLD! 2026", "en") == ["Hello,", "WORLD!", "2026"]
    assert reference_tokens("didn't you-", "en") == ["didn't", "you-"]


def test_en_sp_input_matches_stage4_text():
    text = "  Hello,\tWORLD! It's 2026.  "
    assert canonical_sp_input(text, "en") == normalize_text(text, "en")
    assert canonical_sp_input([text], "en") == [normalize_text(text, "en")]


if __name__ == "__main__":
    test_normalize_zh_text()
    test_tokenize_zh_text_preserves_lowercase()
    test_normalize_en_text()
    test_normalize_en_text_preserves_hyphen_and_case()
    test_reference_tokens()
    test_en_sp_input_matches_stage4_text()
    print("ok")
