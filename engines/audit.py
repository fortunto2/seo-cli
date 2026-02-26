"""Page SEO + GEO audit — check meta tags, OG, schema, AI readiness, speed, keywords, readability."""

import requests
import re
import json
from collections import Counter
from urllib.parse import urlparse, urljoin

import trafilatura
import yake
import textstat


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


def _detect_locale_url(url: str, html: str) -> str | None:
    """Detect locale routing — if root is thin, find the real locale page.

    Checks: hreflang links, meta refresh, common locale paths (/en/, /ru/).
    Returns locale URL if found, None if root page is fine.
    """
    title = _extract_tag(html, "title")
    h1 = _extract_tag(html, "h1")
    desc = _extract_meta(html, "description")
    jsonld = _extract_jsonld(html)

    # Root page has full content (title + JSON-LD) — no locale redirect needed
    if title and jsonld:
        return None

    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    # Check hreflang links for locale URLs
    hreflang_urls = re.findall(
        r'<link\s+[^>]*hreflang="([^"]*)"[^>]*href="([^"]*)"', html, re.I
    )
    if not hreflang_urls:
        hreflang_urls = re.findall(
            r'<link\s+[^>]*href="([^"]*)"[^>]*hreflang="([^"]*)"', html, re.I
        )
        hreflang_urls = [(lang, href) for href, lang in hreflang_urls]

    # Prefer x-default, then en, then first available
    for lang, href in hreflang_urls:
        if lang == "x-default":
            return href if href.startswith("http") else urljoin(base, href)
    for lang, href in hreflang_urls:
        if lang.startswith("en"):
            return href if href.startswith("http") else urljoin(base, href)
    if hreflang_urls:
        href = hreflang_urls[0][1]
        return href if href.startswith("http") else urljoin(base, href)

    # Check meta http-equiv refresh redirect
    refresh = re.search(r'<meta\s+http-equiv="refresh"[^>]*url=([^">\s]+)', html, re.I)
    if refresh:
        target = refresh.group(1).strip("'\"")
        return target if target.startswith("http") else urljoin(base, target)

    # Check common JS redirect patterns
    js_redirect = re.search(r'(?:window\.location|location\.href)\s*=\s*["\']([^"\']+)["\']', html)
    if js_redirect:
        target = js_redirect.group(1)
        return target if target.startswith("http") else urljoin(base, target)

    # Probe common locale paths
    for locale in ("en", "ru"):
        locale_url = f"{base}/{locale}/"
        resp = _fetch(locale_url, timeout=10)
        if resp and resp.status_code == 200:
            locale_title = _extract_tag(resp.text, "title")
            if locale_title and (not title or len(locale_title) > len(title)):
                return locale_url

    return None


def _parse_hreflangs(html: str) -> list[dict]:
    """Parse all hreflang link tags into structured list."""
    results = []
    for m in re.finditer(
        r'<link\s+[^>]*hreflang="([^"]*)"[^>]*href="([^"]*)"', html, re.I
    ):
        results.append({"lang": m.group(1), "href": m.group(2)})
    for m in re.finditer(
        r'<link\s+[^>]*href="([^"]*)"[^>]*hreflang="([^"]*)"', html, re.I
    ):
        if not any(r["lang"] == m.group(2) for r in results):
            results.append({"lang": m.group(2), "href": m.group(1)})
    return results


