"""Bing Webmaster Tools API."""

import requests

BASE = "https://ssl.bing.com/webmaster/api.svc/json"


def _get(endpoint: str, api_key: str, **params) -> dict:
    resp = requests.get(f"{BASE}/{endpoint}", params={"apikey": api_key, **params}, timeout=30)
    resp.raise_for_status()
    return resp.json().get("d", resp.json())


def _post(endpoint: str, api_key: str, data: dict) -> dict:
    resp = requests.post(
        f"{BASE}/{endpoint}",
        params={"apikey": api_key},
        json=data,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json() if resp.text else {"ok": True}


def list_sites(api_key: str) -> list:
    return _get("GetUserSites", api_key)


def add_site(api_key: str, site_url: str) -> dict:
    return _post("AddSite", api_key, {"siteUrl": site_url})


def submit_sitemap(api_key: str, site_url: str, sitemap_url: str) -> dict:
    return _post("SubmitFeed", api_key, {"siteUrl": site_url, "feedUrl": sitemap_url})


def submit_urls(api_key: str, site_url: str, urls: list[str]) -> dict:
    """Submit up to 500 URLs per call, 10,000/day."""
    return _post("SubmitUrlBatch", api_key, {"siteUrl": site_url, "urlList": urls[:500]})


def get_crawl_stats(api_key: str, site_url: str) -> dict:
    return _get("GetCrawlStats", api_key, siteUrl=site_url)


def get_query_stats(api_key: str, site_url: str) -> dict:
    return _get("GetQueryStats", api_key, siteUrl=site_url)
