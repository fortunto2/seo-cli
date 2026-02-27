#!/usr/bin/env python3
"""SEO CLI — Unified search engine management for all your sites."""

import sys
import yaml
import click
from pathlib import Path
from datetime import date, timedelta
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

CONFIG_PATH = Path(__file__).parent / "config.yaml"
console = Console()


def _trunc(text: str, width: int = 45) -> str:
    """Truncate text with ellipsis if too long."""
    if len(text) <= width:
        return text
    return text[:width - 1] + "\u2026"


def _fmt_duration(seconds: float) -> str:
    """Format duration: <60s as '42s', >=60s as '1.5m'."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    return f"{seconds / 60:.1f}m"


def load_config(required: bool = True) -> dict:
    if not CONFIG_PATH.exists():
        if required:
            console.print("[red]ERROR:[/] config.yaml not found.")
            console.print("Copy config.example.yaml to config.yaml and fill in credentials.")
            sys.exit(1)
        return {}
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


def _has_cloudflare(cfg: dict) -> bool:
    return bool(cfg.get("cloudflare", {}).get("api_token"))


_gsc_cache: set[str] | None = None


def _get_gsc_urls(sa_file: str) -> set[str]:
    global _gsc_cache
    if _gsc_cache is None:
        from engines.google_sc import list_sites
        sites = list_sites(sa_file)
        _gsc_cache = {s["siteUrl"] for s in sites}
    return _gsc_cache


def _resolve_gsc_url(sa_file: str, site_url: str) -> str | None:
    from urllib.parse import urlparse
    domain = urlparse(site_url).netloc
    gsc_urls = _get_gsc_urls(sa_file)
    for c in [site_url + "/", site_url, f"sc-domain:{domain}"]:
        if c in gsc_urls:
            return c
    return None


# ─── CLI ─────────────────────────────────────────────────────────────────


@click.group()
def cli():
    """SEO CLI — Unified search engine management for all your sites."""
    pass


@cli.command()
def status():
    """Show all sites — indexing, analytics, traffic at a glance."""
    cfg = load_config()
    sites = cfg.get("sites", [])
    from urllib.parse import urlparse

    google_ok = _has_google(cfg)
    cf_ok = _has_cloudflare(cfg)
    sa = cfg.get("google", {}).get("service_account_file")

    # Pre-fetch GSC sites
    gsc_urls = set()
    if google_ok:
        gsc_urls = _get_gsc_urls(sa)

    # Pre-fetch CF zones
    zone_map = {}
    zone_plans = {}
    if cf_ok:
        try:
            from engines.cloudflare import list_zones
            zones = list_zones(cfg["cloudflare"]["api_token"])
            zone_map = {z["name"]: z["id"] for z in zones}
            zone_plans = {z["name"]: z.get("plan", "Free") for z in zones}
        except Exception:
            pass

    # Pre-fetch GA overview for sites that have it
    ga_data = {}
    if google_ok:
        try:
            from engines.ga import get_overview
            for s in sites:
                pid = s.get("ga_property_id")
                if pid:
                    hostname = urlparse(s["url"]).hostname
                    try:
                        ov = get_overview(sa, pid, days=7, hostname=hostname)
                        if ov:
                            ga_data[s["name"]] = ov
                    except Exception:
                        pass
        except ImportError:
            pass

    # Build table
    table = Table(title=f"SEO CLI — {len(sites)} sites", box=box.ROUNDED)
    table.add_column("Site", style="bold", min_width=14)
    table.add_column("GSC", justify="center")
    table.add_column("GA 7d", justify="right")
    table.add_column("CF", justify="center")
    table.add_column("Hosting", justify="center", style="dim")
    table.add_column("IndexNow", justify="center")

    indexnow_ok = _has_indexnow(cfg)

    for s in sites:
        domain = urlparse(s["url"]).hostname or ""

        # GSC status
        in_gsc = any(x in gsc_urls for x in [s["url"] + "/", s["url"], f"sc-domain:{domain}"])
        gsc_str = "[green]OK[/]" if in_gsc else "[dim]-[/]"

        # GA 7-day sessions
        ga_ov = ga_data.get(s["name"])
        if ga_ov:
            sess = ga_ov["sessions"]
            users = ga_ov["users"]
            ga_str = f"{users:,}u/{sess:,}s"
        elif s.get("ga_property_id"):
            ga_str = "[dim]0[/]"
        else:
            ga_str = "[dim]-[/]"

        # CF zone
        cf_zone = zone_map.get(domain)
        if cf_zone:
            plan = zone_plans.get(domain, "")
            plan_short = "Ent" if "enterprise" in plan.lower() else ("Pro" if "pro" in plan.lower() else "Free")
            cf_str = f"[green]{plan_short}[/]"
        else:
            cf_str = "[dim]-[/]"

        # Hosting
        hosting = s.get("hosting", "-")

        # IndexNow
        inow_str = "[green]OK[/]" if indexnow_ok else "[dim]-[/]"

        table.add_row(s["name"], gsc_str, ga_str, cf_str, hosting, inow_str)

    console.print(table)

    # Legend
    console.print("  [dim]GSC=Google Search Console | GA 7d=users/sessions last 7 days | CF=Cloudflare plan[/]\n")


@cli.command()
@click.option("--days", default=28, help="Analytics period in days")
def analytics(days):
    """Search analytics (Google + Yandex)."""
    cfg = load_config()
    sites = cfg.get("sites", [])
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=days)).isoformat()

    if _has_google(cfg):
        from engines.google_sc import get_search_analytics
        sa = cfg["google"]["service_account_file"]
        console.print(f"\n[bold]Google Search Analytics[/] ({start} — {end})\n")

        for s in sites:
            gsc_url = _resolve_gsc_url(sa, s["url"])
            if not gsc_url:
                console.print(f"  [dim]{s['name']:20s} not in GSC[/]")
                continue
            try:
                data = get_search_analytics(sa, gsc_url, start, end)
                rows = data.get("rows", [])
                total_clicks = sum(r.get("clicks", 0) for r in rows)
                total_impressions = sum(r.get("impressions", 0) for r in rows)

                table = Table(title=f"{s['name']} — {total_clicks:,} clicks, {total_impressions:,} impressions", box=box.SIMPLE)
                table.add_column("Query")
                table.add_column("Clicks", justify="right", style="green")
                table.add_column("Impressions", justify="right")
                table.add_column("CTR", justify="right")
                table.add_column("Position", justify="right", style="yellow")

                for r in sorted(rows, key=lambda x: x["clicks"], reverse=True)[:10]:
                    ctr = r.get("ctr", 0) * 100
                    table.add_row(
                        _trunc(r["keys"][0], 50),
                        f"{r['clicks']:,}", f"{r['impressions']:,}",
                        f"{ctr:.1f}%", f"{r['position']:.1f}",
                    )

                console.print(table)
                console.print()
            except Exception as e:
                console.print(f"  [red]x[/] {s['name']:20s} {e}")

    if _has_yandex(cfg):
        from engines.yandex import get_user_id, get_host_id, get_search_queries
        token = cfg["yandex"]["oauth_token"]
        uid = get_user_id(token)
        console.print(f"\n[bold]Yandex Search Queries[/] ({start} — {end})\n")
        for s in sites:
            try:
                hid = get_host_id(token, uid, s["url"])
                if not hid:
                    continue
                data = get_search_queries(token, uid, hid, start, end)
                queries = data.get("queries", [])
                console.print(f"  {s['name']} — {len(queries)} queries")
                for q in queries[:5]:
                    console.print(f"    {q.get('query_text', '?'):40s} clicks={q.get('count', 0)}")
            except Exception as e:
                console.print(f"  [red]x[/] {s['name']:20s} {e}")


@cli.command()
@click.argument("url")
def inspect(url):
    """Check indexing status of a URL (Google)."""
    cfg = load_config()
    if not _has_google(cfg):
        console.print("[red]Google not configured.[/]")
        return

    from engines.google_sc import inspect_url
    sa = cfg["google"]["service_account_file"]

    site_url = None
    for s in cfg.get("sites", []):
        if url.startswith(s["url"]):
            site_url = _resolve_gsc_url(sa, s["url"])
            break

    if not site_url:
        console.print(f"[red]URL {url} does not match any configured site.[/]")
        return

    try:
        result = inspect_url(sa, site_url, url)
        idx = result.get("indexStatusResult", {})
        coverage = idx.get("coverageState", "?")
        color = "green" if "indexed" in coverage.lower() else "red"

        table = Table(title=f"URL Inspection — {url}", box=box.ROUNDED)
        table.add_column("Property", style="bold")
        table.add_column("Value")
        table.add_row("Coverage", f"[{color}]{coverage}[/]")
        table.add_row("Robots", idx.get("robotsTxtState", "?"))
        table.add_row("Indexing", idx.get("indexingState", "?"))
        table.add_row("Last crawl", idx.get("lastCrawlTime", "?"))
        table.add_row("Page fetch", idx.get("pageFetchState", "?"))
        console.print(table)
    except Exception as e:
        console.print(f"[red]ERROR:[/] {e}")


@cli.command()
def submit():
    """Submit sitemaps to Google + Bing + Yandex."""
    cfg = load_config()
    sites = cfg.get("sites", [])

    if _has_google(cfg):
        from engines.google_sc import submit_sitemap
        sa = cfg["google"]["service_account_file"]
        console.print("\n[bold]Submitting sitemaps to Google[/]")
        for s in sites:
            gsc_url = _resolve_gsc_url(sa, s["url"])
            if not gsc_url:
                console.print(f"  [dim]- {s['name']:20s} not in GSC[/]")
                continue
            try:
                submit_sitemap(sa, gsc_url, s["sitemap"])
                console.print(f"  [green]+[/] {s['name']:20s} {s['sitemap']}")
            except Exception as e:
                console.print(f"  [red]x[/] {s['name']:20s} {e}")

    if _has_bing(cfg):
        from engines.bing import submit_sitemap
        console.print("\n[bold]Submitting sitemaps to Bing[/]")
        for s in sites:
            try:
                submit_sitemap(cfg["bing"]["api_key"], s["url"], s["sitemap"])
                console.print(f"  [green]+[/] {s['name']:20s} {s['sitemap']}")
            except Exception as e:
                console.print(f"  [red]x[/] {s['name']:20s} {e}")

    if _has_yandex(cfg):
        from engines.yandex import get_user_id, get_host_id, submit_sitemap
        token = cfg["yandex"]["oauth_token"]
        uid = get_user_id(token)
        console.print("\n[bold]Submitting sitemaps to Yandex[/]")
        for s in sites:
            try:
                hid = get_host_id(token, uid, s["url"])
                if not hid:
                    console.print(f"  [red]x[/] {s['name']:20s} not found (run 'add' first)")
                    continue
                submit_sitemap(token, uid, hid, s["sitemap"])
                console.print(f"  [green]+[/] {s['name']:20s} {s['sitemap']}")
            except Exception as e:
                console.print(f"  [red]x[/] {s['name']:20s} {e}")


@cli.command()
def ping():
    """IndexNow ping all sitemap URLs (Bing + Yandex + Naver + Seznam)."""
    cfg = load_config()
    if not _has_indexnow(cfg):
        console.print("[red]IndexNow not configured.[/] Set 'indexnow.key' in config.yaml")
        return

    from engines.indexnow import submit_sitemap_urls
    key = cfg["indexnow"]["key"]
    sites = cfg.get("sites", [])

    console.print("\n[bold]IndexNow: submitting sitemap URLs[/]")
    for s in sites:
        try:
            result = submit_sitemap_urls(key, s["url"], s["sitemap"])
            if result["ok"]:
                console.print(f"  [green]+[/] {s['name']:20s} {result.get('urls_count', '?')} URLs")
            else:
                console.print(f"  [red]x[/] {s['name']:20s} HTTP {result['status']}")
        except Exception as e:
            console.print(f"  [red]x[/] {s['name']:20s} {e}")


@cli.command()
def add():
    """Register all sites in all engines."""
    cfg = load_config()
    sites = cfg.get("sites", [])

    if _has_google(cfg):
        from engines.google_sc import add_site
        sa = cfg["google"]["service_account_file"]
        console.print("\n[bold]Adding to Google Search Console[/]")
        for s in sites:
            try:
                add_site(sa, s["url"] + "/")
                console.print(f"  [green]+[/] {s['name']:20s} {s['url']}")
            except Exception as e:
                console.print(f"  [red]x[/] {s['name']:20s} {e}")

    if _has_bing(cfg):
        from engines.bing import add_site
        console.print("\n[bold]Adding to Bing Webmaster Tools[/]")
        for s in sites:
            try:
                add_site(cfg["bing"]["api_key"], s["url"])
                console.print(f"  [green]+[/] {s['name']:20s} {s['url']}")
            except Exception as e:
                console.print(f"  [red]x[/] {s['name']:20s} {e}")

    if _has_yandex(cfg):
        from engines.yandex import get_user_id, add_site
        token = cfg["yandex"]["oauth_token"]
        uid = get_user_id(token)
        console.print("\n[bold]Adding to Yandex Webmaster[/]")
        for s in sites:
            try:
                result = add_site(token, uid, s["url"])
                console.print(f"  [green]+[/] {s['name']:20s} host_id={result.get('host_id', '?')}")
            except Exception as e:
                console.print(f"  [red]x[/] {s['name']:20s} {e}")


@cli.command()
@click.argument("url")
def reindex(url):
    """Instant reindexing of a URL (Google Indexing API + IndexNow)."""
    cfg = load_config()

    if _has_google(cfg):
        from engines.google_indexing import publish_url
        sa = cfg["google"]["service_account_file"]
        try:
            publish_url(sa, url)
            console.print(f"  [green]+[/] Google Indexing API — {url}")
        except Exception as e:
            console.print(f"  [red]x[/] Google Indexing API — {e}")

    if _has_indexnow(cfg):
        from engines.indexnow import submit_urls
        key = cfg["indexnow"]["key"]
        site_url = None
        for s in cfg.get("sites", []):
            if url.startswith(s["url"]):
                site_url = s["url"]
                break
        if site_url:
            try:
                result = submit_urls(key, site_url, [url])
                if result["ok"]:
                    console.print(f"  [green]+[/] IndexNow — {url}")
                else:
                    console.print(f"  [red]x[/] IndexNow — HTTP {result['status']}")
            except Exception as e:
                console.print(f"  [red]x[/] IndexNow — {e}")


def _fmt_delta_pct(current: float, previous: float) -> str:
    """Format a percentage delta with color: green for growth, red for decline."""
    if previous == 0:
        return "[dim]--[/]"
    pct = (current - previous) / previous * 100
    sign = "+" if pct >= 0 else ""
    color = "green" if pct >= 0 else "red"
    return f"[{color}]{sign}{pct:.0f}%[/]"


def _fmt_delta_pos(current: float, previous: float) -> str:
    """Format position delta with color: green if position improved (decreased), red if worse."""
    delta = current - previous
    if abs(delta) < 0.05:
        return "[dim]0.0[/]"
    sign = "+" if delta > 0 else ""
    # Lower position number = better, so negative delta = improvement = green
    color = "green" if delta < 0 else "red"
    return f"[{color}]{sign}{delta:.1f}[/]"


@cli.command()
def report():
    """Full SEO report across all sites."""
    cfg = load_config()
    sites = cfg.get("sites", [])

    # Current period: last 28 days
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=28)).isoformat()

    # Previous period: 28 days before the current period
    prev_end = (date.today() - timedelta(days=28)).isoformat()
    prev_start = (date.today() - timedelta(days=56)).isoformat()

    console.print(Panel(
        f"SEO REPORT — {start} to {end}  (vs {prev_start} to {prev_end})",
        style="bold blue",
    ))

    total_clicks = 0
    total_impressions = 0
    prev_total_clicks = 0
    prev_total_impressions = 0
    all_opportunities = []

    if _has_google(cfg):
        from engines.google_sc import get_search_analytics, list_sitemaps
        sa = cfg["google"]["service_account_file"]

        for s in sites:
            gsc_url = _resolve_gsc_url(sa, s["url"])
            name = s["name"]

            if not gsc_url:
                console.print(f"\n  [dim]{name:20s} not in GSC[/]")
                continue

            try:
                # Fetch current period
                data = get_search_analytics(sa, gsc_url, start, end)
                rows = data.get("rows", [])
                clicks = sum(r.get("clicks", 0) for r in rows)
                impressions = sum(r.get("impressions", 0) for r in rows)
                total_clicks += clicks
                total_impressions += impressions
                avg_pos = sum(r["position"] * r["impressions"] for r in rows) / max(impressions, 1) if rows else 0

                # Fetch previous period
                prev_data = get_search_analytics(sa, gsc_url, prev_start, prev_end)
                prev_rows = prev_data.get("rows", [])
                prev_clicks = sum(r.get("clicks", 0) for r in prev_rows)
                prev_impressions = sum(r.get("impressions", 0) for r in prev_rows)
                prev_total_clicks += prev_clicks
                prev_total_impressions += prev_impressions
                prev_avg_pos = sum(r["position"] * r["impressions"] for r in prev_rows) / max(prev_impressions, 1) if prev_rows else 0

                # Format deltas
                clicks_delta = _fmt_delta_pct(clicks, prev_clicks)
                imp_delta = _fmt_delta_pct(impressions, prev_impressions)
                pos_delta = _fmt_delta_pos(avg_pos, prev_avg_pos)

                color = "green" if clicks > 0 else "dim"
                console.print(
                    f"\n  [{color}]{name}[/] — [bold]{clicks:,}[/] clicks ({clicks_delta})"
                    f" | {impressions:,} imp ({imp_delta})"
                    f" | avg pos {avg_pos:.1f} ({pos_delta})"
                )

                if rows:
                    for r in sorted(rows, key=lambda x: x["clicks"], reverse=True)[:3]:
                        console.print(f"    {r['keys'][0]:35s} clicks={r['clicks']:3d}  pos={r['position']:.1f}")

                for r in rows:
                    if r["impressions"] >= 50 and r["clicks"] / max(r["impressions"], 1) < 0.02:
                        all_opportunities.append({
                            "site": name, "query": r["keys"][0],
                            "impressions": r["impressions"], "clicks": r["clicks"],
                            "position": r["position"],
                        })
            except Exception as e:
                console.print(f"\n  [red]{name}[/] — error: {e}")

            try:
                sitemaps = list_sitemaps(sa, gsc_url)
                for sm in sitemaps:
                    errors = sm.get("errors", 0)
                    warnings = sm.get("warnings", 0)
                    if errors or warnings:
                        console.print(f"    [yellow]Sitemap:[/] {errors} errors, {warnings} warnings")
                if not sitemaps:
                    console.print(f"    [yellow]Sitemap:[/] not submitted")
            except Exception:
                pass

    # IndexNow check
    if _has_indexnow(cfg):
        import requests
        key = cfg["indexnow"]["key"]
        console.print(f"\n  [bold]IndexNow key status[/]")
        for s in sites:
            try:
                resp = requests.get(f"{s['url']}/{key}.txt", timeout=10)
                if resp.status_code == 200 and key in resp.text:
                    console.print(f"    [green]+[/] {s['name']}")
                else:
                    console.print(f"    [red]x[/] {s['name']} (HTTP {resp.status_code})")
            except Exception:
                console.print(f"    [red]x[/] {s['name']} (unreachable)")

    # Totals with period-over-period comparison
    clicks_vs = _fmt_delta_pct(total_clicks, prev_total_clicks)
    imp_vs = _fmt_delta_pct(total_impressions, prev_total_impressions)
    console.print(Panel(
        f"TOTALS: [bold green]{total_clicks:,}[/] clicks ({clicks_vs} vs prev)"
        f" | [bold]{total_impressions:,}[/] impressions ({imp_vs} vs prev)",
        style="blue",
    ))

    if all_opportunities:
        table = Table(title="Low-CTR Opportunities", box=box.SIMPLE)
        table.add_column("Site")
        table.add_column("Query")
        table.add_column("Impressions", justify="right")
        table.add_column("CTR", justify="right", style="red")
        table.add_column("Position", justify="right")
        for opp in sorted(all_opportunities, key=lambda x: x["impressions"], reverse=True)[:10]:
            ctr = opp["clicks"] / max(opp["impressions"], 1) * 100
            table.add_row(opp["site"], opp["query"], f"{opp['impressions']:,}", f"{ctr:.1f}%", f"{opp['position']:.1f}")
        console.print(table)


@cli.command()
@click.argument("url", required=False)
def audit(url):
    """SEO + GEO page audit. Audits all sites if no URL given.

    Works without config.yaml when a URL is provided directly:
        seo audit https://example.com
    """
    cfg = load_config(required=not url)
    from engines.audit import audit_url

    urls = [url] if url else [s["url"] for s in cfg.get("sites", [])]
    if not urls:
        console.print("[red]ERROR:[/] No URL provided and no sites in config.")
        return
    multi = len(urls) > 1

    all_results = []
    for target in urls:
        console.print(f"  [dim]Auditing {target}...[/]") if multi else None
        result = audit_url(target, skip_speed=multi)
        all_results.append(result)

    # ─── Summary table (multi-site) ──────────────────────────────
    if multi:
        cat_order = ["seo", "og", "schema", "tech", "files", "geo", "links"]
        cat_labels = {"seo": "SEO", "og": "OG", "schema": "Schema", "tech": "Tech", "files": "Files", "geo": "GEO", "links": "Links"}

        summary = Table(title="Audit Summary — All Sites", box=box.ROUNDED, padding=(0, 1))
        summary.add_column("Site", style="bold", min_width=14)
        for cat in cat_order:
            summary.add_column(cat_labels[cat], justify="center", min_width=6)
        summary.add_column("Total", justify="center", style="bold", min_width=7)
        summary.add_column("Score", justify="center", min_width=5)

        all_actions = []

        for result in all_results:
            # Group checks by category
            cat_scores = {}
            for c in result["checks"]:
                cat = c["category"]
                if cat not in cat_scores:
                    cat_scores[cat] = {"ok": 0, "total": 0}
                cat_scores[cat]["total"] += 1
                if c["ok"]:
                    cat_scores[cat]["ok"] += 1

            row = [result["url"].replace("https://", "")]
            for cat in cat_order:
                s = cat_scores.get(cat, {"ok": 0, "total": 0})
                color = "green" if s["ok"] == s["total"] else ("yellow" if s["ok"] / max(s["total"], 1) >= 0.5 else "red")
                row.append(f"[{color}]{s['ok']}/{s['total']}[/]")

            pct = int(result["score"] / result["max_score"] * 100) if result["max_score"] else 0
            color = "green" if pct >= 80 else ("yellow" if pct >= 60 else "red")
            row.append(f"{result['score']}/{result['max_score']}")
            row.append(f"[{color}]{pct}%[/]")
            summary.add_row(*row)

            # Collect action items
            fails = [c for c in result["checks"] if not c["ok"] and c["hint"]]
            if fails:
                site_name = result["url"].replace("https://", "")
                for c in fails:
                    all_actions.append((site_name, c["category"], c["hint"]))

        console.print(summary)

        # Action items per site
        if all_actions:
            actions_table = Table(title="Action Items", box=box.SIMPLE)
            actions_table.add_column("Site", style="cyan", min_width=14)
            actions_table.add_column("Cat", min_width=6)
            actions_table.add_column("Issue")
            for site, cat, hint in all_actions:
                actions_table.add_row(site, cat.upper(), hint)
            console.print(actions_table)

        console.print()
        return

    # ─── Detailed view (single URL) ─────────────────────────────
    result = all_results[0]
    score = result["score"]
    max_score = result["max_score"]
    pct = int(score / max_score * 100) if max_score else 0
    color = "green" if pct >= 80 else ("yellow" if pct >= 60 else "red")

    locale_info = f"  (locale: {result['locale_url']})" if result.get("locale_url") else ""
    console.print(Panel(f"[bold]{urls[0]}[/]{locale_info}  —  [{color}]{score}/{max_score} ({pct}%)[/]", title="SEO+GEO Audit", style=color))

    categories = {}
    for c in result["checks"]:
        cat = c["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(c)

    labels = {"seo": "SEO Basics", "og": "Open Graph / Social", "schema": "Structured Data",
              "tech": "Technical", "files": "Files", "geo": "GEO (AI Optimization)",
              "links": "Links & Images"}

    for cat, items in categories.items():
        table = Table(title=labels.get(cat, cat), box=box.SIMPLE, show_header=False)
        table.add_column("Status", width=3)
        table.add_column("Check", min_width=25)
        table.add_column("Value")
        for c in items:
            icon = "[green]+[/]" if c["ok"] else "[red]x[/]"
            val = c["value"] if c["ok"] else (c["hint"] or c["value"])
            table.add_row(icon, c["name"], val)
        console.print(table)

    # Page Speed
    speed = result.get("speed", {})
    for strategy in ("mobile", "desktop"):
        sdata = speed.get(strategy, {})
        scores = sdata.get("scores", {})
        cwv = sdata.get("cwv", {})
        if not scores:
            continue

        table = Table(title=f"PageSpeed — {strategy.title()}", box=box.SIMPLE, show_header=False)
        table.add_column("Metric", min_width=20)
        table.add_column("Value", justify="right")

        for cat_id, score_val in scores.items():
            sc = "green" if score_val >= 90 else ("yellow" if score_val >= 50 else "red")
            table.add_row(cat_id.replace("-", " ").title(), f"[{sc}]{score_val}[/]")

        for label, info in cwv.items():
            val = info["value"]
            rating = info["rating"]
            rc = "green" if rating == "FAST" else ("yellow" if rating == "AVERAGE" else "red")
            unit = "ms" if label != "CLS" else ""
            display = f"{val/1000:.2f}" if label == "CLS" else f"{val:,}{unit}"
            table.add_row(f"{label}", f"[{rc}]{display}[/] ({rating})")

        console.print(table)

    # Content Analysis (keywords, readability, density)
    content = result.get("content", {})
    if content.get("keywords"):
        table = Table(title=f"Keywords — YAKE ({content.get('word_count', 0)} words, {content.get('lang', '?')})", box=box.SIMPLE)
        table.add_column("Keyword")
        table.add_column("Score", justify="right")
        table.add_column("In Title", justify="center")
        table.add_column("In H1", justify="center")
        table.add_column("In Desc", justify="center")

        for kw in content["keywords"][:12]:
            table.add_row(
                kw["keyword"], str(kw["score"]),
                "[green]+[/]" if kw["in_title"] else "[dim]-[/]",
                "[green]+[/]" if kw["in_h1"] else "[dim]-[/]",
                "[green]+[/]" if kw["in_desc"] else "[dim]-[/]",
            )
        console.print(table)

    if content.get("density"):
        table = Table(title="Word Density", box=box.SIMPLE)
        table.add_column("Word")
        table.add_column("Count", justify="right")
        table.add_column("Density", justify="right")
        for d in content["density"][:10]:
            table.add_row(d["word"], str(d["count"]), f"{d['density']}%")
        console.print(table)

    readability = content.get("readability", {})
    if readability:
        table = Table(title="Readability", box=box.SIMPLE, show_header=False)
        table.add_column("Metric", min_width=20)
        table.add_column("Value", justify="right")
        if "flesch_ease" in readability:
            fe = readability["flesch_ease"]
            color = "green" if fe >= 60 else ("yellow" if fe >= 30 else "red")
            label = "Easy" if fe >= 60 else ("Standard" if fe >= 30 else "Hard")
            table.add_row("Flesch Reading Ease", f"[{color}]{fe:.0f}[/] ({label})")
        if "flesch_grade" in readability:
            table.add_row("Flesch-Kincaid Grade", f"{readability['flesch_grade']:.1f}")
        if "gunning_fog" in readability:
            table.add_row("Gunning Fog Index", f"{readability['gunning_fog']:.1f}")
        if "reading_time_sec" in readability:
            rt = readability["reading_time_sec"]
            table.add_row("Reading Time", f"{rt:.0f}s" if rt < 60 else f"{rt/60:.1f}min")
        console.print(table)

    # Action items
    fails = [c for c in result["checks"] if not c["ok"] and c["hint"]]
    if fails:
        console.print("[bold yellow]Action Items:[/]")
        for i, c in enumerate(fails, 1):
            console.print(f"  {i}. {c['hint']}")
    console.print()


@cli.command()
@click.argument("site_name", required=False)
@click.option("--skip-audit", is_flag=True, help="Skip initial audit step")
def launch(site_name, skip_audit):
    """New site promotion — register, submit sitemaps, ping, audit."""
    cfg = load_config()
    sites = cfg.get("sites", [])

    if site_name:
        sites = [s for s in sites if s["name"].lower() == site_name.lower()]
        if not sites:
            console.print(f"[red]Site '{site_name}' not found in config.[/]")
            return

    google_ok = _has_google(cfg)
    bing_ok = _has_bing(cfg)
    yandex_ok = _has_yandex(cfg)
    indexnow_ok = _has_indexnow(cfg)

    for s in sites:
        console.print(Panel(f"[bold]{s['name']}[/] — {s['url']}", title="Launch", style="blue"))
        steps = []

        # Step 1: Add to search engines
        if google_ok:
            from engines.google_sc import add_site as gsc_add
            try:
                gsc_add(cfg["google"]["service_account_file"], s["url"] + "/")
                steps.append(("Google SC", True, "Added"))
            except Exception as e:
                steps.append(("Google SC", False, str(e)[:60]))
        else:
            steps.append(("Google SC", False, "Not configured"))

        if bing_ok:
            from engines.bing import add_site as bing_add
            try:
                bing_add(cfg["bing"]["api_key"], s["url"])
                steps.append(("Bing WMT", True, "Added"))
            except Exception as e:
                steps.append(("Bing WMT", False, str(e)[:60]))
        else:
            steps.append(("Bing WMT", False, "Not configured"))

        if yandex_ok:
            from engines.yandex import get_user_id, add_site as yandex_add
            try:
                uid = get_user_id(cfg["yandex"]["oauth_token"])
                yandex_add(cfg["yandex"]["oauth_token"], uid, s["url"])
                steps.append(("Yandex WM", True, "Added"))
            except Exception as e:
                steps.append(("Yandex WM", False, str(e)[:60]))
        else:
            steps.append(("Yandex WM", False, "Not configured"))

        # Step 2: Submit sitemaps
        sitemap = s.get("sitemap", "")
        if sitemap:
            if google_ok:
                from engines.google_sc import submit_sitemap as gsc_submit
                try:
                    sa = cfg["google"]["service_account_file"]
                    gsc_url = _resolve_gsc_url(sa, s["url"])
                    if gsc_url:
                        gsc_submit(sa, gsc_url, sitemap)
                        steps.append(("Sitemap → Google", True, "Submitted"))
                    else:
                        steps.append(("Sitemap → Google", False, "Not in GSC yet"))
                except Exception as e:
                    steps.append(("Sitemap → Google", False, str(e)[:60]))

            if bing_ok:
                from engines.bing import submit_sitemap as bing_submit
                try:
                    bing_submit(cfg["bing"]["api_key"], s["url"], sitemap)
                    steps.append(("Sitemap → Bing", True, "Submitted"))
                except Exception as e:
                    steps.append(("Sitemap → Bing", False, str(e)[:60]))

            if yandex_ok:
                from engines.yandex import get_host_id, submit_sitemap as yandex_submit
                try:
                    uid = get_user_id(cfg["yandex"]["oauth_token"])
                    hid = get_host_id(cfg["yandex"]["oauth_token"], uid, s["url"])
                    if hid:
                        yandex_submit(cfg["yandex"]["oauth_token"], uid, hid, sitemap)
                        steps.append(("Sitemap → Yandex", True, "Submitted"))
                    else:
                        steps.append(("Sitemap → Yandex", False, "Host not found"))
                except Exception as e:
                    steps.append(("Sitemap → Yandex", False, str(e)[:60]))
        else:
            steps.append(("Sitemap", False, "No sitemap URL in config"))

        # Step 3: IndexNow ping
        if indexnow_ok and sitemap:
            from engines.indexnow import submit_sitemap_urls
            try:
                result = submit_sitemap_urls(cfg["indexnow"]["key"], s["url"], sitemap)
                if result["ok"]:
                    steps.append(("IndexNow ping", True, f"{result.get('urls_count', '?')} URLs"))
                else:
                    steps.append(("IndexNow ping", False, f"HTTP {result['status']}"))
            except Exception as e:
                steps.append(("IndexNow ping", False, str(e)[:60]))
        elif not indexnow_ok:
            steps.append(("IndexNow ping", False, "Not configured"))

        # Step 4: Verify IndexNow key file
        if indexnow_ok:
            import requests as req
            key = cfg["indexnow"]["key"]
            try:
                resp = req.get(f"{s['url']}/{key}.txt", timeout=10)
                if resp.status_code == 200 and key in resp.text:
                    steps.append(("IndexNow key file", True, "Verified"))
                else:
                    steps.append(("IndexNow key file", False, f"HTTP {resp.status_code}"))
            except Exception:
                steps.append(("IndexNow key file", False, "Unreachable"))

        # Step 5: Initial audit
        if not skip_audit:
            from engines.audit import audit_url
            try:
                result = audit_url(s["url"], skip_speed=True)
                pct = int(result["score"] / result["max_score"] * 100) if result["max_score"] else 0
                color = "green" if pct >= 80 else ("yellow" if pct >= 60 else "red")
                steps.append(("SEO Audit", pct >= 60, f"[{color}]{pct}%[/] ({result['score']}/{result['max_score']})"))
            except Exception as e:
                steps.append(("SEO Audit", False, str(e)[:60]))

        # Display checklist
        table = Table(title="Launch Checklist", box=box.ROUNDED)
        table.add_column("Step", min_width=20)
        table.add_column("Status", justify="center", width=4)
        table.add_column("Details")
        for step_name, ok, detail in steps:
            icon = "[green]+[/]" if ok else "[red]x[/]"
            table.add_row(step_name, icon, detail)
        console.print(table)

        passed = sum(1 for _, ok, _ in steps if ok)
        total = len(steps)
        console.print(Panel(
            f"[bold]Next Steps:[/]\n"
            f"  1. Verify domain ownership in Google SC & Yandex WM dashboards\n"
            f"  2. Run [cyan]seo monitor[/] in a few days to track indexing\n"
            f"  3. Run [cyan]seo improve {s['url']}[/] to fix audit issues\n"
            f"  4. Run [cyan]seo competitors \"your keyword\"[/] to analyze competition",
            title=f"{passed}/{total} passed",
            style="green" if passed == total else "yellow",
        ))
        console.print()


@cli.command()
@click.argument("query")
@click.option("--site", default=None, help="Site name from config to compare against")
@click.option("--lang", default="en", help="Language code")
@click.option("--num", default=10, help="Number of results to analyze")
def competitors(query, site, lang, num):
    """Competitor & keyword analysis for a search query."""
    from engines.serp import google_search, extract_page_seo
    from engines.keywords import google_autocomplete

    cfg = load_config()

    # Find our site URL if --site specified
    our_url = None
    if site:
        for s in cfg.get("sites", []):
            if s["name"].lower() == site.lower():
                our_url = s["url"]
                break
        if not our_url:
            console.print(f"[yellow]Site '{site}' not found in config, skipping comparison.[/]")

    console.print(f"\n[bold]Competitor Analysis[/] — \"{query}\" (lang={lang}, top {num})\n")

    # Step 1: Get SERP results
    api_key = cfg.get("google", {}).get("cse_api_key", "")
    cx = cfg.get("google", {}).get("cse_cx", "")
    console.print("  [dim]Fetching Google results...[/]")
    serp_results = google_search(query, lang=lang, num=num, api_key=api_key, cx=cx)

    if not serp_results:
        console.print("  [yellow]No results returned. Google may be blocking scraping.[/]")
        console.print("  [dim]Try again later or reduce --num.[/]")
        return

    # Step 2: Extract SEO data from each competitor
    console.print(f"  [dim]Analyzing {len(serp_results)} pages...[/]")
    competitor_data = []
    for r in serp_results:
        console.print(f"    [dim]{r['position']}. {r['url'][:60]}...[/]")
        seo = extract_page_seo(r["url"])
        seo["position"] = r["position"]
        seo["snippet"] = r.get("snippet", "")
        if not seo.get("title"):
            seo["title"] = r.get("title", "")
        competitor_data.append(seo)

    # Extract our site SEO if specified
    our_seo = None
    if our_url:
        console.print(f"    [dim]Our site: {our_url}...[/]")
        our_seo = extract_page_seo(our_url)

    # Step 3: SERP Overview Table
    table = Table(title=f"SERP Overview — \"{query}\"", box=box.ROUNDED)
    table.add_column("#", justify="right", style="dim", width=3)
    table.add_column("Domain", min_width=20)
    table.add_column("Title", min_width=25, max_width=40)
    table.add_column("Words", justify="right")
    table.add_column("Schema", min_width=10)

    for c in competitor_data:
        if c.get("error"):
            table.add_row(str(c["position"]), c.get("domain", "?"), "[dim]fetch error[/]", "", "")
            continue
        schema_str = ", ".join(c.get("schema_types", [])[:3]) or "[dim]none[/]"
        table.add_row(
            str(c["position"]),
            c.get("domain", "?"),
            (c.get("title", "")[:38] + "..") if len(c.get("title", "")) > 40 else c.get("title", ""),
            str(c.get("word_count", 0)),
            schema_str,
        )

    if our_seo and not our_seo.get("error"):
        table.add_row(
            "[cyan]*[/]",
            f"[cyan]{our_seo.get('domain', '?')}[/]",
            f"[cyan]{(our_seo.get('title', '')[:38] + '..') if len(our_seo.get('title', '')) > 40 else our_seo.get('title', '')}[/]",
            f"[cyan]{our_seo.get('word_count', 0)}[/]",
            f"[cyan]{', '.join(our_seo.get('schema_types', [])[:3]) or 'none'}[/]",
        )

    console.print(table)

    # Step 4: Gap Analysis
    # Collect what competitors have
    all_schemas = set()
    competitors_with_faq = 0
    competitors_with_og = 0
    avg_word_count = 0
    valid_count = 0

    for c in competitor_data:
        if c.get("error"):
            continue
        valid_count += 1
        all_schemas.update(c.get("schema_types", []))
        if c.get("has_faq"):
            competitors_with_faq += 1
        if c.get("og_image"):
            competitors_with_og += 1
        avg_word_count += c.get("word_count", 0)

    avg_word_count = avg_word_count // max(valid_count, 1)

    gap_table = Table(title="Gap Analysis", box=box.SIMPLE)
    gap_table.add_column("Metric", min_width=20)
    gap_table.add_column("Competitors", min_width=15)
    gap_table.add_column("Your Site" if our_seo else "Recommendation", min_width=15)

    gap_table.add_row(
        "Avg word count",
        str(avg_word_count),
        f"[{'green' if our_seo and our_seo.get('word_count', 0) >= avg_word_count else 'red'}]{our_seo.get('word_count', 0)}[/]" if our_seo and not our_seo.get("error") else f"Aim for {avg_word_count}+",
    )
    gap_table.add_row(
        "Schema types",
        ", ".join(sorted(all_schemas)[:5]) or "none",
        ", ".join(our_seo.get("schema_types", [])[:3]) or "[red]none[/]" if our_seo and not our_seo.get("error") else "Add JSON-LD",
    )
    gap_table.add_row(
        "FAQ/HowTo schema",
        f"{competitors_with_faq}/{valid_count} have it",
        "[green]Yes[/]" if our_seo and our_seo.get("has_faq") else "[red]Missing[/]" if our_seo else "Add FAQ schema",
    )
    gap_table.add_row(
        "OG image",
        f"{competitors_with_og}/{valid_count} have it",
        "[green]Yes[/]" if our_seo and our_seo.get("og_image") else "[red]Missing[/]" if our_seo else "Add og:image",
    )
    console.print(gap_table)

    # Step 5: Keyword suggestions
    console.print(f"\n  [dim]Fetching keyword ideas...[/]")
    suggestions = google_autocomplete(query, lang=lang)
    if suggestions:
        kw_table = Table(title="Related Keywords", box=box.SIMPLE)
        kw_table.add_column("#", justify="right", style="dim")
        kw_table.add_column("Keyword")
        for i, s in enumerate(suggestions, 1):
            kw_table.add_row(str(i), s)
        console.print(kw_table)

    console.print()


@cli.command()
@click.option("--days", default=7, help="Analytics period in days")
@click.option("--threshold", default=3.0, help="Min position change to show")
def monitor(days, threshold):
    """Position tracking — compare current vs previous snapshot."""
    from engines.storage import load_data, save_data, timestamp

    cfg = load_config()
    sites = cfg.get("sites", [])

    if not _has_google(cfg):
        console.print("[red]Google not configured.[/] Monitor requires GSC analytics.")
        return

    from engines.google_sc import get_search_analytics
    sa = cfg["google"]["service_account_file"]

    end = date.today().isoformat()
    start = (date.today() - timedelta(days=days)).isoformat()

    # Load previous snapshot
    prev = load_data("monitor.json")
    prev_sites = prev.get("sites", {})

    # Build current snapshot
    current = {"last_check": timestamp(), "sites": {}}
    all_changes = []

    console.print(f"\n[bold]Position Monitor[/] ({start} — {end})\n")

    for s in sites:
        name = s["name"]
        gsc_url = _resolve_gsc_url(sa, s["url"])
        if not gsc_url:
            continue

        try:
            data = get_search_analytics(sa, gsc_url, start, end)
            rows = data.get("rows", [])
        except Exception as e:
            console.print(f"  [red]x[/] {name}: {e}")
            continue

        # Build current query map
        current_queries = {}
        for r in rows:
            query = r["keys"][0]
            current_queries[query] = {
                "clicks": r["clicks"],
                "impressions": r["impressions"],
                "position": round(r["position"], 1),
            }
        current["sites"][name] = {"queries": current_queries}

        # Compare with previous
        prev_queries = prev_sites.get(name, {}).get("queries", {})

        if not prev_queries:
            console.print(f"  [dim]{name}: baseline saved ({len(current_queries)} queries)[/]")
            continue

        for query, cur in current_queries.items():
            prev_q = prev_queries.get(query)
            if prev_q:
                pos_delta = cur["position"] - prev_q["position"]
                click_delta = cur["clicks"] - prev_q["clicks"]
                if abs(pos_delta) >= threshold:
                    all_changes.append({
                        "site": name, "query": query,
                        "pos_now": cur["position"], "pos_prev": prev_q["position"],
                        "delta": pos_delta,
                        "clicks_now": cur["clicks"], "clicks_prev": prev_q["clicks"],
                        "click_delta": click_delta,
                    })
            else:
                # New query
                all_changes.append({
                    "site": name, "query": query,
                    "pos_now": cur["position"], "pos_prev": None,
                    "delta": 0,
                    "clicks_now": cur["clicks"], "clicks_prev": 0,
                    "click_delta": cur["clicks"],
                    "new": True,
                })

        # Check for dropped queries
        for query, prev_q in prev_queries.items():
            if query not in current_queries:
                all_changes.append({
                    "site": name, "query": query,
                    "pos_now": None, "pos_prev": prev_q["position"],
                    "delta": 0,
                    "clicks_now": 0, "clicks_prev": prev_q["clicks"],
                    "click_delta": -prev_q["clicks"],
                    "dropped": True,
                })

    # Save current snapshot
    save_data("monitor.json", current)

    if not prev_sites:
        console.print(Panel(
            "Baseline snapshot saved. Run [cyan]seo monitor[/] again later to see changes.",
            style="blue",
        ))
        return

    if not all_changes:
        console.print("  [dim]No significant position changes detected.[/]")
        console.print()
        return

    # Display Position Changes Table
    all_changes.sort(key=lambda x: abs(x.get("delta", 0)), reverse=True)

    table = Table(title="Position Changes", box=box.ROUNDED)
    table.add_column("Site", style="bold")
    table.add_column("Query", min_width=25)
    table.add_column("Position", justify="right")
    table.add_column("Delta", justify="right")
    table.add_column("Clicks", justify="right")
    table.add_column("Status")

    for ch in all_changes[:20]:
        if ch.get("dropped"):
            table.add_row(
                ch["site"], ch["query"],
                f"[dim]{ch['pos_prev']:.1f}[/]", "",
                f"{ch['clicks_prev']} → 0",
                "[red]DROPPED[/]",
            )
        elif ch.get("new"):
            table.add_row(
                ch["site"], ch["query"],
                f"{ch['pos_now']:.1f}", "[cyan]NEW[/]",
                str(ch["clicks_now"]),
                "[cyan]NEW[/]",
            )
        else:
            delta = ch["delta"]
            # Negative delta = position improved (moved up)
            color = "green" if delta < 0 else "red"
            sign = "+" if delta > 0 else ""
            table.add_row(
                ch["site"], ch["query"],
                f"{ch['pos_now']:.1f}",
                f"[{color}]{sign}{delta:.1f}[/]",
                f"{ch['clicks_prev']} → {ch['clicks_now']}",
                f"[green]Improved[/]" if delta < 0 else "[red]Declined[/]",
            )

    console.print(table)

    # Summary
    improved = sum(1 for c in all_changes if not c.get("new") and not c.get("dropped") and c.get("delta", 0) < 0)
    declined = sum(1 for c in all_changes if not c.get("new") and not c.get("dropped") and c.get("delta", 0) > 0)
    new_q = sum(1 for c in all_changes if c.get("new"))
    dropped_q = sum(1 for c in all_changes if c.get("dropped"))

    console.print(Panel(
        f"[green]{improved} improved[/]  |  [red]{declined} declined[/]  |  "
        f"[cyan]{new_q} new[/]  |  [red]{dropped_q} dropped[/]",
        title="Summary",
        style="blue",
    ))
    console.print()


# Impact scores for audit checks (used by improve command)
_IMPACT = {
    "Title": 10, "Robots meta": 10, "HTTPS": 10,
    "Meta description": 9, "sitemap.xml": 9,
    "JSON-LD": 8, "H1": 8, "robots.txt": 8,
    "og:image": 7, "Canonical": 7, "Organization/WebSite": 7,
    "Rich schema": 6, "og:title": 6, "og:description": 6,
    "llms.txt": 5, "Image alt tags": 5, "Internal links": 5,
    "Viewport": 5, "Favicon": 4, "Hreflang": 3,
    "AI bots allowed": 4, "Markdown content": 3,
    "llms-full.txt": 2, "og:url": 2, "og:type": 2, "twitter:card": 2,
}

_DIFFICULTY = {
    "Title": "Easy", "Meta description": "Easy", "H1": "Easy",
    "Canonical": "Easy", "Viewport": "Easy", "og:title": "Easy",
    "og:description": "Easy", "og:image": "Easy", "og:url": "Easy",
    "og:type": "Easy", "twitter:card": "Easy", "Hreflang": "Medium",
    "JSON-LD": "Medium", "Organization/WebSite": "Medium",
    "Rich schema": "Medium", "Favicon": "Easy",
    "robots.txt": "Easy", "sitemap.xml": "Medium",
    "HTTPS": "Hard", "Robots meta": "Easy",
    "llms.txt": "Medium", "llms-full.txt": "Medium",
    "AI bots allowed": "Easy", "Markdown content": "Medium",
    "Image alt tags": "Medium", "Internal links": "Medium",
}


@cli.command()
@click.argument("url", required=False)
@click.option("--history", is_flag=True, help="Show full fix history")
def improve(url, history):
    """Audit→fix cycle with priority tracking."""
    from engines.storage import load_data, save_data, timestamp
    from engines.audit import audit_url

    cfg = load_config(required=not url)

    # Load previous issues
    prev = load_data("issues.json")
    prev_issues = prev.get("issues", {})
    prev_time = prev.get("last_check", "")

    if history:
        if not prev_issues:
            console.print("  [dim]No history yet. Run [cyan]seo improve[/] first.[/]")
            return
        table = Table(title="Fix History", box=box.ROUNDED)
        table.add_column("Site")
        table.add_column("Issue")
        table.add_column("Status")
        table.add_column("Since")
        for key, info in sorted(prev_issues.items()):
            site, check_name = key.split("|", 1)
            status = info.get("status", "open")
            color = "green" if status == "fixed" else "red"
            table.add_row(site, check_name, f"[{color}]{status}[/]", info.get("first_seen", "?"))
        console.print(table)
        console.print()
        return

    # Run audits
    urls = [url] if url else [s["url"] for s in cfg.get("sites", [])]
    all_issues = []
    current_issue_keys = set()

    for target in urls:
        console.print(f"  [dim]Auditing {target}...[/]")
        result = audit_url(target, skip_speed=True)
        site_label = target.replace("https://", "").replace("http://", "")

        for c in result["checks"]:
            if not c["ok"]:
                key = f"{site_label}|{c['name']}"
                current_issue_keys.add(key)
                impact = _IMPACT.get(c["name"], 5)
                difficulty = _DIFFICULTY.get(c["name"], "Medium")

                # Determine status vs previous
                prev_info = prev_issues.get(key)
                if prev_info:
                    days_open = (date.today() - date.fromisoformat(prev_info["first_seen"][:10])).days
                    status = f"Open ({days_open}d)"
                    first_seen = prev_info["first_seen"]
                else:
                    status = "New"
                    first_seen = timestamp()

                all_issues.append({
                    "key": key, "site": site_label, "category": c["category"],
                    "name": c["name"], "impact": impact, "difficulty": difficulty,
                    "hint": c.get("hint", ""), "status": status, "first_seen": first_seen,
                })

    # Check for fixed issues
    fixed = []
    for key, info in prev_issues.items():
        if info.get("status") != "fixed" and key not in current_issue_keys:
            fixed.append(key)

    # Build and save updated issues
    now = timestamp()
    updated_issues = {}
    for issue in all_issues:
        updated_issues[issue["key"]] = {
            "status": "open",
            "first_seen": issue["first_seen"],
            "last_seen": now,
        }
    for key in fixed:
        updated_issues[key] = {
            "status": "fixed",
            "first_seen": prev_issues[key]["first_seen"],
            "fixed_at": now,
        }
    # Keep historical fixed items
    for key, info in prev_issues.items():
        if info.get("status") == "fixed" and key not in updated_issues:
            updated_issues[key] = info

    save_data("issues.json", {"last_check": now, "issues": updated_issues})

    # Sort by impact (highest first)
    all_issues.sort(key=lambda x: x["impact"], reverse=True)

    if not all_issues and not fixed:
        console.print(Panel("[green]All checks passing! No issues found.[/]", style="green"))
        return

    # Display Priority Action Table
    if all_issues:
        table = Table(title="Priority Actions", box=box.ROUNDED)
        table.add_column("#", justify="right", style="dim", width=3)
        table.add_column("Site", min_width=14)
        table.add_column("Cat", width=6)
        table.add_column("Issue", min_width=15)
        table.add_column("Impact", justify="center", width=6)
        table.add_column("Difficulty", justify="center")
        table.add_column("Hint", min_width=20)
        table.add_column("Status")

        for i, issue in enumerate(all_issues, 1):
            impact_color = "red" if issue["impact"] >= 9 else ("yellow" if issue["impact"] >= 7 else "dim")
            diff_color = "green" if issue["difficulty"] == "Easy" else ("yellow" if issue["difficulty"] == "Medium" else "red")
            status_color = "cyan" if issue["status"] == "New" else "yellow"
            table.add_row(
                str(i),
                issue["site"],
                issue["category"].upper(),
                issue["name"],
                f"[{impact_color}]{issue['impact']}[/]",
                f"[{diff_color}]{issue['difficulty']}[/]",
                issue["hint"][:50] if issue["hint"] else "",
                f"[{status_color}]{issue['status']}[/]",
            )
        console.print(table)

    # Progress Panel
    new_count = sum(1 for i in all_issues if i["status"] == "New")
    open_count = sum(1 for i in all_issues if i["status"] != "New")
    fixed_count = len(fixed)

    console.print(Panel(
        f"[green]{fixed_count} fixed[/]  |  [yellow]{open_count} open[/]  |  [cyan]{new_count} new[/]"
        + (f"  |  Previous check: {prev_time[:10]}" if prev_time else ""),
        title="Progress",
        style="blue",
    ))
    console.print()


@cli.command()
@click.option("--days", default=7, help="Number of days to show")
def traffic(days):
    """Cloudflare traffic analytics for all sites."""
    cfg = load_config()
    if not _has_cloudflare(cfg):
        console.print("[red]Cloudflare not configured.[/] Add cloudflare.api_token to config.yaml")
        return

    from engines.cloudflare import list_zones, get_zone_analytics, get_zone_errors, get_zone_countries, get_bot_human_split

    token = cfg["cloudflare"]["api_token"]
    sites = cfg.get("sites", [])
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=days)).isoformat()

    # Map site names to zone IDs
    try:
        zones = list_zones(token)
    except Exception as e:
        console.print(f"[red]Failed to list zones:[/] {e}")
        return

    zone_map = {z["name"]: z["id"] for z in zones}
    zone_plans = {z["name"]: z.get("plan", "Free") for z in zones}

    console.print(f"\n[bold]Cloudflare Traffic[/] ({start} — {end})\n")

    # Datetime range for adaptive groups (bot score queries need datetime, not date)
    dt_start = f"{start}T00:00:00Z"
    dt_end = f"{end}T23:59:59Z"

    # Summary table
    summary = Table(title="Traffic Summary", box=box.ROUNDED)
    summary.add_column("Site", style="bold", min_width=18)
    summary.add_column("Page Views", justify="right")
    summary.add_column("Uniques", justify="right", style="cyan")
    summary.add_column("Human", justify="right", style="green")
    summary.add_column("Bots", justify="right", style="yellow")
    summary.add_column("Verified", justify="right", style="dim")
    summary.add_column("Requests", justify="right", style="dim")
    summary.add_column("Bandwidth", justify="right")

    all_site_data = []

    for s in sites:
        from urllib.parse import urlparse as _urlparse
        domain = _urlparse(s["url"]).netloc
        zone_id = zone_map.get(domain)
        if not zone_id:
            summary.add_row(s["name"], "[dim]not in CF[/]", "", "", "", "", "", "")
            continue
        zone_plan = zone_plans.get(domain, "Free")

        try:
            analytics = get_zone_analytics(token, zone_id, start, end)
        except Exception as e:
            summary.add_row(s["name"], f"[red]{e}[/]", "", "", "", "", "", "")
            continue

        total_pv = sum(d["sum"]["pageViews"] for d in analytics)
        total_uniq = sum(d["uniq"]["uniques"] for d in analytics)
        total_req = sum(d["sum"]["requests"] for d in analytics)
        total_bytes = sum(d["sum"]["bytes"] for d in analytics)
        total_threats = sum(d["sum"]["threats"] for d in analytics)

        # Bot vs human split (only reliable on Enterprise with Bot Management)
        has_bot_mgmt = "enterprise" in zone_plan.lower()
        if has_bot_mgmt:
            try:
                bot_split = get_bot_human_split(token, zone_id, dt_start, dt_end)
                human_req = bot_split["human"]
                bot_req = bot_split["bot"] + bot_split.get("likely_bot", 0)
                verified_req = bot_split.get("verified_bot", 0)
                human_str = f"{human_req:,}"
                bot_str = f"{bot_req:,}"
                verified_str = f"{verified_req:,}" if verified_req else "-"
            except Exception:
                human_str = "?"
                bot_str = "?"
                verified_str = "?"
        else:
            # Free/Pro/Business — no reliable bot classification
            human_str = "[dim]-[/]"
            bot_str = "[dim]-[/]"
            verified_str = "[dim]-[/]"

        # Format bandwidth
        if total_bytes >= 1_000_000_000:
            bw = f"{total_bytes / 1_000_000_000:.1f} GB"
        elif total_bytes >= 1_000_000:
            bw = f"{total_bytes / 1_000_000:.0f} MB"
        else:
            bw = f"{total_bytes / 1_000:.0f} KB"

        summary.add_row(
            s["name"],
            f"{total_pv:,}",
            f"{total_uniq:,}",
            human_str,
            bot_str,
            verified_str,
            f"{total_req:,}",
            bw,
        )
        all_site_data.append({
            "name": s["name"], "domain": domain, "zone_id": zone_id,
            "analytics": analytics, "total_uniq": total_uniq,
        })

    console.print(summary)

    # Daily breakdown for top sites
    for site in sorted(all_site_data, key=lambda x: x["total_uniq"], reverse=True)[:3]:
        if not site["analytics"]:
            continue
        table = Table(title=f"{site['name']} — Daily", box=box.SIMPLE)
        table.add_column("Date")
        table.add_column("Views", justify="right")
        table.add_column("Uniques", justify="right", style="cyan")
        table.add_column("Requests", justify="right")

        for d in site["analytics"]:
            table.add_row(
                d["dimensions"]["date"],
                f"{d['sum']['pageViews']:,}",
                f"{d['uniq']['uniques']:,}",
                f"{d['sum']['requests']:,}",
            )
        console.print(table)

    # Top countries (aggregate)
    for site in all_site_data[:1]:  # Top site only
        try:
            countries = get_zone_countries(token, site["zone_id"], start, end)
            if countries:
                ctable = Table(title=f"{site['name']} — Top Countries", box=box.SIMPLE)
                ctable.add_column("Country")
                ctable.add_column("Requests", justify="right")
                for c in countries[:10]:
                    ctable.add_row(c["country"], f"{c['requests']:,}")
                console.print(ctable)
        except Exception:
            pass

    # HTTP errors
    has_errors = False
    for site in all_site_data:
        try:
            error_data = get_zone_errors(token, site["zone_id"], start, end)
            status_totals = {}
            for day in error_data:
                for s_entry in day.get("sum", {}).get("responseStatusMap", []):
                    code = s_entry["edgeResponseStatus"]
                    if code >= 400:
                        status_totals[code] = status_totals.get(code, 0) + s_entry["requests"]
            if status_totals:
                if not has_errors:
                    console.print()
                    etable = Table(title="HTTP Errors", box=box.SIMPLE)
                    etable.add_column("Site")
                    etable.add_column("Status")
                    etable.add_column("Count", justify="right")
                    has_errors = True
                for code, count in sorted(status_totals.items()):
                    color = "yellow" if code < 500 else "red"
                    etable.add_row(site["name"], f"[{color}]{code}[/]", f"{count:,}")
        except Exception:
            pass

    if has_errors:
        console.print(etable)

    console.print()


@cli.command()
@click.option("--days", default=7, help="Number of days to analyze")
def crawlers(days):
    """AI crawler analytics — who's crawling your sites, referrals, ROI."""
    cfg = load_config()
    if not _has_cloudflare(cfg):
        console.print("[red]Cloudflare not configured.[/] Add cloudflare.api_token to config.yaml")
        return

    from engines.cloudflare import (
        list_zones, get_ai_crawler_stats, get_ai_referral_traffic, get_ai_top_paths,
    )

    token = cfg["cloudflare"]["api_token"]
    sites = cfg.get("sites", [])

    end_dt = date.today().isoformat() + "T23:59:59Z"
    start_dt = (date.today() - timedelta(days=days)).isoformat() + "T00:00:00Z"

    # Previous period for trend comparison
    prev_end = (date.today() - timedelta(days=days)).isoformat() + "T23:59:59Z"
    prev_start = (date.today() - timedelta(days=days * 2)).isoformat() + "T00:00:00Z"

    try:
        zones = list_zones(token)
    except Exception as e:
        console.print(f"[red]Failed to list zones:[/] {e}")
        return

    zone_map = {z["name"]: z["id"] for z in zones}

    console.print(f"\n[bold]AI Crawler Analytics[/] (last {days} days)\n")

    for s in sites:
        from urllib.parse import urlparse as _urlparse
        domain = _urlparse(s["url"]).netloc
        zone_id = zone_map.get(domain)
        if not zone_id:
            continue

        console.print(f"  [dim]Scanning {s['name']}...[/]")

        # Current + previous period
        crawler_stats = get_ai_crawler_stats(token, zone_id, start_dt, end_dt)
        prev_stats = get_ai_crawler_stats(token, zone_id, prev_start, prev_end)
        prev_map = {c["crawler"]: c["requests"] for c in prev_stats}

        # Referrals
        referrals = get_ai_referral_traffic(token, zone_id, start_dt, end_dt)
        ref_map = {r["referrer"]: r["requests"] for r in referrals}

        if crawler_stats:
            total_crawls = sum(c["requests"] for c in crawler_stats)
            total_ok = sum(c["ok"] for c in crawler_stats)
            total_refs = sum(r["requests"] for r in referrals) if referrals else 0

            # Summary line
            console.print(f"\n  [bold]{s['name']}[/]: {total_crawls:,} AI crawls, "
                          f"{total_ok:,} OK ({int(total_ok/max(total_crawls,1)*100)}%), "
                          f"{total_refs:,} referrals")

            # Main crawler table with all metrics
            table = Table(title=f"AI Crawlers", box=box.ROUNDED)
            table.add_column("Crawler", min_width=16)
            table.add_column("Crawls", justify="right", style="cyan")
            table.add_column("OK", justify="right", style="green")
            table.add_column("Errors", justify="right", style="red")
            table.add_column("Bandwidth", justify="right")
            table.add_column("Trend", justify="right")
            table.add_column("Referrals", justify="right", style="magenta")
            table.add_column("ROI", justify="right", style="bold")

            for c in crawler_stats:
                bw = c["bytes"]
                if bw >= 1_000_000:
                    bw_str = f"{bw / 1_000_000:.1f} MB"
                elif bw >= 1_000:
                    bw_str = f"{bw / 1_000:.0f} KB"
                else:
                    bw_str = f"{bw} B"

                # Trend vs previous period
                prev_req = prev_map.get(c["crawler"], 0)
                if prev_req > 0:
                    change = (c["requests"] - prev_req) / prev_req * 100
                    tc = "green" if change > 0 else "red"
                    trend_str = f"[{tc}]{'+' if change > 0 else ''}{change:.0f}%[/]"
                else:
                    trend_str = "[green]new[/]"

                # Match crawler to referrer domain
                ref_count = 0
                crawler_lower = c["crawler"].lower()
                for domain, count in ref_map.items():
                    if ("openai" in crawler_lower or "chatgpt" in crawler_lower) and "chatgpt" in domain or "openai" in domain:
                        ref_count = count
                        break
                    elif "claude" in crawler_lower and "claude" in domain:
                        ref_count = count
                        break
                    elif "perplexity" in crawler_lower and "perplexity" in domain:
                        ref_count = count
                        break
                    elif "google" in crawler_lower and "gemini" in domain:
                        ref_count = count
                        break
                    elif "bing" in crawler_lower and "copilot" in domain:
                        ref_count = count
                        break

                ref_str = f"{ref_count:,}" if ref_count else "-"

                # ROI = referrals per 100 crawls
                if ref_count and c["requests"]:
                    roi = ref_count / c["requests"] * 100
                    roi_str = f"{roi:.1f}%" if roi < 10 else f"{roi:.0f}%"
                else:
                    roi_str = "-"

                table.add_row(
                    c["crawler"], f"{c['requests']:,}",
                    str(c["ok"]), str(c["errors"]),
                    bw_str, trend_str, ref_str, roi_str,
                )

            console.print(table)
        else:
            console.print(f"  [dim]{s['name']}: no AI crawler activity detected[/]")

        # Referral sources (show all, not just matched to crawlers)
        if referrals:
            rtable = Table(title="AI Referral Traffic (visitors from AI)", box=box.SIMPLE)
            rtable.add_column("Source", min_width=20)
            rtable.add_column("Visits", justify="right", style="green")
            for r in referrals:
                rtable.add_row(r["referrer"], f"{r['requests']:,}")
            console.print(rtable)

        # Top paths crawled by AI
        paths = get_ai_top_paths(token, zone_id, start_dt, end_dt)
        if paths:
            ptable = Table(title="Most Crawled Pages by AI", box=box.SIMPLE)
            ptable.add_column("Path", min_width=35)
            ptable.add_column("Crawls", justify="right", style="cyan")
            ptable.add_column("% of total", justify="right", style="dim")
            total_path_crawls = sum(p["requests"] for p in paths)
            for p in paths[:10]:
                pct = p["requests"] / max(total_path_crawls, 1) * 100
                ptable.add_row(_trunc(p["path"], 50), f"{p['requests']:,}", f"{pct:.0f}%")
            console.print(ptable)

        console.print()


