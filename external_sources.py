"""Discover external A3i evidence; only reviewed snapshots can reach the chatbot."""

import argparse
import hashlib
import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from langchain_tavily import TavilySearch

from conversation import mentioned_products
from website import search_terms

DB_PATH = Path(__file__).parent / "data" / "external_sources.sqlite3"
DISCOVERY_DOMAINS = ["linkedin.com", "en.wikipedia.org", "nvidia.com", "anthropic.com"]


def external_allowed(query: str) -> bool:
    """External evidence covers company background, never product promises."""
    return not mentioned_products(query) and not re.search(
        r"\b(pric\w*|costs?|quotes?|fees?|plans?|subscriptions?|products?|features?|"
        r"integrations?|polic\w*|privacy|terms|refunds?|retention|demos?|meetings?|trials?)\b",
        query, re.I,
    ) and bool(re.search(
        r"\b(found\w*|cofounders?|established|headquarters|headquartered|based|located|location|leadership|ceo|coo|"
        r"announcements?|news|partners?|partnerships?)\b|company (?:background|history)",
        query, re.I,
    ))


def allowed_url(url: str) -> bool:
    """Allow known public pages, not arbitrary URLs proposed by a model."""
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.username or parsed.password
                or parsed.port not in (None, 443) or parsed.query or parsed.fragment):
            return False
        host, path = parsed.hostname, parsed.path.rstrip("/")
        if host in {"linkedin.com", "www.linkedin.com"}:
            return path == "/company/a3i-accelerators" or path.startswith("/posts/a3i-accelerators_")
        if host == "en.wikipedia.org":
            return path.startswith("/wiki/") and ":" not in path and "%" not in path
        return any(host == domain or (host or "").endswith("." + domain)
                   for domain in ("nvidia.com", "anthropic.com"))
    except ValueError:
        return False


def store_candidates(items: list[dict]) -> list[int]:
    """Deduplicate exact snapshots without approving new or changed content."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    ids = []
    with closing(sqlite3.connect(DB_PATH, timeout=10)) as db, db:
        db.execute("""CREATE TABLE IF NOT EXISTS sources (
            id INTEGER PRIMARY KEY, snapshot_hash TEXT UNIQUE NOT NULL,
            url TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL,
            published_at TEXT, retrieved_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('pending_review', 'approved', 'rejected')),
            reviewed_at TEXT
        )""")
        for item in items[:3]:
            url = str(item.get("url", ""))
            title = str(item.get("title") or "")[:500]
            content = str(item.get("raw_content") or item.get("content") or "")[:12000].strip()
            identity = title + "\n" + content
            if not allowed_url(url) or not re.search(r"\ba3i[\s-]+accel(?:erators)?\b", identity, re.I):
                continue
            if "linkedin.com" not in urlsplit(url).hostname and "a3i-accel.com" not in content.casefold():
                continue
            if not content:
                continue
            published = str(item["published_date"])[:100] if item.get("published_date") else None
            digest = hashlib.sha256(json.dumps([url, title, content, published]).encode()).hexdigest()
            db.execute("""INSERT OR IGNORE INTO sources
                (snapshot_hash, url, title, content, published_at, retrieved_at, status)
                VALUES (?, ?, ?, ?, ?, ?, 'pending_review')""",
                (digest, url, title, content, published, datetime.now(timezone.utc).isoformat()))
            ids.append(db.execute("SELECT id FROM sources WHERE snapshot_hash = ?", (digest,)).fetchone()[0])
    return ids


def discover(query: str) -> list[int]:
    """Ask Tavily for public text; search domains never come from the visitor."""
    response = TavilySearch(
        max_results=3, topic="general", search_depth="basic",
        include_domains=DISCOVERY_DOMAINS, include_raw_content=True,
    ).invoke({"query": "A3i Accel " + query, "include_domains": DISCOVERY_DOMAINS})
    if not isinstance(response, dict) or response.get("error"):
        raise ValueError("External discovery is unavailable; check Tavily configuration or quota.")
    return store_candidates(response.get("results", []))


def list_sources() -> list[dict]:
    if not DB_PATH.exists():
        return []
    with closing(sqlite3.connect(DB_PATH, timeout=10)) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute("SELECT * FROM sources ORDER BY id DESC")]


def review(source_id: int, status: str) -> None:
    if status not in {"approved", "rejected"}:
        raise ValueError("Choose approved or rejected")
    if not DB_PATH.exists():
        raise ValueError("Source ID not found")
    with closing(sqlite3.connect(DB_PATH, timeout=10)) as db, db:
        row = db.execute("SELECT url FROM sources WHERE id = ?", (source_id,)).fetchone()
        if not row or not allowed_url(row[0]):
            raise ValueError("Source ID not found or URL is not allowed")
        db.execute("UPDATE sources SET status = ?, reviewed_at = ? WHERE id = ?",
                   (status, datetime.now(timezone.utc).isoformat(), source_id))


def approved_results(query: str) -> list[dict]:
    """Read approvals on each request so cached official searches cannot hide revocation."""
    if not external_allowed(query):
        return []
    terms = search_terms(query)
    rows, seen = [], set()
    for row in sorted(list_sources(), key=lambda row: row["reviewed_at"] or "", reverse=True):
        if row["status"] != "approved" or not allowed_url(row["url"]) or row["url"] in seen:
            continue
        seen.add(row["url"])
        if terms & search_terms(row["title"] + " " + row["content"]):
            rows.append(row)
    rows.sort(key=lambda row: (len(terms & search_terms(row["content"])), row["reviewed_at"]), reverse=True)
    results = []
    for row in rows:
        results.append({key: row[key] for key in
                        ("url", "title", "content", "published_at", "retrieved_at", "reviewed_at")})
        results[-1].update(source="reviewed_external", priority="secondary")
        if len(results) == 2:
            break
    return results


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).with_name(".env"))
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("collect").add_argument("query")
    actions.add_parser("list")
    for action in ("approve", "reject"):
        actions.add_parser(action).add_argument("id", type=int)
    args = parser.parse_args()
    try:
        if args.action == "collect":
            if not external_allowed(args.query):
                parser.error("Collect company background or announcements; keep product claims official-only.")
            print("Saved source IDs for review:", discover(args.query))
        elif args.action == "list":
            print(json.dumps(list_sources(), indent=2, ensure_ascii=True))
        else:
            review(args.id, "approved" if args.action == "approve" else "rejected")
            print("Source", args.id, "approved" if args.action == "approve" else "rejected")
    except Exception:
        parser.exit(1, "Source operation failed. Check the ID, database permissions, or Tavily configuration.\n")
