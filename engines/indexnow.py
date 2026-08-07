"""IndexNow — instant URL submission to Bing, Yandex, Naver, Seznam."""

import requests
from urllib.parse import urlparse

ENDPOINT = "https://api.indexnow.org/indexnow"


BATCH = 10_000


def submit_urls(key: str, site_url: str, urls: list[str]) -> dict:
    """Submit URLs via IndexNow, in batches of 10,000.

    The docstring said "max 10,000 per batch" and the code sent whatever it was handed, so a site
    with a large sitemap got one 400 for the whole submission and no indication why. Air Signal has
    62,000 URLs; every one of them was rejected together.

    Reports the batches separately: a partial success is a real outcome here, and collapsing it to
    one ok/failed hides which half went through.
    """
    host = urlparse(site_url).netloc
    batches = [urls[i : i + BATCH] for i in range(0, len(urls), BATCH)] or [[]]
    statuses: list[int] = []

    for batch in batches:
        if not batch:
            continue
        resp = requests.post(
            ENDPOINT,
            json={
                "host": host,
                "key": key,
                "keyLocation": f"{site_url}/{key}.txt",
                "urlList": batch,
            },
            timeout=30,
        )
        statuses.append(resp.status_code)

    accepted = sum(1 for s in statuses if s in (200, 202))
    return {
        "status": statuses[0] if statuses else 0,
        "ok": bool(statuses) and accepted == len(statuses),
        "batches": len(statuses),
        "accepted": accepted,
    }


def submit_sitemap_urls(key: str, site_url: str, sitemap_url: str) -> dict:
    """Fetch sitemap and submit all URLs via IndexNow."""
    import xml.etree.ElementTree as ET

    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    def fetch(url: str) -> list[str]:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        locs = [loc.text for loc in root.findall(".//s:loc", ns) if loc.text]
        # A <sitemapindex> lists other sitemaps, not pages — follow them one level.
        if root.tag.endswith("sitemapindex"):
            nested: list[str] = []
            for child in locs:
                try:
                    nested.extend(fetch(child))
                except Exception:
                    continue
            return nested
        return locs

    urls = fetch(sitemap_url)

    if not urls:
        return {"status": 0, "ok": False, "error": "No URLs found in sitemap"}

    result = submit_urls(key, site_url, urls)
    result["urls_count"] = len(urls)
    return result
