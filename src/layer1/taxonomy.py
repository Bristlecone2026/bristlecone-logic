"""
Bristlecone Logic - Layer 1: Intent Taxonomy & Input Sanitization Engine
Validates raw payloads, strips malicious injection vectors, and categorizes intent.
"""

import re
from enum import Enum
from typing import Dict, Any, Tuple


class TaskCategory(str, Enum):
    COMMODITY = "COMMODITY_VALIDATION"
    STRUCTURED = "STRUCTURED_TRANSFORM"
    DIRTY_WORK = "DIRTY_WORK_EXTRACTION"
    REJECTED = "SECURITY_VIOLATION"


class TaxonomyEngine:
    """Zero-Trust input filter and intent classifier."""

    # High-risk patterns for basic prompt injection mitigation
    SANITY_BLOCKED_PATTERNS = [
        r"ignore previous instructions",
        r"system prompt",
        r"override security",
        r"sudo",
        r"<script",
    ]

    @classmethod
    def sanitize_input(cls, text: str) -> str:
        """Strips harmful markup and normalizes whitespace."""
        if not text:
            return ""
        # Remove direct script tags / simple injections
        cleaned = re.sub(r"<[^>]*>", "", text)
        return cleaned.strip()

    @classmethod
    def classify_and_validate(cls, intent: str, context: Dict[str, Any]) -> Tuple[TaskCategory, Dict[str, Any]]:
        """
        Processes intent and assigns classification metadata.
        Raises ValueError if prompt injection or malformed payload is detected.
        """
        clean_intent = cls.sanitize_input(intent)

        # 1. Security Check
        for pattern in cls.SANITY_BLOCKED_PATTERNS:
            if re.search(pattern, clean_intent, re.IGNORECASE):
                raise ValueError(f"Payload blocked by Layer 1 Zero-Trust filter: Pattern '{pattern}' detected.")

        intent_lower = clean_intent.lower()

        # 2. Categorization Logic
        dirty_keywords = ["scrape", "pdf", "audit", "compliance", "legacy", "raw_html"]
        structured_keywords = ["transform", "map", "schema", "convert", "json", "parse"]

        if any(kw in intent_lower for kw in dirty_keywords) or len(str(context)) > 1500:
            category = TaskCategory.DIRTY_WORK
        elif any(kw in intent_lower for kw in structured_keywords) or bool(context):
            category = TaskCategory.STRUCTURED
        else:
            category = TaskCategory.COMMODITY

        return category, {
            "sanitized_intent": clean_intent,
            "category": category.value,
            "context_size_bytes": len(str(context)),
            "sanitized": True
        }
