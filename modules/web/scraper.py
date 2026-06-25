"""Web scraping with httpx + BeautifulSoup, optional Playwright for JS pages.

Default path is a fast static fetch (httpx) parsed with BeautifulSoup. If
`wait_for_js=True` and Playwright + a browser are installed, the page is
rendered first so client-side content is captured; otherwise it falls back to
the static fetch and notes that JS was not rendered.
"""

from __future__ import annotations

import re

import httpx
from bs4 import BeautifulSoup

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/120.0 Safari/537.36")
MAX_CHARS = 10_000


def scrape_webpage(url: str, extract_mode: str = "text",
                   wait_for_js: bool = False) -> dict:
    note = None
    if wait_for_js:
        html = _render_with_playwright(url)
        if html is None:
            note = "Playwright not available; returned static HTML (JS not rendered)."
            html = _fetch_static(url)
    else:
        html = _fetch_static(url)

    if isinstance(html, dict):  # an error dict propagated up
        return html

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    extractors = {
        "text": _extract_text,
        "markdown": _extract_markdown,
        "links": _extract_links,
        "tables": _extract_tables,
        "images": _extract_images,
    }
    fn = extractors.get(extract_mode, _extract_text)
    data = fn(soup, url)

    out = {"url": url, "mode": extract_mode, "data": data}
    if note:
        out["note"] = note
    return out


def _fetch_static(url: str):
    try:
        with httpx.Client(follow_redirects=True, timeout=20.0,
                          headers={"User-Agent": USER_AGENT}) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.text
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP {e.response.status_code} fetching {url}"}
    except Exception as e:
        return {"error": f"Failed to fetch {url}: {e}"}


def _render_with_playwright(url: str):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, wait_until="networkidle", timeout=30_000)
            html = page.content()
            browser.close()
            return html
    except Exception:
        return None


def _clip(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + "\n...[truncated]"


def _extract_text(soup: BeautifulSoup, url: str) -> str:
    return _clip(soup.get_text("\n", strip=True))


def _extract_markdown(soup: BeautifulSoup, url: str) -> str:
    parts: list[str] = []
    body = soup.body or soup
    for el in body.find_all(["h1", "h2", "h3", "h4", "p", "li", "a"]):
        txt = el.get_text(" ", strip=True)
        if not txt:
            continue
        if el.name in ("h1", "h2", "h3", "h4"):
            parts.append("#" * int(el.name[1]) + " " + txt)
        elif el.name == "li":
            parts.append("- " + txt)
        elif el.name == "a" and el.get("href"):
            parts.append(f"[{txt}]({el['href']})")
        else:
            parts.append(txt)
    return _clip("\n\n".join(parts))


def _extract_links(soup: BeautifulSoup, url: str) -> list[dict]:
    links = []
    for a in soup.find_all("a", href=True):
        links.append({"text": a.get_text(" ", strip=True)[:120], "href": a["href"]})
        if len(links) >= 300:
            break
    return links


def _extract_tables(soup: BeautifulSoup, url: str) -> list[list[list[str]]]:
    tables = []
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(" ", strip=True)
                     for c in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)
        if rows:
            tables.append(rows)
        if len(tables) >= 20:
            break
    return tables


def _extract_images(soup: BeautifulSoup, url: str) -> list[dict]:
    imgs = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if src:
            imgs.append({"src": src, "alt": img.get("alt", "")[:120]})
        if len(imgs) >= 200:
            break
    return imgs
