#!/usr/bin/env python3

import re
import string
import unicodedata
from typing import List, Sequence, Union


CJK_CHAR_PATTERN = re.compile(
    r"([\u1100-\u11ff\u2e80-\ua4cf\ua840-\uD7AF\uF900-\uFAFF\uFE30-\uFE4F\uFF65-\uFFDC\U00020000-\U0002FFFF])"
)
WHITESPACE_PATTERN = re.compile(r"\s+")

COMMON_EXTRA_PUNCT = "“”‘’«»‹›…—–·`´，。！？；：（）【】《》、～「」『』﹃﹄〔〕〈〉﹏￥"
ZH_PUNCT_TRANSLATION = str.maketrans(
    {ch: " " for ch in set(string.punctuation + COMMON_EXTRA_PUNCT)}
)


def collapse_whitespace(text: str) -> str:
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def tokenize_zh_text(text: str) -> str:
    chars = CJK_CHAR_PATTERN.split(text.strip())
    return " ".join(part.strip() for part in chars if part.strip())


def normalize_zh_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.lower()
    text = text.translate(ZH_PUNCT_TRANSLATION)
    return collapse_whitespace(text)


def canonicalize_en_text(text: str) -> str:
    return collapse_whitespace(unicodedata.normalize("NFKC", text))


def canonicalize_text(text: str, language: str) -> str:
    language = language.lower()
    if language == "zh":
        return normalize_zh_text(text)
    if language == "en":
        return canonicalize_en_text(text)
    raise ValueError(f"Unsupported language: {language}")


def canonical_reference_tokens(text: str, language: str) -> List[str]:
    normalized = canonicalize_text(text, language)
    if not normalized:
        return []
    if language.lower() == "zh":
        return tokenize_zh_text(normalized).split()
    return normalized.split()


def canonical_sp_input(
    texts: Union[str, Sequence[str]], language: str
) -> Union[str, List[str]]:
    language = language.lower()
    if isinstance(texts, str):
        normalized = canonicalize_text(texts, language)
        return tokenize_zh_text(normalized) if language == "zh" else normalized

    if language == "zh":
        return [tokenize_zh_text(canonicalize_text(text, language)) for text in texts]
    return [canonicalize_text(text, language) for text in texts]
