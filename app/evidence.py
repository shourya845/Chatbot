"""Deterministic evidence checks used before and after answer generation."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .knowledge import query_terms


ABSTENTION = ("I couldn't verify that information from the available A3i sources. "
              "You can use the demo request form to contact A3i.")
TIME_SENSITIVE = re.compile(
    r"\b(?:current|currently|today|latest|now|price|prices|pricing|cost|available)\b", re.I
)
HIGH_RISK = re.compile(
    r"\b(?:price|prices|pricing|cost|guarantee|current|currently|latest|today|"
    r"how many|percentage|percent|integrat(?:e|es|ion)|support(?:s|ed)?)\b",
    re.I,
)
NUMBER_CLAIM = re.compile(r"(?:[$€£]\s?\d[\d,.]*|\b\d+(?:\.\d+)?\s?%)")
MIN_RELEVANCE_COVERAGE = 0.34


@dataclass(frozen=True)
class EvidenceAssessment:
    status: str
    results: list[dict[str, Any]]


def _record_is_stale(record: dict[str, Any], now: datetime) -> bool:
    if record.get("source") != "approved_local":
        return False
    reviewed = record.get("last_reviewed_at")
    if not isinstance(reviewed, str):
        return True
    try:
        reviewed_at = datetime.fromisoformat(reviewed.replace("Z", "+00:00"))
    except ValueError:
        return True
    max_age = max(1, int(os.getenv("KNOWLEDGE_MAX_AGE_DAYS", "180")))
    return (now - reviewed_at.astimezone(timezone.utc)).days > max_age


def assess_evidence(query: str, results: list[dict[str, Any]]) -> EvidenceAssessment:
    if not results:
        return EvidenceAssessment("missing", [])
    versions: dict[str, str] = {}
    for result in results:
        document_id, version = result.get("document_id"), result.get("version")
        if document_id and document_id in versions and versions[document_id] != version:
            return EvidenceAssessment("conflicting", [])
        if document_id and version:
            versions[document_id] = version
    terms = query_terms(query) - {"a3i", "accel"}
    now = datetime.now(timezone.utc)
    relevant, stale_count = [], 0
    for result in results:
        searchable = " ".join(str(result.get(field, "")) for field in (
            "title", "section_heading", "content", "url"
        ))
        matched = terms & query_terms(searchable)
        coverage = len(matched) / len(terms) if terms else 1.0
        if coverage < MIN_RELEVANCE_COVERAGE:
            continue
        if TIME_SENSITIVE.search(query) and _record_is_stale(result, now):
            stale_count += 1
            continue
        relevant.append(result)
    if relevant:
        return EvidenceAssessment("supported", relevant)
    return EvidenceAssessment("stale" if stale_count else "irrelevant", [])


def requires_buffered_answer(question: str) -> bool:
    return bool(HIGH_RISK.search(question))


def numeric_claims_supported(answer: str, evidence: str) -> bool:
    def normalize(number: str) -> str:
        return number.replace(" ", "").rstrip(".,")

    evidence_numbers = {normalize(number) for number in NUMBER_CLAIM.findall(evidence)}
    answer_numbers = {normalize(number) for number in NUMBER_CLAIM.findall(answer)}
    return answer_numbers <= evidence_numbers
