"""
Text utilities for document processing
"""

import re
from typing import List, Dict

def extract_accronyms(text: str) -> List[str]:
    """Extract ACCA-specific acronyms from text"""
    accronyms = []
    
    # Common ACCA acronyms
    patterns = [
        r'\bISA\s*\d+\b',  # ISA 240, ISA 315, etc.
        r'\bIAS\s*\d+\b',  # IAS 16, IAS 2, etc.
        r'\bIFRS\s*\d+\b',  # IFRS 15, etc.
        r'\bAA\b',  # Audit and Assurance
        r'\bAAA\b',  # Advanced Audit and Assurance
        r'\bSBR\b',  # Strategic Business Reporting
        r'\bSBL\b',  # Strategic Business Leader
        r'\bFM\b',  # Financial Management
        r'\bFR\b',  # Financial Reporting
        r'\bTX\b',  # Taxation
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        accronyms.extend([m.upper() for m in matches])
    
    return list(set(accronyms))  # Remove duplicates

def extract_keywords(text: str) -> List[str]:
    """Extract important keywords from text"""
    keywords = []
    
    # Audit-related keywords
    audit_keywords = [
        'risk', 'material', 'assertion', 'evidence', 'procedure',
        'control', 'test', 'sample', 'fraud', 'error', 'misstatement',
        'valuation', 'completeness', 'existence', 'occurrence', 'cut-off',
        'rights', 'obligations', 'presentation', 'disclosure'
    ]
    
    # Professional keywords
    prof_keywords = [
        'professional', 'scepticism', 'judgment', 'ethics',
        'independence', 'objective', 'integrity', 'objectivity',
        'competence', 'confidentiality', 'professional behaviour'
    ]
    
    text_lower = text.lower()
    
    for keyword in audit_keywords + prof_keywords:
        if keyword in text_lower:
            keywords.append(keyword)
    
    return list(set(keywords))

def calculate_readability(text: str) -> Dict:
    """
    Calculate basic readability metrics
    """
    sentences = re.split(r'[.!?]+', text)
    words = text.split()
    
    if not words or not sentences:
        return {
            'word_count': 0,
            'sentence_count': 0,
            'avg_words_per_sentence': 0,
            'avg_word_length': 0
        }
    
    # Remove empty sentences
    sentences = [s for s in sentences if s.strip()]
    
    avg_words = len(words) / len(sentences) if sentences else 0
    avg_word_len = sum(len(w) for w in words) / len(words) if words else 0
    
    return {
        'word_count': len(words),
        'sentence_count': len(sentences),
        'avg_words_per_sentence': round(avg_words, 1),
        'avg_word_length': round(avg_word_len, 1)
    }