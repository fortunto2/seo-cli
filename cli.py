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


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        console.print("[red]ERROR:[/] config.yaml not found.")
        console.print("Copy config.example.yaml to config.yaml and fill in credentials.")
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
    """Show all sites + engine connections."""
    cfg = load_config()
    sites = cfg.get("sites", [])

    table = Table(title=f"SEO CLI — {len(sites)} sites", box=box.ROUNDED)
    table.add_column("Site", style="bold")
    table.add_column("URL", style="cyan")
    table.add_column("Google", justify="center")
    table.add_column("Bing", justify="center")
    table.add_column("Yandex", justify="center")
    table.add_column("IndexNow", justify="center")

    google_ok = _has_google(cfg)
    bing_ok = _has_bing(cfg)
    yandex_ok = _has_yandex(cfg)
    indexnow_ok = _has_indexnow(cfg)

    gsc_urls = set()
    if google_ok:
        gsc_urls = _get_gsc_urls(cfg["google"]["service_account_file"])

    for s in sites:
        from urllib.parse import urlparse
        domain = urlparse(s["url"]).netloc
        in_gsc = any(x in gsc_urls for x in [s["url"] + "/", s["url"], f"sc-domain:{domain}"])

        table.add_row(
            s["name"],
            s["url"],
            "[green]Owner[/]" if google_ok and in_gsc else ("[yellow]--[/]" if google_ok else "[dim]off[/]"),
            "[green]OK[/]" if bing_ok else "[dim]off[/]",
            "[green]OK[/]" if yandex_ok else "[dim]off[/]",
            "[green]OK[/]" if indexnow_ok else "[dim]off[/]",
        )

    console.print(table)


@cli.command()
def analytics():
    """Search analytics last 28 days (Google + Yandex)."""
    cfg = load_config()
    sites = cfg.get("sites", [])
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=28)).isoformat()

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

                table = Table(title=f"{s['name']} — {total_clicks} clicks, {total_impressions:,} impressions", box=box.SIMPLE)
                table.add_column("Query")
                table.add_column("Clicks", justify="right", style="green")
                table.add_column("Impressions", justify="right")
                table.add_column("Position", justify="right", style="yellow")

                for r in sorted(rows, key=lambda x: x["clicks"], reverse=True)[:10]:
                    table.add_row(r["keys"][0], str(r["clicks"]), f"{r['impressions']:,}", f"{r['position']:.1f}")

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


@cli.command()
def report():
    """Full SEO report across all sites."""
    cfg = load_config()
    sites = cfg.get("sites", [])
    end = date.today().isoformat()
    start = (date.today() - timedelta(days=28)).isoformat()

    console.print(Panel(f"SEO REPORT — {start} to {end}", style="bold blue"))

    total_clicks = 0
    total_impressions = 0
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
                data = get_search_analytics(sa, gsc_url, start, end)
                rows = data.get("rows", [])
                clicks = sum(r.get("clicks", 0) for r in rows)
                impressions = sum(r.get("impressions", 0) for r in rows)
                total_clicks += clicks
                total_impressions += impressions
                avg_pos = sum(r["position"] * r["impressions"] for r in rows) / max(impressions, 1) if rows else 0

                color = "green" if clicks > 0 else "dim"
                console.print(f"\n  [{color}]{name}[/] — [bold]{clicks:,}[/] clicks | {impressions:,} imp | avg pos {avg_pos:.1f}")

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

    # Totals
    console.print(Panel(f"TOTALS: [bold green]{total_clicks:,}[/] clicks | [bold]{total_impressions:,}[/] impressions", style="blue"))

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
    """SEO + GEO page audit. Audits all sites if no URL given."""
    cfg = load_config()
    from engines.audit import audit_url

    urls = [url] if url else [s["url"] for s in cfg.get("sites", [])]
    multi = len(urls) > 1

    all_results = []
    for target in urls:
        console.print(f"  [dim]Auditing {target}...[/]") if multi else None
        result = audit_url(target, skip_speed=multi)
        all_results.append(result)

    # ─── Summary table (multi-site) ──────────────────────────────
    if multi:
        cat_order = ["seo", "og", "schema", "tech", "files", "geo"]
        cat_labels = {"seo": "SEO", "og": "OG", "schema": "Schema", "tech": "Tech", "files": "Files", "geo": "GEO"}

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

    console.print(Panel(f"[bold]{urls[0]}[/]  —  [{color}]{score}/{max_score} ({pct}%)[/]", title="SEO+GEO Audit", style=color))

    categories = {}
    for c in result["checks"]:
        cat = c["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(c)

    labels = {"seo": "SEO Basics", "og": "Open Graph / Social", "schema": "Structured Data",
              "tech": "Technical", "files": "Files", "geo": "GEO (AI Optimization)"}

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


def main():
    cli()


if __name__ == "__main__":
    main()