def audit_url(url: str, skip_speed: bool = False) -> dict:
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

    # ─── Locale Detection ────────────────────────────────────────
    locale_url = _detect_locale_url(url, html)
    if locale_url and locale_url.rstrip("/") != url.rstrip("/"):
        locale_resp = _fetch(locale_url)
        if locale_resp and locale_resp.status_code == 200:
            results["locale_url"] = locale_url
            html = locale_resp.text

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

    # ─── Hreflang / i18n ─────────────────────────────────────────
    hreflangs = _parse_hreflangs(html)
    lang_codes = [h["lang"] for h in hreflangs]

    add("seo", "Hreflang", len(hreflangs) > 0, f"{len(hreflangs)} languages" if hreflangs else "",
        "No hreflang (ok if single language)" if not hreflangs else "")

    if hreflangs:
        # Check x-default exists
        has_x_default = "x-default" in lang_codes
        add("seo", "Hreflang x-default", has_x_default, "",
            "Add hreflang x-default for language fallback" if not has_x_default else "")

        # Check self-referencing — current page URL should be in hreflang hrefs
        audit_url_norm = (locale_url or url).rstrip("/")
        self_ref = any(h["href"].rstrip("/") == audit_url_norm for h in hreflangs)
        add("seo", "Hreflang self-ref", self_ref, "",
            "Current page should be in its own hreflang set" if not self_ref else "")

        # Check all hreflang URLs are absolute
        all_absolute = all(h["href"].startswith("http") for h in hreflangs)
        add("seo", "Hreflang absolute URLs", all_absolute, "",
            "Hreflang hrefs must be absolute URLs" if not all_absolute else "")

    # Check html lang attribute
    html_lang = re.search(r'<html[^>]*\slang="([^"]*)"', html, re.I)
    lang_val = html_lang.group(1) if html_lang else ""
    add("seo", "HTML lang attr", bool(lang_val), lang_val,
        "Add lang attribute to <html> tag" if not lang_val else "")

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

    # ─── Links & Images ────────────────────────────────────────────

    # Broken internal links checker
    all_links = re.findall(r'<a\s[^>]*href="([^"]*)"', html, re.I)
    internal_links = []
    for href in all_links:
        # Skip anchors, mailto, tel, javascript
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        # Resolve relative URLs
        if href.startswith("/") or not href.startswith("http"):
            full = urljoin(url, href)
        else:
            full = href
        # Keep only same-domain links
        link_parsed = urlparse(full)
        if link_parsed.netloc == parsed.netloc:
            internal_links.append(full)

    # Deduplicate and check up to 20 links with HEAD requests
    unique_internal = list(dict.fromkeys(internal_links))[:20]
    broken_links = []
    for link in unique_internal:
        try:
            r = requests.head(link, timeout=5, headers={
                "User-Agent": "Mozilla/5.0 (compatible; SEO-CLI/1.0)"
            }, allow_redirects=True)
            if r.status_code in (404, 500):
                broken_links.append(f"{link} ({r.status_code})")
        except Exception:
            broken_links.append(f"{link} (error)")

    broken_detail = f"{len(broken_links)} broken" if broken_links else "All OK"
    if broken_links:
        broken_detail += ": " + ", ".join(broken_links[:5])
    add("links", "Internal links", not broken_links, broken_detail,
        f"Fix {len(broken_links)} broken internal link(s)" if broken_links else "")

    # Images without alt attribute
    img_tags = re.findall(r'<img\s[^>]*?/?>', html, re.I)
    total_images = len(img_tags)
    missing_alt = 0
    for img in img_tags:
        if 'alt=' not in img.lower():
            missing_alt += 1
        elif re.search(r'alt="\s*"', img, re.I):
            missing_alt += 1
    all_have_alt = missing_alt == 0
    alt_value = f"{missing_alt}/{total_images} missing" if total_images else "No images found"
    add("links", "Image alt tags", all_have_alt, alt_value,
        f"Add alt text to {missing_alt} image(s)" if missing_alt else "")

    # ─── Page Speed (Google PageSpeed Insights API) ──────────────
    results["speed"] = _check_pagespeed(url) if not skip_speed else {}

    # ─── Content Analysis (trafilatura + yake + textstat) ───────
    results["content"] = _analyze_content(html, title, desc, h1)

    return results


# ─── Content Analysis Helpers ────────────────────────────────────────


def _analyze_content(html: str, title: str, desc: str, h1: str) -> dict:
    """Full content analysis: keywords (yake), readability (textstat), density."""
    # Extract clean text via trafilatura (much better than regex)
    body_text = trafilatura.extract(html, include_comments=False, include_tables=True) or ""
    if not body_text:
        return {"keywords": [], "readability": {}, "word_count": 0}

    word_count = len(body_text.split())

    # ── YAKE keyword extraction ──
    # Detect language hint from content
    lang = "en"
    if re.search(r'[а-яА-ЯёЁ]{3,}', body_text):
        lang = "ru"

    kw_extractor = yake.KeywordExtractor(lan=lang, n=3, top=20, dedupLim=0.7)
    yake_kws = kw_extractor.extract_keywords(body_text)
    # yake returns (keyword, score) — lower score = more relevant
    keywords = []
    title_lower = title.lower()
    h1_lower = h1.lower()
    desc_lower = desc.lower()

    for kw, score in yake_kws[:15]:
        kw_lower = kw.lower()
        keywords.append({
            "keyword": kw,
            "score": round(score, 4),
            "in_title": kw_lower in title_lower,
            "in_h1": kw_lower in h1_lower,
            "in_desc": kw_lower in desc_lower,
        })

    # ── Readability (textstat) ──
    readability = {}
    try:
        if lang == "en":
            readability = {
                "flesch_ease": textstat.flesch_reading_ease(body_text),
                "flesch_grade": textstat.flesch_kincaid_grade(body_text),
                "gunning_fog": textstat.gunning_fog(body_text),
                "reading_time_sec": textstat.reading_time(body_text, ms_per_char=14.69),
            }
        else:
            # textstat supports russian for some metrics
            readability = {
                "reading_time_sec": textstat.reading_time(body_text, ms_per_char=14.69),
            }
    except Exception:
        pass

    # ── Word frequency (simple density) ──
    words = re.findall(r'[a-zA-Zа-яА-ЯёЁ]{3,}', body_text.lower())
    total = len(words)
    word_freq = Counter(words).most_common(10)
    density = [{"word": w, "count": c, "density": round(c / total * 100, 1)} for w, c in word_freq] if total else []

    return {
        "keywords": keywords,
        "readability": readability,
        "word_count": word_count,
        "density": density,
        "lang": lang,
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
              "tech": "Technical", "files": "Files", "geo": "GEO (AI Optimization)",
              "links": "Links & Images"}

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
