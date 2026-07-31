"""IndexNow — instant URL submission to Bing, Yandex, Naver, Seznam."""

import requests
from urllib.parse import urlparse

ENDPOINT = "https://api.indexnow.org/indexnow"


def submit_urls(key: str, site_url: str, urls: list[str]) -> dict:
    """Submit URLs via IndexNow. Max 10,000 per batch."""
    host = urlparse(site_url).netloc
    resp = requests.post(
        ENDPOINT,
        json={
            "host": host,
            "key": key,
            "keyLocation": f"{site_url}/{key}.txt",
            "urlList": urls,
        },
        timeout=30,
    )
    return {"status": resp.status_code, "ok": resp.status_code in (200, 202)}


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
