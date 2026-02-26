#!/usr/bin/env python3
"""
SEO CLI — Unified search engine management for all your sites.

Usage:
    python cli.py status          # Show all sites, engines, sitemaps
    python cli.py submit          # Submit all sitemaps to all engines
    python cli.py ping            # IndexNow ping all sitemap URLs
    python cli.py add             # Add all sites to all engines
    python cli.py analytics       # Search analytics from Google & Yandex
    python cli.py inspect URL     # Check indexing status of a URL (Google)
"""

import sys
import json
import yaml
from pathlib import Path
from datetime import date, timedelta

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(f"ERROR: {CONFIG_PATH} not found.")
        print(f"Copy config.example.yaml to config.yaml and fill in credentials.")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def _has_google(cfg: dict) -> bool:
    sa = cfg.get("google", {}).get("service_account_file", "")
    return bool(sa) and Path(sa).exists()


def _has_bing(cfg: dict) -> bool:
    return bool(cfg.get("bing", {}).get("api_key"))


def _has_yandex(cfg: dict) -> bool:
    return bool(cfg.get("yandex", {}).get("oauth_token"))


def _has_indexnow(cfg: dict) -> bool:
    return bool(cfg.get("indexnow", {}).get("key"))


def _resolve_gsc_url(sa_file: str, site_url: str) -> str | None:
    """Find the actual GSC property URL for a site (sc-domain: or https://)."""
    from engines.google_sc import list_sites
    from urllib.parse import urlparse

    domain = urlparse(site_url).netloc
    gsc_sites = list_sites(sa_file)

    # Try exact matches first, then domain property
    candidates = [
        site_url + "/",
        site_url,
        f"sc-domain:{domain}",
    ]
    gsc_urls = {s["siteUrl"] for s in gsc_sites}
    for c in candidates:
        if c in gsc_urls:
            return c
    return None


# ─── Commands ────────────────────────────────────────────────────────────


def cmd_status(cfg: dict):
    """Show registered sites in each engine."""
    sites = cfg.get("sites", [])
    print(f"\n{'='*60}")
    print(f"  SEO CLI — {len(sites)} sites configured")
    print(f"{'='*60}")

    for s in sites:
        print(f"\n  {s['name']:20s} {s['url']}")

    # Google
    print(f"\n--- Google Search Console ---")
    if _has_google(cfg):
        try:
            from engines.google_sc import list_sites
            gsites = list_sites(cfg["google"]["service_account_file"])
            for s in gsites:
                print(f"  {s.get('siteUrl', '?'):40s} level={s.get('permissionLevel', '?')}")
            if not gsites:
                print("  (no sites — add service account email as Owner in Search Console)")
        except Exception as e:
            print(f"  ERROR: {e}")
    else:
        print("  (not configured)")

    # Bing
    print(f"\n--- Bing Webmaster Tools ---")
    if _has_bing(cfg):
        try:
            from engines.bing import list_sites
            bsites = list_sites(cfg["bing"]["api_key"])
            for s in (bsites if isinstance(bsites, list) else []):
                print(f"  {s.get('Url', '?')}")
            if not bsites:
                print("  (no sites)")
        except Exception as e:
            print(f"  ERROR: {e}")
    else:
        print("  (not configured)")

    # Yandex
    print(f"\n--- Yandex Webmaster ---")
    if _has_yandex(cfg):
        try:
            from engines.yandex import get_user_id, list_sites
            uid = get_user_id(cfg["yandex"]["oauth_token"])
            yhosts = list_sites(cfg["yandex"]["oauth_token"], uid)
            for h in yhosts:
                verified = h.get("verified", False)
                tag = "verified" if verified else "NOT verified"
                print(f"  {h.get('unicode_host_url', '?'):40s} [{tag}]")
            if not yhosts:
                print("  (no sites)")
        except Exception as e:
            print(f"  ERROR: {e}")
    else:
        print("  (not configured)")

    # IndexNow
    print(f"\n--- IndexNow ---")
    if _has_indexnow(cfg):
        key = cfg["indexnow"]["key"]
        print(f"  Key: {key[:8]}...")
        for s in sites:
            print(f"  Key file needed: {s['url']}/{key}.txt")
    else:
        print("  (not configured)")

    print()


