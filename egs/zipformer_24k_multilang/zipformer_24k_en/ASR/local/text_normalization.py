#!/usr/bin/env python3

from typing import List

from text_policy import (
    canonical_reference_tokens,
    canonicalize_en_text,
    canonicalize_text,
    normalize_zh_text,
    tokenize_zh_text,
)


def normalize_en_text(text: str) -> str:
    return canonicalize_en_text(text)


def normalize_text(text: str, language: str) -> str:
    return canonicalize_text(text, language)


def reference_tokens(text: str, language: str) -> List[str]:
    return canonical_reference_tokens(text, language)
