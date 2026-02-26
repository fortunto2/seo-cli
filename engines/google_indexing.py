"""Google Indexing API — instant URL indexing."""


def _build_service(sa_file: str):
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds = service_account.Credentials.from_service_account_file(
        sa_file, scopes=["https://www.googleapis.com/auth/indexing"]
    )
    return build("indexing", "v3", credentials=creds)


def publish_url(sa_file: str, url: str, action: str = "URL_UPDATED") -> dict:
    """Notify Google about a URL change. action: URL_UPDATED or URL_DELETED."""
    service = _build_service(sa_file)
    body = {"url": url, "type": action}
    return service.urlNotifications().publish(body=body).execute()


def get_notification_status(sa_file: str, url: str) -> dict:
    """Check the last notification status for a URL."""
    service = _build_service(sa_file)
    return service.urlNotifications().getMetadata(url=url).execute()
