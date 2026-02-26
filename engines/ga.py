"""Google Analytics 4 Data API — sessions, users, pages, channels, countries."""

from google.oauth2 import service_account
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest, RunRealtimeReportRequest,
    DateRange, Dimension, Metric, OrderBy, FilterExpression, Filter,
)

SCOPES = ["https://www.googleapis.com/auth/analytics.readonly"]


def _client(sa_file: str) -> BetaAnalyticsDataClient:
    return BetaAnalyticsDataClient.from_service_account_file(sa_file)


def _host_filter(hostname: str | None) -> FilterExpression | None:
    """Build a dimension filter for hostName if specified."""
    if not hostname:
        return None
    return FilterExpression(
        filter=Filter(
            field_name="hostName",
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.EXACT,
                value=hostname,
            ),
        )
    )


def _rows_to_dicts(resp) -> list[dict]:
    """Convert GA4 response rows into plain dicts."""
    dims = [h.name for h in resp.dimension_headers]
    mets = [h.name for h in resp.metric_headers]
    results = []
    for row in resp.rows:
        d = {}
        for i, dv in enumerate(row.dimension_values):
            d[dims[i]] = dv.value
        for i, mv in enumerate(row.metric_values):
            d[mets[i]] = mv.value
        results.append(d)
    return results


def list_properties(sa_file: str) -> list[dict]:
    """List GA4 properties accessible by the service account."""
    from googleapiclient.discovery import build
    creds = service_account.Credentials.from_service_account_file(sa_file, scopes=SCOPES)
    service = build("analyticsadmin", "v1beta", credentials=creds)
    summaries = service.accountSummaries().list().execute()
    results = []
    for acc in summaries.get("accountSummaries", []):
        for prop in acc.get("propertySummaries", []):
            results.append({
                "account": acc["displayName"],
                "property": prop["displayName"],
                "property_id": prop["property"].replace("properties/", ""),
            })
    return results


def get_overview(sa_file: str, property_id: str, days: int = 28, hostname: str = None) -> dict:
    """Get high-level overview: sessions, users, pageviews, bounce, avg duration."""
    client = _client(sa_file)
    resp = client.run_report(RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="yesterday")],
        metrics=[
            Metric(name="sessions"),
            Metric(name="totalUsers"),
            Metric(name="newUsers"),
            Metric(name="screenPageViews"),
            Metric(name="averageSessionDuration"),
            Metric(name="bounceRate"),
            Metric(name="engagedSessions"),
        ],
        dimension_filter=_host_filter(hostname),
    ))
    if not resp.rows:
        return {}
    mv = resp.rows[0].metric_values
    return {
        "sessions": int(mv[0].value),
        "users": int(mv[1].value),
        "new_users": int(mv[2].value),
        "pageviews": int(mv[3].value),
        "avg_duration": float(mv[4].value),
        "bounce_rate": float(mv[5].value),
        "engaged_sessions": int(mv[6].value),
    }


def get_top_pages(sa_file: str, property_id: str, days: int = 28, limit: int = 15, hostname: str = None) -> list[dict]:
    """Get top pages by pageviews."""
    client = _client(sa_file)
    resp = client.run_report(RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="yesterday")],
        dimensions=[Dimension(name="pagePath")],
        metrics=[
            Metric(name="screenPageViews"),
            Metric(name="totalUsers"),
            Metric(name="averageSessionDuration"),
            Metric(name="bounceRate"),
        ],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="screenPageViews"), desc=True)],
        limit=limit,
        dimension_filter=_host_filter(hostname),
    ))
    return _rows_to_dicts(resp)


def get_channels(sa_file: str, property_id: str, days: int = 28, hostname: str = None) -> list[dict]:
    """Get traffic by channel group."""
    client = _client(sa_file)
    resp = client.run_report(RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="yesterday")],
        dimensions=[Dimension(name="sessionDefaultChannelGroup")],
        metrics=[
            Metric(name="sessions"),
            Metric(name="totalUsers"),
            Metric(name="engagedSessions"),
            Metric(name="screenPageViews"),
        ],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        dimension_filter=_host_filter(hostname),
    ))
    return _rows_to_dicts(resp)


def get_countries(sa_file: str, property_id: str, days: int = 28, limit: int = 10, hostname: str = None) -> list[dict]:
    """Get top countries by users."""
    client = _client(sa_file)
    resp = client.run_report(RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="yesterday")],
        dimensions=[Dimension(name="country")],
        metrics=[Metric(name="totalUsers"), Metric(name="sessions")],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="totalUsers"), desc=True)],
        limit=limit,
        dimension_filter=_host_filter(hostname),
    ))
    return _rows_to_dicts(resp)


def get_sources(sa_file: str, property_id: str, days: int = 28, limit: int = 10, hostname: str = None) -> list[dict]:
    """Get top traffic sources (source/medium)."""
    client = _client(sa_file)
    resp = client.run_report(RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="yesterday")],
        dimensions=[Dimension(name="sessionSourceMedium")],
        metrics=[
            Metric(name="sessions"),
            Metric(name="totalUsers"),
            Metric(name="engagedSessions"),
        ],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
        limit=limit,
        dimension_filter=_host_filter(hostname),
    ))
    return _rows_to_dicts(resp)


def get_daily(sa_file: str, property_id: str, days: int = 28, hostname: str = None) -> list[dict]:
    """Get daily sessions, users, pageviews."""
    client = _client(sa_file)
    resp = client.run_report(RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="yesterday")],
        dimensions=[Dimension(name="date")],
        metrics=[
            Metric(name="sessions"),
            Metric(name="totalUsers"),
            Metric(name="screenPageViews"),
        ],
        order_bys=[OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name="date"))],
        dimension_filter=_host_filter(hostname),
    ))
    return _rows_to_dicts(resp)


def get_hostnames(sa_file: str, property_id: str, days: int = 28) -> list[dict]:
    """Get all hostnames with traffic in this property."""
    client = _client(sa_file)
    resp = client.run_report(RunReportRequest(
        property=f"properties/{property_id}",
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="yesterday")],
        dimensions=[Dimension(name="hostName")],
        metrics=[Metric(name="sessions"), Metric(name="totalUsers"), Metric(name="screenPageViews")],
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name="sessions"), desc=True)],
    ))
    return _rows_to_dicts(resp)


def get_realtime(sa_file: str, property_id: str) -> dict:
    """Get realtime active users."""
    client = _client(sa_file)
    resp = client.run_realtime_report(RunRealtimeReportRequest(
        property=f"properties/{property_id}",
        metrics=[Metric(name="activeUsers")],
    ))
    if resp.rows:
        return {"active_users": int(resp.rows[0].metric_values[0].value)}
    return {"active_users": 0}
