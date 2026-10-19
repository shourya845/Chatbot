"""Reviewed local A3i knowledge records and lightweight keyword retrieval."""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from .config import KNOWLEDGE_DIR


logger = logging.getLogger(__name__)
COLLECTION_PATH = Path(
    os.getenv(
        "A3I_KNOWLEDGE_PATH",
        KNOWLEDGE_DIR / "collection.json",
    )
)
STOPWORDS = set(
    "a an and are as at be by do does for from how i in is it of on or the this "
    "to what which who with you your".split()
)
REQUIRED_FIELDS = (
    "document_id",
    "source_url",
    "page_title",
    "section_heading",
    "content",
    "content_hash",
    "last_reviewed_at",
)
MIN_KEYWORD_COVERAGE = 0.2


def query_terms(text: str) -> set[str]:
    return {
        term for term in re.findall(r"[a-z0-9][a-z0-9-]+", text.casefold())
        if term not in STOPWORDS and len(term) > 1
    }


def load_collection(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or COLLECTION_PATH
    if not target.exists():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        records = payload.get("records", []) if isinstance(payload, dict) else []
        return [record for record in records if isinstance(record, dict)]
    except (OSError, json.JSONDecodeError) as error:
        logger.warning("Knowledge collection could not be loaded (%s)", type(error).__name__)
        return []


def search_approved_knowledge(
    query: str, limit: int = 3, path: Path | None = None
) -> list[dict[str, Any]]:
    """Return only approved records with lexical overlap; never pending drafts."""
    terms = query_terms(query)
    if not terms:
        return []
    ranked = []
    for record in load_collection(path):
        if record.get("approval_status") != "approved":
            continue
        if any(
            not isinstance(record.get(field), str) or not record[field].strip()
            for field in REQUIRED_FIELDS
        ):
            continue
        title_terms = query_terms(record["page_title"])
        heading_terms = query_terms(record["section_heading"])
        content_terms = query_terms(record["content"])
        overlap = terms & content_terms
        matched = terms & (title_terms | heading_terms | content_terms)
        score = 5 * len(terms & heading_terms) + 3 * len(terms & title_terms) + len(overlap)
        coverage = len(matched) / len(terms)
        if score <= 0 or coverage < MIN_KEYWORD_COVERAGE:
            continue
        ranked.append((score, coverage, record))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    results = []
    for _, _, record in ranked[:limit]:
        results.append(
            {
                "url": record["source_url"],
                "title": record["page_title"],
                "section_heading": record["section_heading"],
                "content": record["content"],
                "document_id": record["document_id"],
                "version": record["content_hash"],
                "last_reviewed_at": record["last_reviewed_at"],
                "source": "approved_local",
            }
        )
    return results
