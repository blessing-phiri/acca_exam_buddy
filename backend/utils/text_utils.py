"""
Text utilities for document processing.
"""

from __future__ import annotations

import re
from typing import Dict, List


def extract_acronyms(text: str) -> List[str]:
    """Extract ACCA-specific acronyms from text."""
    acronyms: List[str] = []

    patterns = [
        r"\bISA\s*\d+\b",
        r"\bIAS\s*\d+\b",
        r"\bIFRS\s*\d+\b",
        r"\bAA\b",
        r"\bAAA\b",
        r"\bSBR\b",
        r"\bSBL\b",
        r"\bFM\b",
        r"\bFR\b",
        r"\bTX\b",
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        acronyms.extend(match.upper() for match in matches)

    return sorted(set(acronyms))


def extract_accronyms(text: str) -> List[str]:
    """Backward-compatible alias for older typoed function name."""
    return extract_acronyms(text)


def extract_keywords(text: str) -> List[str]:
    """Extract important keywords from text."""
    keywords: List[str] = []

    audit_keywords = [
        "risk",
        "material",
        "assertion",
        "evidence",
        "procedure",
        "control",
        "test",
        "sample",
        "fraud",
        "error",
        "misstatement",
        "valuation",
        "completeness",
        "existence",
        "occurrence",
        "cut-off",
        "rights",
        "obligations",
        "presentation",
        "disclosure",
    ]

    professional_keywords = [
        "professional",
        "scepticism",
        "judgment",
        "ethics",
        "independence",
        "objective",
        "integrity",
        "objectivity",
        "competence",
        "confidentiality",
        "professional behaviour",
    ]

    text_lower = text.lower()
    for keyword in audit_keywords + professional_keywords:
        if keyword in text_lower:
            keywords.append(keyword)

    return sorted(set(keywords))


def calculate_readability(text: str) -> Dict:
    """Calculate basic readability metrics."""
    sentences = [sentence for sentence in re.split(r"[.!?]+", text) if sentence.strip()]
    words = text.split()

    if not words or not sentences:
        return {
            "word_count": 0,
            "sentence_count": 0,
            "avg_words_per_sentence": 0,
            "avg_word_length": 0,
        }

    avg_words = len(words) / len(sentences)
    avg_word_len = sum(len(word) for word in words) / len(words)

    return {
        "word_count": len(words),
        "sentence_count": len(sentences),
        "avg_words_per_sentence": round(avg_words, 1),
        "avg_word_length": round(avg_word_len, 1),
    }
