"""Page SEO + GEO audit — check meta tags, OG, schema, AI readiness, speed, keywords."""

import requests
import re
import json
from collections import Counter
from urllib.parse import urlparse, urljoin


def _fetch(url: str, timeout: int = 15) -> requests.Response | None:
    try:
        return requests.get(url, timeout=timeout, headers={
            "User-Agent": "Mozilla/5.0 (compatible; SEO-CLI/1.0)"
        })
    except Exception:
        return None


def _extract_meta(html: str, name: str) -> str:
    """Extract meta tag content by name or property."""
    for attr in ("name", "property"):
        m = re.search(rf'<meta\s+{attr}="{name}"\s+content="([^"]*)"', html, re.I)
        if m:
            return m.group(1)
        m = re.search(rf'<meta\s+content="([^"]*)"\s+{attr}="{name}"', html, re.I)
        if m:
            return m.group(1)
    return ""


def _extract_tag(html: str, tag: str) -> str:
    """Extract first occurrence of a tag's inner text."""
    m = re.search(rf'<{tag}[^>]*>(.*?)</{tag}>', html, re.I | re.S)
    return m.group(1).strip() if m else ""


def _extract_jsonld(html: str) -> list[dict]:
    """Extract all JSON-LD blocks."""
    results = []
    for m in re.finditer(r'<script\s+type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(m.group(1))
            if isinstance(data, list):
                results.extend(data)
            else:
                results.append(data)
        except json.JSONDecodeError:
            pass
    return results


def _check_exists(url: str) -> tuple[bool, int]:
    """Check if URL exists. Returns (exists, status_code)."""
    resp = _fetch(url)
    if resp is None:
        return False, 0
    return resp.status_code == 200, resp.status_code


def audit_url(url: str) -> dict:
    """Full SEO + GEO audit of a URL."""
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    results = {"url": url, "checks": [], "score": 0, "max_score": 0}
    checks = results["checks"]

    def add(category: str, name: str, ok: bool, value: str = "", hint: str = ""):
        results["max_score"] += 1
        if ok:
            results["score"] += 1
        checks.append({"category": category, "name": name, "ok": ok, "value": value, "hint": hint})

    # Fetch page
    resp = _fetch(url)
    if not resp or resp.status_code != 200:
        add("page", "Accessible", False, f"HTTP {resp.status_code if resp else 'timeout'}")
        return results

    html = resp.text

    # ─── SEO Basics ──────────────────────────────────────────────
    title = _extract_tag(html, "title")
    add("seo", "Title", bool(title), title[:60] if title else "",
        "Missing <title>" if not title else ("Too long (>60)" if len(title) > 60 else ""))

    desc = _extract_meta(html, "description")
    add("seo", "Meta description", bool(desc), desc[:80] if desc else "",
        "Missing meta description" if not desc else ("Too long (>160)" if len(desc) > 160 else ""))

    h1 = _extract_tag(html, "h1")
    add("seo", "H1", bool(h1), h1[:60] if h1 else "", "Missing H1 tag" if not h1 else "")

    canonical = ""
    m = re.search(r'<link\s+rel="canonical"\s+href="([^"]*)"', html, re.I)
    if not m:
        m = re.search(r'<link\s+href="([^"]*)"\s+rel="canonical"', html, re.I)
    if m:
        canonical = m.group(1)
    add("seo", "Canonical", bool(canonical), canonical, "Missing canonical URL" if not canonical else "")

    viewport = _extract_meta(html, "viewport")
    add("seo", "Viewport", bool(viewport), "", "Missing viewport meta (mobile)" if not viewport else "")

    # Hreflang
    hreflangs = re.findall(r'<link\s+[^>]*hreflang="([^"]*)"', html, re.I)
    add("seo", "Hreflang", len(hreflangs) > 0, f"{len(hreflangs)} languages" if hreflangs else "",
        "No hreflang (ok if single language)" if not hreflangs else "")

    # ─── Open Graph ──────────────────────────────────────────────
    og_title = _extract_meta(html, "og:title")
    add("og", "og:title", bool(og_title), og_title[:50] if og_title else "")

    og_desc = _extract_meta(html, "og:description")
    add("og", "og:description", bool(og_desc), og_desc[:50] if og_desc else "")

    og_image = _extract_meta(html, "og:image")
    add("og", "og:image", bool(og_image), og_image[:60] if og_image else "", "No social preview image" if not og_image else "")

    og_url = _extract_meta(html, "og:url")
    add("og", "og:url", bool(og_url), og_url)

    og_type = _extract_meta(html, "og:type")
    add("og", "og:type", bool(og_type), og_type)

    # Twitter card
    tw_card = _extract_meta(html, "twitter:card")
    add("og", "twitter:card", bool(tw_card), tw_card)

    # ─── Structured Data ─────────────────────────────────────────
    jsonld = _extract_jsonld(html)
    types = [d.get("@type", "?") for d in jsonld]
    add("schema", "JSON-LD", len(jsonld) > 0, ", ".join(types) if types else "",
        "No structured data" if not jsonld else "")

    has_org = any(t in ("Organization", "WebSite") for t in types)
    add("schema", "Organization/WebSite", has_org, "",
        "Add Organization or WebSite schema" if not has_org else "")

    # ─── Technical ───────────────────────────────────────────────
    robots_meta = _extract_meta(html, "robots")
    noindex = "noindex" in robots_meta.lower() if robots_meta else False
    add("tech", "Robots meta", not noindex, robots_meta if robots_meta else "default (index,follow)",
        "Page is noindex!" if noindex else "")

    https = parsed.scheme == "https"
    add("tech", "HTTPS", https, "", "Not HTTPS!" if not https else "")

    # ─── Files (site-level) ──────────────────────────────────────
    robots_ok, _ = _check_exists(f"{base}/robots.txt")
    add("files", "robots.txt", robots_ok)

    sitemap_ok, _ = _check_exists(f"{base}/sitemap.xml")
    add("files", "sitemap.xml", sitemap_ok)

    favicon = bool(re.search(r'<link\s+[^>]*rel="icon"', html, re.I))
    if not favicon:
        fav_ok, _ = _check_exists(f"{base}/favicon.ico")
        favicon = fav_ok
    add("files", "Favicon", favicon)

    # ─── GEO (AI/LLM Optimization) ──────────────────────────────
    llms_ok, _ = _check_exists(f"{base}/llms.txt")
    add("geo", "llms.txt", llms_ok, f"{base}/llms.txt",
        "Add llms.txt for AI agent discovery (llmstxt.org)" if not llms_ok else "")

    llms_full_ok, _ = _check_exists(f"{base}/llms-full.txt")
    add("geo", "llms-full.txt", llms_full_ok, "",
        "Optional: detailed version for LLMs" if not llms_full_ok else "")

    # Check if robots.txt allows AI bots
    robots_resp = _fetch(f"{base}/robots.txt")
    ai_bots_blocked = False
    if robots_resp and robots_resp.status_code == 200:
        robots_text = robots_resp.text.lower()
        blocked_bots = []
        for bot in ["gptbot", "chatgpt-user", "claude-web", "anthropic", "perplexitybot", "cohere-ai"]:
            if bot in robots_text and "disallow" in robots_text:
                blocked_bots.append(bot)
        if blocked_bots:
            ai_bots_blocked = True
        add("geo", "AI bots allowed", not ai_bots_blocked,
            f"Blocked: {', '.join(blocked_bots)}" if blocked_bots else "All AI bots allowed",
            "Some AI bots blocked in robots.txt" if ai_bots_blocked else "")
    else:
        add("geo", "AI bots allowed", True, "No robots.txt = all allowed")

    # Check markdown endpoint (common patterns)
    md_found = False
    for md_path in ["/llms.txt", f"{parsed.path}.md" if parsed.path != "/" else "/index.md"]:
        md_resp = _fetch(f"{base}{md_path}")
        if md_resp and md_resp.status_code == 200 and len(md_resp.text) > 100:
            md_found = True
            break
    add("geo", "Markdown content", md_found, "",
        "Serve content as .md for LLM consumption" if not md_found else "")

    # Schema for AI (FAQ, HowTo, Article — structured content AI can parse)
    ai_schemas = [t for t in types if t in ("FAQPage", "HowTo", "Article", "BlogPosting", "Product", "SoftwareApplication")]
    add("geo", "Rich schema", len(ai_schemas) > 0, ", ".join(ai_schemas) if ai_schemas else "",
        "Add FAQ/Article/Product schema for AI citations" if not ai_schemas else "")

    # ─── Page Speed (Google PageSpeed Insights API) ──────────────
    results["speed"] = _check_pagespeed(url)

    # ─── Keywords ────────────────────────────────────────────────
    results["keywords"] = _extract_keywords(html, title, desc, h1)

    return results


# ─── Helpers ─────────────────────────────────────────────────────────


STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "this", "that", "are", "was",
    "be", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "can", "not", "no", "so", "if",
    "as", "than", "then", "just", "also", "how", "all", "each", "every",
    "your", "our", "their", "its", "my", "his", "her", "we", "you", "they",
    "i", "me", "he", "she", "us", "them", "who", "what", "which", "when",
    "where", "why", "more", "most", "some", "any", "new", "get", "make",
    "about", "up", "out", "one", "two", "been", "into", "over", "only",
    # Russian
    "и", "в", "на", "с", "для", "что", "это", "как", "по", "из", "не",
    "от", "за", "все", "или", "но", "его", "она", "они", "мы", "вы",
    "он", "её", "их", "вас", "нас", "так", "уже", "при", "до", "без",
}