def cmd_add(cfg: dict):
    """Add all sites to all engines."""
    sites = cfg.get("sites", [])

    if _has_google(cfg):
        from engines.google_sc import add_site
        sa = cfg["google"]["service_account_file"]
        print("\n--- Adding to Google Search Console ---")
        for s in sites:
            try:
                add_site(sa, s["url"] + "/")
                print(f"  + {s['name']:20s} {s['url']}")
            except Exception as e:
                print(f"  x {s['name']:20s} {e}")

    if _has_bing(cfg):
        from engines.bing import add_site
        print("\n--- Adding to Bing Webmaster Tools ---")
        for s in sites:
            try:
                add_site(cfg["bing"]["api_key"], s["url"])
                print(f"  + {s['name']:20s} {s['url']}")
            except Exception as e:
                print(f"  x {s['name']:20s} {e}")

    if _has_yandex(cfg):
        from engines.yandex import get_user_id, add_site
        token = cfg["yandex"]["oauth_token"]
        uid = get_user_id(token)
        print("\n--- Adding to Yandex Webmaster ---")
        for s in sites:
            try:
                result = add_site(token, uid, s["url"])
                print(f"  + {s['name']:20s} host_id={result.get('host_id', '?')}")
            except Exception as e:
                print(f"  x {s['name']:20s} {e}")

    print()


def cmd_submit(cfg: dict):
    """Submit sitemaps to all engines."""
    sites = cfg.get("sites", [])

    if _has_google(cfg):
        from engines.google_sc import submit_sitemap
        sa = cfg["google"]["service_account_file"]
        print("\n--- Submitting sitemaps to Google ---")
        for s in sites:
            gsc_url = _resolve_gsc_url(sa, s["url"])
            if not gsc_url:
                print(f"  -  {s['name']:20s} (not in GSC)")
                continue
            try:
                submit_sitemap(sa, gsc_url, s["sitemap"])
                print(f"  OK {s['name']:20s} {s['sitemap']}")
            except Exception as e:
                print(f"  x  {s['name']:20s} {e}")

    if _has_bing(cfg):
        from engines.bing import submit_sitemap
        print("\n--- Submitting sitemaps to Bing ---")
        for s in sites:
            try:
                submit_sitemap(cfg["bing"]["api_key"], s["url"], s["sitemap"])
                print(f"  OK {s['name']:20s} {s['sitemap']}")
            except Exception as e:
                print(f"  x  {s['name']:20s} {e}")

    if _has_yandex(cfg):
        from engines.yandex import get_user_id, get_host_id, submit_sitemap
        token = cfg["yandex"]["oauth_token"]
        uid = get_user_id(token)
        print("\n--- Submitting sitemaps to Yandex ---")
        for s in sites:
            try:
                hid = get_host_id(token, uid, s["url"])
                if not hid:
                    print(f"  x  {s['name']:20s} site not found in Yandex (run 'add' first)")
                    continue
                submit_sitemap(token, uid, hid, s["sitemap"])
                print(f"  OK {s['name']:20s} {s['sitemap']}")
            except Exception as e:
                print(f"  x  {s['name']:20s} {e}")

    print()


def cmd_ping(cfg: dict):
    """Submit all sitemap URLs via IndexNow (Bing + Yandex instant)."""
    if not _has_indexnow(cfg):
        print("IndexNow not configured. Set 'indexnow.key' in config.yaml")
        return

    from engines.indexnow import submit_sitemap_urls
    key = cfg["indexnow"]["key"]
    sites = cfg.get("sites", [])

    print("\n--- IndexNow: submitting sitemap URLs ---")
    for s in sites:
        try:
            result = submit_sitemap_urls(key, s["url"], s["sitemap"])
            if result["ok"]:
                print(f"  OK {s['name']:20s} {result.get('urls_count', '?')} URLs submitted")
            else:
                print(f"  x  {s['name']:20s} HTTP {result['status']} — {result.get('error', '')}")
        except Exception as e:
            print(f"  x  {s['name']:20s} {e}")

    print()


