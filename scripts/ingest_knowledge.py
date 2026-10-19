"""Fetch approved A3i URLs and create reviewable pending knowledge records."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree import ElementTree

import httpx

from app.config import KNOWLEDGE_DIR


BASE_URL = "https://a3i-accel.com"
SITEMAP_URL = BASE_URL + "/sitemap.xml"
OUTPUT_PATH = KNOWLEDGE_DIR / "collection.json"
ALLOWED_HOSTS = {"a3i-accel.com", "www.a3i-accel.com"}


def approved_url(url: str) -> bool:
    parsed = urlsplit(url)
    return (parsed.scheme == "https" and parsed.hostname in ALLOWED_HOSTS
            and not parsed.username and not parsed.password and parsed.port in (None, 443)
            and not parsed.path.startswith(("/api/", "/admin/", "/auth/")))


class SectionParser(HTMLParser):
    """Extract useful visible blocks without adding an HTML parsing dependency."""

    BLOCKS = {"h1", "h2", "h3", "h4", "p", "li", "dt", "dd"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.page_title = ""
        self.heading = "Overview"
        self.sections: list[tuple[str, str]] = []
        self._tag: str | None = None
        self._text: list[str] = []
        self._ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self._ignored += 1
        if not self._ignored and self._tag is None and (tag in self.BLOCKS or tag == "title"):
            self._tag = tag
            self._text = []

    def handle_data(self, data):
        if not self._ignored and self._tag:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self._ignored:
            self._ignored -= 1
            return
        if self._tag != tag:
            return
        text = " ".join(" ".join(self._text).split())
        if tag == "title":
            self.page_title = text
        elif tag.startswith("h") and text:
            self.heading = text
        elif text:
            self.sections.append((self.heading, text))
        self._tag = None
        self._text = []


def sitemap_urls(client: httpx.Client) -> list[str]:
    response = client.get(SITEMAP_URL)
    response.raise_for_status()
    root = ElementTree.fromstring(response.text)
    urls = [element.text.strip() for element in root.iter() if element.tag.endswith("loc") and element.text]
    return list(dict.fromkeys(url for url in urls if approved_url(url)))


def combine_sections(parser: SectionParser) -> list[tuple[str, str]]:
    grouped: list[tuple[str, list[str]]] = []
    for heading, text in parser.sections:
        if grouped and grouped[-1][0] == heading:
            grouped[-1][1].append(text)
        else:
            grouped.append((heading, [text]))
    chunks = []
    for heading, blocks in grouped:
        current = ""
        part = 1
        for block in blocks:
            candidate = (current + "\n" + block).strip()
            if current and len(candidate) > 1800:
                label = heading if part == 1 else f"{heading} (part {part})"
                chunks.append((label, current))
                current, part = block, part + 1
            else:
                current = candidate
        if current:
            label = heading if part == 1 else f"{heading} (part {part})"
            chunks.append((label, current))
    return chunks


def make_record(url: str, title: str, heading: str, content: str, collected_at: str) -> dict:
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    document_id = hashlib.sha256(
        f"{url}\n{heading}\n{content_hash}".encode("utf-8")
    ).hexdigest()[:16]
    return {
        "document_id": document_id,
        "source_url": url,
        "page_title": title or "A3i-Accel",
        "section_heading": heading,
        "content": content,
        "collected_at": collected_at,
        "last_reviewed_at": None,
        "content_hash": content_hash,
        "approval_status": "pending_review",
    }


def read_existing(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {record["document_id"]: record for record in payload.get("records", [])
                if isinstance(record, dict) and isinstance(record.get("document_id"), str)}
    except (OSError, json.JSONDecodeError):
        return {}


def ingest(output: Path = OUTPUT_PATH) -> dict:
    collected_at = datetime.now(timezone.utc).isoformat()
    previous = read_existing(output)
    records = []
    headers = {"User-Agent": "A3i-Accel knowledge updater/1.0"}
    with httpx.Client(headers=headers, timeout=20, follow_redirects=True) as client:
        urls = sitemap_urls(client)
        for url in urls:
            response = client.get(url)
            response.raise_for_status()
            if not approved_url(str(response.url)):
                raise ValueError("A sitemap URL redirected outside the approved A3i domain")
            parser = SectionParser()
            parser.feed(response.text)
            for heading, content in combine_sections(parser):
                if len(content) < 30:
                    continue
                record = make_record(url, parser.page_title, heading, content, collected_at)
                old = previous.get(record["document_id"])
                if old and old.get("approval_status") == "approved":
                    record["approval_status"] = "approved"
                    record["last_reviewed_at"] = old.get("last_reviewed_at")
                records.append(record)
    payload = {
        "schema_version": 1,
        "generated_at": collected_at,
        "source_sitemap": SITEMAP_URL,
        "records": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    result = ingest(args.output)
    pending = sum(record["approval_status"] == "pending_review" for record in result["records"])
    approved = sum(record["approval_status"] == "approved" for record in result["records"])
    print(f"Saved {len(result['records'])} records: {pending} pending review, {approved} approved.")
