"""Yandex Webmaster API v4."""

import requests

BASE = "https://api.webmaster.yandex.net/v4"


def _headers(token: str) -> dict:
    return {"Authorization": f"OAuth {token}", "Content-Type": "application/json"}


def get_user_id(token: str) -> int:
    resp = requests.get(f"{BASE}/user/", headers=_headers(token), timeout=30)
    resp.raise_for_status()
    return resp.json()["user_id"]


def list_sites(token: str, user_id: int) -> list:
    resp = requests.get(f"{BASE}/user/{user_id}/hosts/", headers=_headers(token), timeout=30)
    resp.raise_for_status()
    return resp.json().get("hosts", [])


def add_site(token: str, user_id: int, site_url: str) -> dict:
    resp = requests.post(
        f"{BASE}/user/{user_id}/hosts/",
        headers=_headers(token),
        json={"host_url": site_url},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_host_id(token: str, user_id: int, site_url: str) -> str | None:
    """Find host_id for a given site URL."""
    hosts = list_sites(token, user_id)
    for host in hosts:
        if host.get("unicode_host_url", "").rstrip("/") == site_url.rstrip("/"):
            return host["host_id"]
        if host.get("ascii_host_url", "").rstrip("/") == site_url.rstrip("/"):
            return host["host_id"]
    return None


def submit_sitemap(token: str, user_id: int, host_id: str, sitemap_url: str) -> dict:
    resp = requests.post(
        f"{BASE}/user/{user_id}/hosts/{host_id}/user-added-sitemaps/",
        headers=_headers(token),
        json={"url": sitemap_url},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def list_sitemaps(token: str, user_id: int, host_id: str) -> list:
    resp = requests.get(
        f"{BASE}/user/{user_id}/hosts/{host_id}/user-added-sitemaps/",
        headers=_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("sitemaps", [])


def submit_url_for_reindex(token: str, user_id: int, host_id: str, url: str) -> dict:
    resp = requests.post(
        f"{BASE}/user/{user_id}/hosts/{host_id}/recrawl/queue/",
        headers=_headers(token),
        json={"url": url},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_reindex_quota(token: str, user_id: int, host_id: str) -> dict:
    resp = requests.get(
        f"{BASE}/user/{user_id}/hosts/{host_id}/recrawl/quota/",
        headers=_headers(token),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_indexing_history(
    token: str, user_id: int, host_id: str, date_from: str, date_to: str
) -> dict:
    resp = requests.get(
        f"{BASE}/user/{user_id}/hosts/{host_id}/indexing/history/",
        headers=_headers(token),
        params={"date_from": date_from, "date_to": date_to},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def get_search_queries(
    token: str, user_id: int, host_id: str, date_from: str, date_to: str
) -> dict:
    resp = requests.get(
        f"{BASE}/user/{user_id}/hosts/{host_id}/search-queries/popular/",
        headers=_headers(token),
        params={"date_from": date_from, "date_to": date_to},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()