def cmd_analytics(cfg: dict):
    """Show search analytics from Google and Yandex (last 28 days)."""
    sites = cfg.get("sites", [])
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=28)).isoformat()

    if _has_google(cfg):
        from engines.google_sc import get_search_analytics
        sa = cfg["google"]["service_account_file"]
        print(f"\n--- Google Search Analytics ({start} — {end}) ---")
        for s in sites:
            gsc_url = _resolve_gsc_url(sa, s["url"])
            if not gsc_url:
                print(f"  - {s['name']:20s} (not in GSC)")
                continue
            try:
                data = get_search_analytics(sa, gsc_url, start, end)
                rows = data.get("rows", [])
                total_clicks = sum(r.get("clicks", 0) for r in rows)
                total_impressions = sum(r.get("impressions", 0) for r in rows)
                print(f"\n  {s['name']} — {total_clicks} clicks, {total_impressions} impressions")
                for r in rows[:5]:
                    q = r["keys"][0]
                    print(f"    {q:40s} clicks={r['clicks']:4d}  imp={r['impressions']:6d}  pos={r['position']:.1f}")
            except Exception as e:
                print(f"  x {s['name']:20s} {e}")

    if _has_yandex(cfg):
        from engines.yandex import get_user_id, get_host_id, get_search_queries
        token = cfg["yandex"]["oauth_token"]
        uid = get_user_id(token)
        print(f"\n--- Yandex Search Queries ({start} — {end}) ---")
        for s in sites:
            try:
                hid = get_host_id(token, uid, s["url"])
                if not hid:
                    print(f"  x {s['name']:20s} not found in Yandex")
                    continue
                data = get_search_queries(token, uid, hid, start, end)
                queries = data.get("queries", [])
                print(f"\n  {s['name']} — {len(queries)} queries")
                for q in queries[:5]:
                    print(f"    {q.get('query_text', '?'):40s} clicks={q.get('count', 0)}")
            except Exception as e:
                print(f"  x {s['name']:20s} {e}")

    print()


def cmd_inspect(cfg: dict, url: str):
    """Check indexing status of a specific URL (Google only)."""
    if not _has_google(cfg):
        print("Google not configured.")
        return

    from engines.google_sc import inspect_url
    sa = cfg["google"]["service_account_file"]

    # Find which site this URL belongs to
    site_url = None
    for s in cfg.get("sites", []):
        if url.startswith(s["url"]):
            site_url = _resolve_gsc_url(sa, s["url"])
            break

    if not site_url:
        print(f"URL {url} does not match any configured site (or not in GSC).")
        return

    print(f"\n--- Google URL Inspection ---")
    print(f"  URL: {url}")
    try:
        result = inspect_url(sa, site_url, url)
        idx = result.get("indexStatusResult", {})
        print(f"  Coverage: {idx.get('coverageState', '?')}")
        print(f"  Robots:   {idx.get('robotsTxtState', '?')}")
        print(f"  Indexing:  {idx.get('indexingState', '?')}")
        print(f"  Last crawl: {idx.get('lastCrawlTime', '?')}")
        print(f"  Page fetch: {idx.get('pageFetchState', '?')}")
    except Exception as e:
        print(f"  ERROR: {e}")
    print()


# ─── Main ────────────────────────────────────────────────────────────────


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]
    cfg = load_config()

    commands = {
        "status": lambda: cmd_status(cfg),
        "add": lambda: cmd_add(cfg),
        "submit": lambda: cmd_submit(cfg),
        "ping": lambda: cmd_ping(cfg),
        "analytics": lambda: cmd_analytics(cfg),
        "inspect": lambda: cmd_inspect(cfg, sys.argv[2] if len(sys.argv) > 2 else ""),
    }

    if cmd in commands:
        commands[cmd]()
    else:
        print(f"Unknown command: {cmd}")
        print(f"Available: {', '.join(commands.keys())}")
        sys.exit(1)


if __name__ == "__main__":
    main()
