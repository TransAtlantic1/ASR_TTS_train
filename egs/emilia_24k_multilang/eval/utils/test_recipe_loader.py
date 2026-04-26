#!/usr/bin/env python3

from recipe_loader import load_local_module


def test_load_local_module_supports_sibling_imports():
    text_norm = load_local_module("en", "text_normalization")

    assert text_norm.normalize_en_text("  a   b  ") == "a b"
    assert text_norm.reference_tokens("  a   b  ", "en") == ["a", "b"]


if __name__ == "__main__":
    test_load_local_module_supports_sibling_imports()
