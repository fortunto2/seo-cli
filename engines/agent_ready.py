"""Agent-readiness audit: what an AI agent can discover, read and act on.

A site now has two audiences. Search engines want a sitemap and clean HTML; agents want to
know what may be crawled, where the machine-readable version is, and what they can call.

THE SOFT-404 GUARD IS THE POINT OF THIS FILE.

Every check here is "does this well-known path exist", and a great many sites answer 200 with
their home page for any URL at all. A checker that trusts the status code then reports a
perfect score for a site that has none of it — measured on a real site, twelve of twelve
"passed" while every single response was the same HTML page.

So the first request made is for a path invented on the spot. If that answers 200, the site
is a soft-404 and no existence check on it can be believed; the audit says so loudly and
verifies content rather than status for everything after.

That is also worth fixing on its own account: soft 404s waste crawl budget, and Google
treats them as a quality problem.
"""

import json
import random
import re
import string

import requests

TIMEOUT = 12
UA = "seo-cli agent-audit (+https://github.com/fortunto2)"

# Agents whose rules a site should have an opinion about — allow or deny, but not silence.
NOTABLE_AGENTS = ["GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "CCBot", "Bytespider"]


def _get(url: str, accept: str | None = None) -> requests.Response | None:
    headers = {"User-Agent": UA}
    if accept:
        headers["Accept"] = accept
    try:
        return requests.get(url, headers=headers, timeout=TIMEOUT, allow_redirects=True)
    except requests.RequestException:
        return None


def _is_soft_404(base: str) -> bool:
    """Ask for a path that cannot exist. A 200 means every other 200 here is meaningless."""
    nonce = "".join(random.choices(string.ascii_lowercase + string.digits, k=18))
    resp = _get(f"{base}/.well-known/seo-cli-probe-{nonce}")
    return resp is not None and resp.status_code == 200


def _looks_like_html(resp: requests.Response) -> bool:
    ctype = resp.headers.get("content-type", "").lower()
    return "html" in ctype or resp.text.lstrip()[:15].lower().startswith("<!doctype html")


def _exists(base: str, path: str, *, soft404: bool, expect: str = "any") -> tuple[bool, str]:
    """True only when the response is real.

    `expect="json"` requires the body to parse; `expect="text"` requires non-empty content that
    is not the site's HTML. On a soft-404 site an HTML body is exactly what an absent file
    returns, so HTML is treated as absence rather than as a pass.
    """
    resp = _get(f"{base}{path}")
    if resp is None:
        return False, "unreachable"
    if resp.status_code != 200:
        return False, str(resp.status_code)

    if expect == "json":
        try:
            json.loads(resp.text)
        except ValueError:
            return False, "200 but not JSON"
        return True, "ok"

    if _looks_like_html(resp):
        # Genuine HTML at a .well-known path is not what any of these specs describe.
        return False, "200 but HTML" + (" (soft 404)" if soft404 else "")
    if not resp.text.strip():
        return False, "200 but empty"
    return True, "ok"


def _sample_page(base: str) -> str | None:
    """A real content URL from the sitemap, so negotiation is tested where content lives."""
    for candidate in ("/sitemap-index.xml", "/sitemap.xml"):
        resp = _get(f"{base}{candidate}")
        if resp is None or resp.status_code != 200:
            continue
        locs = re.findall(r"<loc>([^<]+)</loc>", resp.text)
        # An index points at more sitemaps; follow one hop.
        if locs and locs[0].endswith(".xml"):
            inner = _get(locs[0])
            locs = re.findall(r"<loc>([^<]+)</loc>", inner.text) if inner is not None else []
        pages = [u for u in locs if u.rstrip("/") != base.rstrip("/") and not u.endswith(".xml")]
        if pages:
            return pages[-1]
    return None


def audit_agent_readiness(url: str) -> dict:
    """Returns the same shape as engines.audit.audit_url: url, score, max_score, checks[]."""
    base = url.rstrip("/")
    checks: list[dict] = []

    def add(category: str, name: str, ok: bool, value: str = "", hint: str = "") -> None:
        checks.append(
            {"category": category, "name": name, "ok": ok, "value": value, "hint": hint}
        )

    soft404 = _is_soft_404(base)

    # ─── Honesty of the server itself ────────────────────────────
    add(
        "sanity",
        "Distinct 404s",
        not soft404,
        "every unknown path answers 200" if soft404 else "unknown paths 404 correctly",
        "Return a real 404 for unknown paths — otherwise agents, crawlers and this audit all "
        "see files that are not there, and Google counts it as a quality problem",
    )

    # ─── Discoverability ─────────────────────────────────────────
    robots = _get(f"{base}/robots.txt")
    robots_txt = robots.text if robots is not None and robots.status_code == 200 else ""
    robots_ok = bool(robots_txt) and not (robots is not None and _looks_like_html(robots))
    add("discovery", "robots.txt", robots_ok, "found" if robots_ok else "missing",
        "Add robots.txt — it is the first thing every agent fetches")

    has_sitemap_line = bool(re.search(r"^\s*sitemap:", robots_txt, re.I | re.M))
    add("discovery", "Sitemap in robots.txt", has_sitemap_line,
        "declared" if has_sitemap_line else "not declared",
        "Add a Sitemap: line to robots.txt")

    sitemap_ok = False
    for candidate in ("/sitemap-index.xml", "/sitemap.xml", "/sitemap_index.xml"):
        resp = _get(f"{base}{candidate}")
        if resp is not None and resp.status_code == 200 and "<" in resp.text[:200]:
            sitemap_ok = True
            break
    add("discovery", "Sitemap reachable", sitemap_ok, "found" if sitemap_ok else "missing",
        "Publish a sitemap")

    llms_ok, llms_why = _exists(base, "/llms.txt", soft404=soft404, expect="text")
    add("discovery", "llms.txt", llms_ok, "found" if llms_ok else llms_why,
        "Add /llms.txt — a short plain-text map of the site written for language models")

    # ─── What agents may do ──────────────────────────────────────
    named = [a for a in NOTABLE_AGENTS if re.search(re.escape(a), robots_txt, re.I)]
    add("policy", "AI bot rules", bool(named), ", ".join(named) if named else "none named",
        "Say allow or deny for GPTBot, ClaudeBot and PerplexityBot — silence is a decision "
        "made for you")

    signals = "content-signal" in robots_txt.lower()
    add("policy", "Content Signals", signals, "present" if signals else "absent",
        "Optional: Content-Signals in robots.txt states search/ai-train/ai-input intent")

    # ─── Machine-readable content ────────────────────────────────
    # Probe the home page AND a real content page. A site whose root is an index often has no
    # markdown source for it while every article does, and calling that "no negotiation" is the
    # same false negative the soft-404 guard exists to prevent — in the other direction.
    md_ok, md_where, md_ctype = False, "", "not offered"
    for label, probe in (("home", f"{base}/"), ("a page", _sample_page(base))):
        if probe is None:
            continue
        md = _get(probe, accept="text/markdown")
        if md is None:
            continue
        ctype = md.headers.get("content-type", "").lower()
        if "markdown" in ctype:
            md_ok, md_where, md_ctype = True, label, ctype
            break
        md_ctype = ctype or "?"
    add("content", "Markdown negotiation", md_ok,
        f"{md_ctype} (on {md_where})" if md_ok else md_ctype,
        "Optional: serve text/markdown when asked, so agents skip HTML parsing")

    # ─── Capability discovery ────────────────────────────────────
    for path, label, expect in (
        ("/.well-known/mcp.json", "MCP server card", "json"),
        ("/.well-known/agent-card.json", "A2A agent card", "json"),
        ("/.well-known/api-catalog", "API catalog", "any"),
        ("/.well-known/oauth-protected-resource", "OAuth resource", "json"),
    ):
        ok, why = _exists(base, path, soft404=soft404, expect=expect)
        add("capability", label, ok, "found" if ok else why, f"Optional: publish {path}")

    score = sum(1 for c in checks if c["ok"])
    return {
        "url": url,
        "soft_404": soft404,
        "score": score,
        "max_score": len(checks),
        "checks": checks,
    }


def format_report(audit: dict) -> str:
    lines: list[str] = []
    score, mx = audit["score"], audit["max_score"]
    pct = int(score / mx * 100) if mx else 0

    lines.append(f"\n{'='*65}")
    lines.append(f"  AGENT READINESS — {audit['url']}")
    lines.append(f"  Score: {score}/{mx} ({pct}%)")
    lines.append(f"{'='*65}")

    if audit["soft_404"]:
        lines.append("")
        lines.append("  !! This site answers 200 for paths that do not exist.")
        lines.append("     Existence checks below verify content, not status codes.")

    labels = {
        "sanity": "Server honesty",
        "discovery": "Discoverability",
        "policy": "What agents may do",
        "content": "Machine-readable content",
        "capability": "Capability discovery (optional)",
    }
    grouped: dict[str, list[dict]] = {}
    for c in audit["checks"]:
        grouped.setdefault(c["category"], []).append(c)

    for cat, items in grouped.items():
        lines.append(f"\n  --- {labels.get(cat, cat)} ---")
        for c in items:
            icon = "+" if c["ok"] else "x"
            val = f"  {c['value']}" if c["value"] else ""
            lines.append(f"  {icon} {c['name']:24s}{val}")

    todo = [c for c in audit["checks"] if not c["ok"] and c["hint"]]
    if todo:
        lines.append("\n  --- To fix ---")
        for c in todo:
            lines.append(f"  * {c['name']}: {c['hint']}")

    return "\n".join(lines)