@cli.command()
@click.argument("query")
@click.option("--lang", default="en", help="Language code (en, ru, etc.)")
def keywords(query, lang):
    """Get keyword ideas from Google Autocomplete."""
    from engines.keywords import google_autocomplete, people_also_search

    # Section 1: Direct autocomplete suggestions
    console.print(f"\n[bold]Google Autocomplete[/] — \"{query}\" (lang={lang})\n")
    suggestions = google_autocomplete(query, lang=lang)

    if suggestions:
        table = Table(title="Autocomplete Suggestions", box=box.SIMPLE)
        table.add_column("#", justify="right", style="dim")
        table.add_column("Suggestion")
        for i, s in enumerate(suggestions, 1):
            table.add_row(str(i), s)
        console.print(table)
    else:
        console.print("  [dim]No autocomplete suggestions found.[/]")

    # Section 2: People also search (question/comparison modifiers)
    console.print()
    also_search = people_also_search(query, lang=lang)

    if also_search:
        table = Table(title="People Also Search", box=box.SIMPLE)
        table.add_column("#", justify="right", style="dim")
        table.add_column("Keyword")
        for i, s in enumerate(also_search, 1):
            table.add_row(str(i), s)
        console.print(table)
    else:
        console.print("  [dim]No 'people also search' suggestions found.[/]")

    total = len(suggestions) + len(also_search)
    console.print(f"\n  [bold]{total}[/] keyword ideas found.\n")


