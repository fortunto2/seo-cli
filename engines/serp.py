"""Google SERP via SearXNG (primary) + CSE API + scraping fallback + competitor SEO extraction."""

import re
import requests
from urllib.parse import urlparse, quote_plus


SEARXNG_URL = "http://localhost:8013"


# ─── SearXNG Tavily Adapter (primary) ───────────────────────────────────

def searxng_search(query: str, num: int = 10, engines: str = "google") -> list[dict]:
    """Search via local SearXNG instance (Tavily-compatible API).

    Returns list of {url, title, snippet, position}.
    """
    try:
        resp = requests.post(
            f"{SEARXNG_URL}/search",
            json={"query": query, "max_results": num, "engines": engines},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return []

    results = []
    seen = set()
    for item in data.get("results", []):
        url = item.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        results.append({
            "url": url,
            "title": item.get("title", ""),
            "snippet": item.get("content", ""),
            "position": len(results) + 1,
        })
        if len(results) >= num:
            break

    return results


# ─── Google Custom Search JSON API ──────────────────────────────────────

def google_search_api(query: str, api_key: str, cx: str, lang: str = "en", num: int = 10) -> list[dict]:
    """Search via Google Custom Search JSON API (100 free queries/day)."""
    results = []
    for start in range(1, num + 1, 10):
        try:
            resp = requests.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": api_key, "cx": cx, "q": query,
                    "hl": lang, "num": min(10, num - len(results)), "start": start,
                },
                timeout=15,
            )
            if resp.status_code in (429, 403):
                break
            resp.raise_for_status()
            for item in resp.json().get("items", []):
                results.append({
                    "url": item["link"],
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "position": len(results) + 1,
                })
                if len(results) >= num:
                    break
        except Exception:
            break
        if len(results) >= num:
            break
    return results[:num]


# ─── Unified search (SearXNG → CSE API → scrape) ────────────────────────

def google_search(query: str, lang: str = "en", num: int = 10,
                  api_key: str = "", cx: str = "") -> list[dict]:
    """Search Google — tries SearXNG first, then CSE API, then scraping."""
    # 1. SearXNG (local, fast, no rate limits)
    results = searxng_search(query, num=num, engines="google")
    if results:
        return results

    # 2. CSE API (if configured)
    if api_key and cx:
        results = google_search_api(query, api_key, cx, lang, num)
        if results:
            return results

    # 3. Direct scraping (fragile, last resort)
    return _google_search_scrape(query, lang, num)


def _google_search_scrape(query: str, lang: str = "en", num: int = 10) -> list[dict]:
    """Scrape Google HTML search results (fragile, may get blocked)."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        resp = requests.get(
            f"https://www.google.com/search?q={quote_plus(query)}&hl={lang}&num={num}&gl=us",
            headers=headers, timeout=15,
        )
        if resp.status_code != 200:
            return []
    except Exception:
        return []

    html = resp.text
    results = []
    blocks = re.findall(r'<div class="[^"]*?g[^"]*?"[^>]*>.*?</div>\s*</div>\s*</div>', html, re.S)
    if not blocks:
        blocks = [html]

    seen = set()
    for block in blocks:
        links = re.findall(r'<a[^>]+href="(/url\?q=([^&"]+)|https?://[^"]+)"[^>]*>', block)
        for full_match, cleaned in links:
            href = cleaned if cleaned else full_match
            if href.startswith("/url?q="):
                href = href[7:]
            parsed = urlparse(href)
            if not parsed.netloc or "google." in parsed.netloc or href in seen:
                continue
            h3 = re.search(r'<h3[^>]*>(.*?)</h3>', block, re.S)
            title = re.sub(r'<[^>]+>', '', h3.group(1)).strip() if h3 else ""
            seen.add(href)
            results.append({"url": href, "title": title, "snippet": "", "position": len(results) + 1})
            break
        if len(results) >= num:
            break
    return results[:num]


# ─── Competitor SEO extraction ───────────────────────────────────────────

def extract_page_seo(url: str) -> dict:
    """Fetch URL and extract SEO data: title, desc, h1, schema types, word count, og:image."""
    from engines.audit import _fetch, _extract_meta, _extract_tag, _extract_jsonld

    resp = _fetch(url)
    if not resp or resp.status_code != 200:
        return {"url": url, "error": True}

    html = resp.text

    title = _extract_tag(html, "title")
    desc = _extract_meta(html, "description")
    h1 = _extract_tag(html, "h1")
    og_image = _extract_meta(html, "og:image")

    jsonld = _extract_jsonld(html)
    schema_types = [d.get("@type", "?") for d in jsonld]

    import trafilatura
    body = trafilatura.extract(html, include_comments=False) or ""
    word_count = len(body.split())

    has_faq = any(t in ("FAQPage", "HowTo") for t in schema_types)

    return {
        "url": url,
        "domain": urlparse(url).netloc,
        "title": title,
        "description": desc,
        "h1": h1,
        "og_image": bool(og_image),
        "schema_types": schema_types,
        "has_faq": has_faq,
        "word_count": word_count,
        "error": False,
    }