def _extract_text(html: str) -> str:
    """Strip tags, scripts, styles from HTML to get visible text."""
    text = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.S | re.I)
    text = re.sub(r'<style[^>]*>.*?</style>', ' ', text, flags=re.S | re.I)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&\w+;', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _tokenize(text: str) -> list[str]:
    """Extract lowercase words, filter stop words and short tokens."""
    words = re.findall(r'[a-zA-Zа-яА-ЯёЁ]{3,}', text.lower())
    return [w for w in words if w not in STOP_WORDS]


def _extract_keywords(html: str, title: str, desc: str, h1: str) -> dict:
    """Analyze page keywords: density, title/h1/desc presence."""
    body_text = _extract_text(html)
    words = _tokenize(body_text)

    if not words:
        return {"top_words": [], "top_bigrams": [], "in_title": [], "in_h1": [], "in_desc": []}

    # Single words
    word_counts = Counter(words)
    total = len(words)
    top_words = []
    for word, count in word_counts.most_common(15):
        top_words.append({
            "word": word, "count": count,
            "density": round(count / total * 100, 1),
        })

    # Bigrams (2-word phrases)
    bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
    bigram_counts = Counter(bigrams)
    top_bigrams = []
    for bg, count in bigram_counts.most_common(10):
        if count >= 2:
            top_bigrams.append({"phrase": bg, "count": count})

    # Check top keywords presence in title, h1, description
    title_lower = title.lower()
    h1_lower = h1.lower()
    desc_lower = desc.lower()

    top_kw = [w["word"] for w in top_words[:10]]
    in_title = [w for w in top_kw if w in title_lower]
    in_h1 = [w for w in top_kw if w in h1_lower]
    in_desc = [w for w in top_kw if w in desc_lower]

    return {
        "top_words": top_words,
        "top_bigrams": top_bigrams,
        "in_title": in_title,
        "in_h1": in_h1,
        "in_desc": in_desc,
        "total_words": total,
    }