@cli.command()
@click.option("--days", default=28, help="Number of days to analyze")
@click.option("--site", default=None, help="Site name (default: all with GA)")
def ga(days, site):
    """Google Analytics overview — sessions, pages, channels, countries."""
    cfg = load_config()
    if not _has_google(cfg):
        console.print("[red]Google not configured.[/]")
        return

    from engines.ga import get_overview, get_top_pages, get_channels, get_countries, get_sources, get_hostnames
    from urllib.parse import urlparse

    sa = cfg["google"]["service_account_file"]

    # Collect sites with GA property IDs, extract hostname for filtering
    # Multiple sites can share one property_id (subdomains) — each filtered by hostname
    ga_sites = []
    for s in cfg.get("sites", []):
        pid = s.get("ga_property_id")
        if pid and (not site or s["name"].lower() == site.lower()):
            hostname = urlparse(s["url"]).hostname if s.get("url") else None
            ga_sites.append((s["name"], pid, hostname))

    if not ga_sites:
        console.print("[yellow]No sites with ga_property_id in config.[/]")
        console.print("Add ga_property_id: \"XXXXXXX\" to a site in config.yaml")
        return

    # Check if any property has multiple sites — if so, we need host filtering
    from collections import Counter
    pid_counts = Counter(pid for _, pid, _ in ga_sites)
    needs_filter = {pid for pid, cnt in pid_counts.items() if cnt > 1}

    for name, property_id, hostname in ga_sites:
        # Only filter by hostname when property is shared between multiple sites
        host = hostname if property_id in needs_filter else None
        label = f"{name} ({hostname})" if host else name
        console.print(f"\n[bold]Google Analytics — {label}[/] (last {days} days)\n")

        # Overview
        try:
            ov = get_overview(sa, property_id, days, hostname=host)
            if ov:
                engage_pct = int(ov["engaged_sessions"] / max(ov["sessions"], 1) * 100)
                bounce_pct = int(ov["bounce_rate"] * 100)
                table = Table(title="Overview", box=box.ROUNDED, show_header=False)
                table.add_column("Metric", style="bold", min_width=18)
                table.add_column("Value", justify="right")
                table.add_row("Sessions", f"{ov['sessions']:,}")
                table.add_row("Users", f"{ov['users']:,}")
                table.add_row("New Users", f"{ov['new_users']:,}")
                table.add_row("Page Views", f"{ov['pageviews']:,}")
                table.add_row("Avg Duration", _fmt_duration(ov["avg_duration"]))
                table.add_row("Bounce Rate", f"{bounce_pct}%")
                table.add_row("Engaged", f"{ov['engaged_sessions']:,} ({engage_pct}%)")
                console.print(table)
            else:
                console.print("  [dim]No data[/]")
                continue
        except Exception as e:
            console.print(f"  [red]Overview error:[/] {e}")

        # Top pages
        try:
            pages = get_top_pages(sa, property_id, days, limit=12, hostname=host)
            if pages:
                ptable = Table(title="Top Pages", box=box.SIMPLE)
                ptable.add_column("Path", min_width=30)
                ptable.add_column("Views", justify="right", style="cyan")
                ptable.add_column("Users", justify="right")
                ptable.add_column("Avg Time", justify="right")
                ptable.add_column("Bounce", justify="right")
                for p in pages:
                    dur = float(p.get("averageSessionDuration", 0))
                    bounce = float(p.get("bounceRate", 0)) * 100
                    bc = "green" if bounce < 40 else ("yellow" if bounce < 60 else "red")
                    ptable.add_row(
                        _trunc(p["pagePath"]),
                        f"{int(p['screenPageViews']):,}",
                        f"{int(p['totalUsers']):,}",
                        _fmt_duration(dur),
                        f"[{bc}]{bounce:.0f}%[/]",
                    )
                console.print(ptable)
        except Exception as e:
            console.print(f"  [red]Pages error:[/] {e}")

        # Channels
        try:
            channels = get_channels(sa, property_id, days, hostname=host)
            if channels:
                ctable = Table(title="Traffic Channels", box=box.SIMPLE)
                ctable.add_column("Channel", min_width=18)
                ctable.add_column("Sessions", justify="right", style="cyan")
                ctable.add_column("Users", justify="right")
                ctable.add_column("Engaged", justify="right", style="green")
                ctable.add_column("Pages", justify="right")
                for c in channels:
                    ctable.add_row(
                        c["sessionDefaultChannelGroup"],
                        c["sessions"], c["totalUsers"],
                        c["engagedSessions"], c["screenPageViews"],
                    )
                console.print(ctable)
        except Exception as e:
            console.print(f"  [red]Channels error:[/] {e}")

        # Sources
        try:
            sources = get_sources(sa, property_id, days, limit=10, hostname=host)
            if sources:
                stable = Table(title="Top Sources", box=box.SIMPLE)
                stable.add_column("Source / Medium", min_width=25)
                stable.add_column("Sessions", justify="right", style="cyan")
                stable.add_column("Users", justify="right")
                stable.add_column("Engaged", justify="right", style="green")
                for s_item in sources:
                    stable.add_row(
                        s_item["sessionSourceMedium"],
                        s_item["sessions"], s_item["totalUsers"],
                        s_item["engagedSessions"],
                    )
                console.print(stable)
        except Exception as e:
            console.print(f"  [red]Sources error:[/] {e}")

        # Countries
        try:
            countries = get_countries(sa, property_id, days, limit=10, hostname=host)
            if countries:
                cntable = Table(title="Top Countries", box=box.SIMPLE)
                cntable.add_column("Country", min_width=15)
                cntable.add_column("Users", justify="right", style="cyan")
                cntable.add_column("Sessions", justify="right")
                for c in countries:
                    cntable.add_row(c["country"], c["totalUsers"], c["sessions"])
                console.print(cntable)
        except Exception as e:
            console.print(f"  [red]Countries error:[/] {e}")

        console.print()


