"""Read the public HTML fragments used by the official A3i website."""

import json
import logging
import re
from html.parser import HTMLParser
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)
SOURCES_PATH = Path(__file__).with_name("website_sources.json")
STOPWORDS = set(
    "a3i accel a3i-accel ai what wha is are the a an of for to in and or this that it its "
    "website does do how can i me my you your we our with about will all from "
    "which who provide information explain tell more have has".split()
)
ALIASES = {
    "ceo": "founder", "cofounder": "founder", "co-founder": "founder",
    "founders": "founder", "co-founders": "founder", "coo": "founder",
    "established": "founded", "establish": "founded", "located": "location",
    "headquarters": "location", "headquartered": "location", "based": "location",
    "prices": "pricing", "price": "pricing", "cost": "pricing", "costs": "pricing",
    "quote": "pricing", "quotes": "pricing", "fees": "pricing",
    "products": "product", "agents": "agent", "apps": "app", "ants": "ant",
    "integrations": "integration", "services": "service", "businesses": "business",
    "industries": "industry", "industry-specific": "industry", "solutions": "solution",
    "customized": "custom", "customization": "custom",
}


def search_terms(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.casefold())
    return {ALIASES.get(word, word) for word in words if word not in STOPWORDS}


class PageText(HTMLParser):
    """Keep text blocks and headings; exclude scripts, styles and forms."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "form"}:
            self.hidden += 1
        if not self.hidden and tag in {"p", "li", "div", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")
            if tag.startswith("h"):
                self.parts.append("#" * int(tag[1]) + " ")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "form"}:
            self.hidden = max(0, self.hidden - 1)
        if not self.hidden and tag in {"p", "li", "div", "h1", "h2", "h3", "h4"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

    def text(self):
        text = "\n".join(
            line for part in "".join(self.parts).splitlines()
            if (line := " ".join(part.split()))
        )
        return re.sub(r"(?m)^(#{1,4})[ \t]*\n[ \t]*", r"\1 ", text)


def website_results(query: str) -> list[dict]:
    """Fetch up to two relevant pages from a fixed public-source catalog."""
    try:
        sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("Website source catalog is unavailable")
        return []
    terms = search_terms(query)
    ranked = sorted(
        sources,
        key=lambda page: len(terms & search_terms(page["keywords"])),
        reverse=True,
    )
    selected = [page for page in ranked if terms & search_terms(page["keywords"])][:2]
    if not selected:
        selected = [sources[0]]
    results = []
    with httpx.Client(timeout=8, follow_redirects=False) as client:
        for page in selected:
            # Only fetch fixed fragment IDs, never a URL supplied by a visitor or model.
            page_id = page["id"]
            if not re.fullmatch(r"[a-z0-9-]+", page_id):
                continue
            url = "https://a3i-accel.com/" + (
                "" if page_id == "home" else f"partials/{page_id}.html"
            )
            try:
                response = client.get(url)
                response.raise_for_status()
                if len(response.content) > 2_000_000:
                    continue
                parser = PageText()
                parser.feed(response.text)
                content = parser.text()
                if content:
                    results.append({"url": url, "title": page["title"], "content": content})
                    logger.info("Read public A3i page: %s", page_id)
            except (httpx.HTTPError, ValueError):
                logger.warning("Could not read public A3i page: %s", page_id)
    return results