def _check_pagespeed(url: str) -> dict:
    """Get Core Web Vitals via Google PageSpeed Insights API (free, no key)."""
    result = {"mobile": {}, "desktop": {}}

    for strategy in ("mobile", "desktop"):
        try:
            api_url = (
                f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
                f"?url={requests.utils.quote(url)}&strategy={strategy}"
                f"&category=performance&category=seo&category=best-practices"
            )
            resp = requests.get(api_url, timeout=60)
            if resp.status_code != 200:
                continue
            data = resp.json()

            # Lighthouse scores
            cats = data.get("lighthouseResult", {}).get("categories", {})
            scores = {}
            for cat_id, cat_data in cats.items():
                scores[cat_id] = int((cat_data.get("score") or 0) * 100)

            # Core Web Vitals from field data
            crux = data.get("loadingExperience", {}).get("metrics", {})
            cwv = {}
            metric_map = {
                "LARGEST_CONTENTFUL_PAINT_MS": "LCP",
                "CUMULATIVE_LAYOUT_SHIFT_SCORE": "CLS",
                "INTERACTION_TO_NEXT_PAINT": "INP",
                "FIRST_CONTENTFUL_PAINT_MS": "FCP",
            }
            for key, label in metric_map.items():
                if key in crux:
                    val = crux[key].get("percentile", 0)
                    cat = crux[key].get("category", "?")
                    cwv[label] = {"value": val, "rating": cat}

            result[strategy] = {"scores": scores, "cwv": cwv}
        except Exception:
            pass

    return result


def format_report(audit: dict) -> str:
    """Format audit results as readable text."""
    lines = []
    score = audit["score"]
    max_score = audit["max_score"]
    pct = int(score / max_score * 100) if max_score else 0

    lines.append(f"\n{'='*65}")
    lines.append(f"  SEO+GEO AUDIT — {audit['url']}")
    lines.append(f"  Score: {score}/{max_score} ({pct}%)")
    lines.append(f"{'='*65}")

    categories = {}
    for c in audit["checks"]:
        cat = c["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(c)

    labels = {"seo": "SEO Basics", "og": "Open Graph / Social", "schema": "Structured Data",
              "tech": "Technical", "files": "Files", "geo": "GEO (AI Optimization)"}

    for cat, items in categories.items():
        lines.append(f"\n  --- {labels.get(cat, cat)} ---")
        for c in items:
            icon = "+" if c["ok"] else "x"
            val = f"  {c['value']}" if c["value"] else ""
            hint = f"  ({c['hint']})" if c["hint"] and not c["ok"] else ""
            lines.append(f"  {icon} {c['name']:25s}{val}{hint}")

    # Action items
    fails = [c for c in audit["checks"] if not c["ok"] and c["hint"]]
    if fails:
        lines.append(f"\n  --- Action Items ---")
        for i, c in enumerate(fails, 1):
            lines.append(f"  {i}. {c['hint']}")

    lines.append("")
    return "\n".join(lines)
