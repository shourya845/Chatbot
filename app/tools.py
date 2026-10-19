"""Search approved A3i content without exposing configurable domains to the model."""

import os
import re
import time
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
from threading import Lock
from urllib.parse import urlsplit

from langchain_core.tools import ToolException, tool
from langchain_tavily import TavilySearch
from pydantic import BaseModel, ConfigDict, Field

from .config import load_environment
from .knowledge import search_approved_knowledge
from .privacy import external_services_allowed
from .telemetry import record_search

load_environment()
CACHE_TTL = 15 * 60
MAX_CACHE_ENTRIES = 128
OFFICIAL_HOSTS = {"a3i-accel.com", "www.a3i-accel.com"}
search_cache: OrderedDict = OrderedDict()
cache_lock = Lock()


class SearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    query: str = Field(min_length=1, max_length=1000)


def relevant_excerpt(text: str, query: str) -> str:
    """Prefer matching page sections, instead of cutting off the page introduction."""
    stopwords = set("what are is does how the a an do about and or at of".split())
    terms = set(re.findall(r"\w+", query.casefold())) - stopwords
    sections = re.split(r"(?m)(?=^#{1,4}\s)", text)

    def score(section):
        heading = section.split("\n", 1)[0] if section.startswith("#") else ""
        return (3 * len(terms & set(re.findall(r"\w+", heading.casefold())))
                + len(terms & set(re.findall(r"\w+", section.casefold()))))
    selected = sorted(enumerate(sections), key=lambda item: score(item[1]), reverse=True)[:3]
    return "\n\n".join(section[:1200] for _, section in sorted(selected))[:3600]


def _search_query(query: str) -> str:
    """Add company context to a visitor's search terms."""
    if not re.search(r"\ba3i\b", query, re.I):
        query = "A3i Accel " + query
    return query


def _cached_result(key: str) -> dict | None:
    with cache_lock:
        cached = search_cache.get(key)
        if cached and time.monotonic() - cached[0] < CACHE_TTL:
            search_cache.move_to_end(key)
            return deepcopy(cached[1])
        search_cache.pop(key, None)
    return None


def _cache_result(key: str, result: dict) -> None:
    """Store successful searches in a bounded least-recently-used cache."""
    with cache_lock:
        search_cache[key] = (time.monotonic(), deepcopy(result))
        search_cache.move_to_end(key)
        while len(search_cache) > MAX_CACHE_ENTRIES:
            search_cache.popitem(last=False)


def _official_results(response: dict, query: str) -> list[dict]:
    """Keep content from valid HTTPS URLs on the official A3i domain."""
    results = []
    retrieved_at = datetime.now(timezone.utc).isoformat()
    for item in response.get("results", [])[:3]:
        url = str(item.get("url", ""))
        parsed = urlsplit(url)
        valid_url = (
            parsed.scheme == "https"
            and parsed.hostname in OFFICIAL_HOSTS
            and not parsed.username
            and not parsed.password
            and parsed.port in (None, 443)
        )
        if not valid_url:
            continue
        raw_content = str(item.get("raw_content") or item.get("content", ""))
        content = relevant_excerpt(raw_content, query)
        if content.strip():
            results.append(
                {
                    "url": url,
                    "content": content,
                    "source": "tavily",
                    "retrieved_at": retrieved_at,
                }
            )
    return results


def _search_tavily(query: str) -> dict:
    search = TavilySearch(
        max_results=3,
        topic="general",
        search_depth="basic",
        include_domains=["a3i-accel.com"],
        include_raw_content=True,
    )
    response = search.invoke({"query": query, "include_domains": ["a3i-accel.com"]})
    if isinstance(response, str) and "no search results" in response.lower():
        return {"results": []}
    if not isinstance(response, dict):
        return {"error": "Tavily returned an unexpected response. Please retry."}
    if response.get("error"):
        return search_failure(response["error"])
    return {"results": _official_results(response, query)}


@tool(args_schema=SearchQuery)
def search_a3i_web(query: str) -> dict:
    """Search approved local A3i knowledge first, then the official website when
    cloud access is allowed: company, team, industries, products, services,
    resources, careers, contact, responsible AI, pricing and policies.
    """
    started_at = time.perf_counter()
    cache_hit = None
    retrieval_source = "approved_local"
    try:
        approved_results = search_approved_knowledge(query)
        if approved_results:
            return {"results": approved_results}
        if not external_services_allowed():
            return {"results": []}
        retrieval_source = "tavily"
        cache_hit = False
        if not os.getenv("TAVILY_API_KEY"):
            return {"error": "Tavily search is not configured."}
        query = _search_query(query)
        key = " ".join(re.sub(r"[^\w\s]", " ", query.casefold()).split())
        cached = _cached_result(key)
        if cached is not None:
            cache_hit = True
            return cached
        try:
            result = _search_tavily(query)
            if result.get("results"):
                _cache_result(key, result)
            return result
        except ToolException as error:
            if "no search results" in str(error).lower():
                return {"results": []}
            return search_failure(error)
        except Exception as error:
            return search_failure(error)
    finally:
        record_search(cache_hit=cache_hit, started_at=started_at, source=retrieval_source)


def search_failure(error) -> dict:
    """Classify failures without returning provider text or credentials."""
    status = getattr(getattr(error, "response", None), "status_code", None)
    description = str(error).lower()
    if status in (401, 403) or "unauthorized" in description or "invalid api key" in description:
        message = "Tavily rejected the API key. Check TAVILY_API_KEY in .env."
    elif status == 432 or "credit" in description or "quota" in description:
        message = "Tavily search credits are exhausted. Check your Tavily account."
    elif status == 429:
        message = "Tavily rate limit reached. Please retry shortly."
    elif "timeout" in type(error).__name__.lower() or "timed out" in description:
        message = "Tavily search timed out. Please retry."
    else:
        message = "Tavily search is temporarily unavailable. Please retry."
    return {"error": message}