@cli.command()
@click.option("--days", default=28, help="Number of days to compare")
@click.option("--site", default=None, help="Site name (default: all with both GA + CF)")
def compare(days, site):
    """Compare GA vs Cloudflare — human traffic, landing pages, search performance."""
    cfg = load_config()
    sa = cfg.get("google", {}).get("service_account_file")
    cf_token = cfg.get("cloudflare", {}).get("api_token")

    if not sa or not cf_token:
        console.print("[red]Need both Google (service_account_file) and Cloudflare (api_token) configured.[/]")
        return

    from engines.ga import (
        get_overview, get_landing_pages, get_new_vs_returning,
        get_channels, get_sources,
    )
    from engines.cloudflare import list_zones, get_zone_analytics, get_bot_human_split
    from engines.google_sc import get_search_analytics
    from urllib.parse import urlparse

    # Load CF zones
    try:
        zones = list_zones(cf_token)
    except Exception as e:
        console.print(f"[red]CF zones error:[/] {e}")
        return

    zone_map = {z["name"]: z for z in zones}

    end = date.today().isoformat()
    start = (date.today() - timedelta(days=days)).isoformat()
    dt_start = f"{start}T00:00:00Z"
    dt_end = f"{end}T23:59:59Z"

    # Collect sites that have both GA and CF
    sites = cfg.get("sites", [])
    # Group by ga_property_id to avoid duplicate property queries
    seen_props = set()

    for s in sites:
        if site and s["name"].lower() != site.lower():
            continue

        pid = s.get("ga_property_id")
        hostname = urlparse(s["url"]).hostname if s.get("url") else None
        domain = hostname or ""

        # Need at least GA or CF
        has_ga = bool(pid)
        zone_info = zone_map.get(domain)
        has_cf = bool(zone_info)

        if not has_ga and not has_cf:
            continue

        console.print(f"\n{'='*60}")
        console.print(f"[bold]{s['name']}[/] — {s.get('url', '?')}  (last {days} days)")
        console.print(f"{'='*60}\n")

        # --- GA data ---
        ga_sessions = ga_users = ga_pv = ga_engaged = 0
        ga_bounce = 0.0
        if has_ga:
            # Filter by hostname if property is shared
            prop_key = f"{pid}:{hostname}"
            host_filter = hostname if prop_key not in seen_props or True else None

            try:
                ov = get_overview(sa, pid, days, hostname=hostname)
                if ov:
                    ga_sessions = ov["sessions"]
                    ga_users = ov["users"]
                    ga_pv = ov["pageviews"]
                    ga_engaged = ov["engaged_sessions"]
                    ga_bounce = ov["bounce_rate"]
            except Exception as e:
                console.print(f"  [red]GA error:[/] {e}")

        # --- CF data ---
        cf_requests = cf_pv = cf_uniq = 0
        cf_human = cf_bot = cf_verified = 0
        if has_cf:
            zone_id = zone_info["id"]
            zone_plan = zone_info.get("plan", "Free")
            has_bot_mgmt = "enterprise" in zone_plan.lower()

            try:
                analytics = get_zone_analytics(cf_token, zone_id, start, end)
                cf_requests = sum(d["sum"]["requests"] for d in analytics)
                cf_pv = sum(d["sum"]["pageViews"] for d in analytics)
                cf_uniq = sum(d["uniq"]["uniques"] for d in analytics)
            except Exception:
                pass

            if has_bot_mgmt:
                try:
                    bot = get_bot_human_split(cf_token, zone_id, dt_start, dt_end)
                    cf_human = bot["human"]
                    cf_bot = bot["bot"] + bot.get("likely_bot", 0)
                    cf_verified = bot.get("verified_bot", 0)
                except Exception:
                    pass

        # --- Traffic overview table ---
        t = Table(title="Traffic Overview", box=box.ROUNDED)
        t.add_column("Metric", style="bold", min_width=20)
        t.add_column("GA (real users)", justify="right", style="green")
        t.add_column("CF (all traffic)", justify="right", style="cyan")

        t.add_row("Users", f"{ga_users:,}" if has_ga else "-", f"{cf_uniq:,}" if cf_uniq else "-")
        t.add_row("Page Views", f"{ga_pv:,}" if has_ga else "-", f"{cf_pv:,}" if has_cf else "-")
        t.add_row("Sessions", f"{ga_sessions:,}" if has_ga else "-", "-")
        t.add_row("Total Requests", "-", f"{cf_requests:,}" if has_cf else "-")

        if has_ga and ga_sessions:
            engage_pct = int(ga_engaged / max(ga_sessions, 1) * 100)
            bounce_pct = int(ga_bounce * 100)
            bc = "green" if bounce_pct < 40 else ("yellow" if bounce_pct < 60 else "red")
            t.add_row("Engaged Sessions", f"{ga_engaged:,} ({engage_pct}%)", "-")
            t.add_row("Bounce Rate", f"[{bc}]{bounce_pct}%[/]", "-")

        console.print(t)

        # --- CF Bot breakdown ---
        if cf_human:
            total_cf = cf_human + cf_bot + cf_verified
            bt = Table(title="Cloudflare Bot Management", box=box.ROUNDED)
            bt.add_column("Category", style="bold", min_width=18)
            bt.add_column("Requests", justify="right")
            bt.add_column("%", justify="right")
            bt.add_column("", style="dim")

            bt.add_row("[green]Humans[/]", f"{cf_human:,}", f"{cf_human/max(total_cf,1)*100:.0f}%", "real visitors")
            bt.add_row("[yellow]Bots[/]", f"{cf_bot:,}", f"{cf_bot/max(total_cf,1)*100:.0f}%", "scrapers, AI crawlers")
            bt.add_row("[dim]Verified Bots[/]", f"{cf_verified:,}", f"{cf_verified/max(total_cf,1)*100:.0f}%", "Googlebot, BingBot etc")
            bt.add_row("[bold]Total[/]", f"[bold]{total_cf:,}[/]", "100%", "")
            console.print(bt)

        # --- New vs Returning ---
        if has_ga and ga_sessions:
            try:
                nvr = get_new_vs_returning(sa, pid, days, hostname=hostname)
                if nvr:
                    nvr_table = Table(title="New vs Returning Users", box=box.SIMPLE)
                    nvr_table.add_column("Type", min_width=12)
                    nvr_table.add_column("Sessions", justify="right", style="cyan")
                    nvr_table.add_column("Users", justify="right")
                    nvr_table.add_column("Engaged", justify="right", style="green")
                    nvr_table.add_column("Avg Duration", justify="right")
                    for row in nvr:
                        dur = float(row.get("averageSessionDuration", 0))
                        nvr_table.add_row(
                            row.get("newVsReturning", "?"),
                            f"{int(row['sessions']):,}",
                            f"{int(row['totalUsers']):,}",
                            f"{int(row['engagedSessions']):,}",
                            _fmt_duration(dur),
                        )
                    console.print(nvr_table)
            except Exception as e:
                console.print(f"  [dim]New/returning: {e}[/]")

        # --- Landing Pages (GA) + Search Queries (GSC) ---
        if has_ga and ga_sessions:
            try:
                landings = get_landing_pages(sa, pid, days, limit=10, hostname=hostname)
                if landings:
                    ltable = Table(title="Top Landing Pages (entry points)", box=box.SIMPLE)
                    ltable.add_column("Landing Page", min_width=30)
                    ltable.add_column("Sessions", justify="right", style="cyan")
                    ltable.add_column("Users", justify="right")
                    ltable.add_column("Engaged", justify="right", style="green")
                    ltable.add_column("Bounce", justify="right")
                    ltable.add_column("Pages/Sess", justify="right")
                    for lp in landings:
                        sess = int(lp.get("sessions", 0))
                        engaged = int(lp.get("engagedSessions", 0))
                        pv = int(lp.get("screenPageViews", 0))
                        bounce = float(lp.get("bounceRate", 0)) * 100
                        pps = pv / max(sess, 1)
                        bc = "green" if bounce < 40 else ("yellow" if bounce < 60 else "red")
                        ltable.add_row(
                            _trunc(lp.get("landingPage", "?")),
                            f"{sess:,}", f"{int(lp.get('totalUsers', 0)):,}",
                            f"{engaged:,}",
                            f"[{bc}]{bounce:.0f}%[/]",
                            f"{pps:.1f}",
                        )
                    console.print(ltable)
            except Exception as e:
                console.print(f"  [dim]Landing pages: {e}[/]")

        # --- GSC Search Performance ---
        gsc_url = _resolve_gsc_url(sa, s["url"]) if has_ga else None
        if gsc_url:
            try:
                # Top queries
                qdata = get_search_analytics(sa, gsc_url, start, end, dimensions=["query"])
                rows = qdata.get("rows", [])
                if rows:
                    qtable = Table(title="Top Search Queries (GSC)", box=box.SIMPLE)
                    qtable.add_column("Query", min_width=25)
                    qtable.add_column("Clicks", justify="right", style="cyan")
                    qtable.add_column("Impressions", justify="right")
                    qtable.add_column("CTR", justify="right", style="green")
                    qtable.add_column("Position", justify="right")
                    for r in rows[:12]:
                        ctr = r.get("ctr", 0) * 100
                        pos = r.get("position", 0)
                        pc = "green" if pos <= 3 else ("yellow" if pos <= 10 else "red")
                        qtable.add_row(
                            _trunc(r["keys"][0], 40),
                            f"{int(r.get('clicks', 0)):,}",
                            f"{int(r.get('impressions', 0)):,}",
                            f"{ctr:.1f}%",
                            f"[{pc}]{pos:.1f}[/]",
                        )
                    console.print(qtable)

                # Top pages by clicks
                pdata = get_search_analytics(sa, gsc_url, start, end, dimensions=["page"])
                prows = pdata.get("rows", [])
                if prows:
                    ptable = Table(title="Top Pages by Search Clicks (GSC)", box=box.SIMPLE)
                    ptable.add_column("Page", min_width=35)
                    ptable.add_column("Clicks", justify="right", style="cyan")
                    ptable.add_column("Impressions", justify="right")
                    ptable.add_column("CTR", justify="right", style="green")
                    ptable.add_column("Avg Pos", justify="right")
                    for r in prows[:10]:
                        url_path = urlparse(r["keys"][0]).path or "/"
                        ctr = r.get("ctr", 0) * 100
                        pos = r.get("position", 0)
                        ptable.add_row(
                            _trunc(url_path),
                            f"{int(r.get('clicks', 0)):,}",
                            f"{int(r.get('impressions', 0)):,}",
                            f"{ctr:.1f}%",
                            f"{pos:.1f}",
                        )
                    console.print(ptable)
            except Exception as e:
                console.print(f"  [dim]GSC: {e}[/]")

        # --- AI Referrals (from GA sources) ---
        if has_ga and ga_sessions:
            try:
                sources = get_sources(sa, pid, days, limit=50, hostname=hostname)
                ai_sources = [
                    s for s in sources
                    if any(ai in s.get("sessionSourceMedium", "").lower()
                           for ai in ["chatgpt", "perplexity", "gemini", "copilot", "claude", "you.com"])
                ]
                if ai_sources:
                    atable = Table(title="AI Referral Traffic", box=box.SIMPLE)
                    atable.add_column("Source", min_width=25)
                    atable.add_column("Sessions", justify="right", style="cyan")
                    atable.add_column("Users", justify="right")
                    atable.add_column("Engaged", justify="right", style="green")
                    for ai in ai_sources:
                        atable.add_row(
                            ai["sessionSourceMedium"],
                            ai["sessions"], ai["totalUsers"],
                            ai["engagedSessions"],
                        )
                    console.print(atable)
            except Exception:
                pass

        console.print()


def main():
    cli()


if __name__ == "__main__":
    main()
