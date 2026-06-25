"""DuckDuckGo web search.

Uses the `ddgs` package (the current name of `duckduckgo-search`), falling
back to the old import path if only the legacy package is installed.
"""

from __future__ import annotations

try:  # current package
    from ddgs import DDGS
except ImportError:  # legacy package name
    from duckduckgo_search import DDGS  # type: ignore


def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Return a list of {title, url, snippet} dicts for the query."""
    results: list[dict] = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append(
                {
                    "title": r.get("title", ""),
                    "url": r.get("href") or r.get("url", ""),
                    "snippet": r.get("body") or r.get("snippet", ""),
                }
            )
    return results
