"""Google Search Console API."""


def _build_service(sa_file: str, api: str = "searchconsole", version: str = "v1"):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    scopes = ["https://www.googleapis.com/auth/webmasters"]
    creds = service_account.Credentials.from_service_account_file(sa_file, scopes=scopes)
    return build(api, version, credentials=creds)


def list_sites(sa_file: str) -> list:
    service = _build_service(sa_file, "webmasters", "v3")
    result = service.sites().list().execute()
    return result.get("siteEntry", [])


def add_site(sa_file: str, site_url: str) -> dict:
    service = _build_service(sa_file, "webmasters", "v3")
    service.sites().add(siteUrl=site_url).execute()
    return {"ok": True, "site": site_url}


def submit_sitemap(sa_file: str, site_url: str, sitemap_url: str) -> dict:
    service = _build_service(sa_file, "webmasters", "v3")
    service.sitemaps().submit(siteUrl=site_url, feedpath=sitemap_url).execute()
    return {"ok": True, "sitemap": sitemap_url}


def list_sitemaps(sa_file: str, site_url: str) -> list:
    service = _build_service(sa_file, "webmasters", "v3")
    result = service.sitemaps().list(siteUrl=site_url).execute()
    return result.get("sitemap", [])


def get_search_analytics(
    sa_file: str, site_url: str, start_date: str, end_date: str, dimensions: list[str] | None = None
) -> dict:
    service = _build_service(sa_file, "webmasters", "v3")
    body = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": dimensions or ["query"],
        "rowLimit": 25,
    }
    return service.searchanalytics().query(siteUrl=site_url, body=body).execute()


def inspect_url(sa_file: str, site_url: str, page_url: str) -> dict:
    service = _build_service(sa_file)
    body = {"inspectionUrl": page_url, "siteUrl": site_url}
    result = service.urlInspection().index().inspect(body=body).execute()
    return result.get("inspectionResult", {})
