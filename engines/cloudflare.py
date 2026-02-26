"""Cloudflare Analytics API — traffic, errors, top countries, AI crawlers via GraphQL."""

import requests

GRAPHQL_URL = "https://api.cloudflare.com/client/v4/graphql"
ZONES_URL = "https://api.cloudflare.com/client/v4/zones"

# Known AI crawlers (user-agent patterns + labels)
AI_CRAWLERS = [
    ("GPTBot", "OpenAI GPTBot"),
    ("ChatGPT-User", "ChatGPT User"),
    ("OAI-SearchBot", "OpenAI Search"),
    ("ClaudeBot", "Anthropic Claude"),
    ("Claude-SearchBot", "Claude Search"),
    ("Claude-User", "Claude User"),
    ("Google-CloudVertexBot", "Google Vertex"),
    ("Googlebot", "Googlebot"),
    ("bingbot", "Bingbot"),
    ("Bytespider", "ByteDance"),
    ("CCBot", "Common Crawl"),
    ("meta-externalagent", "Meta Agent"),
    ("meta-externalfetcher", "Meta Fetcher"),
    ("FacebookBot", "FacebookBot"),
    ("Applebot", "Applebot"),
    ("Amazonbot", "Amazonbot"),
    ("DuckAssistBot", "DuckDuckGo"),
    ("PerplexityBot", "Perplexity"),
    ("Perplexity-User", "Perplexity User"),
    ("MistralAI-User", "Mistral AI"),
]

# AI referrer domains (for referral traffic from AI platforms)
AI_REFERRERS = [
    "chatgpt.com",
    "chat.openai.com",
    "perplexity.ai",
    "claude.ai",
    "gemini.google.com",
    "copilot.microsoft.com",
    "you.com",
]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def list_zones(token: str) -> list[dict]:
    """List all Cloudflare zones (sites)."""
    resp = requests.get(ZONES_URL, headers=_headers(token), params={"per_page": 50}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return [{"id": z["id"], "name": z["name"], "status": z["status"]} for z in data.get("result", [])]


def get_zone_analytics(token: str, zone_id: str, date_from: str, date_to: str) -> list[dict]:
    """Get daily HTTP analytics for a zone (pageViews, uniques, requests, bytes, threats)."""
    query = """
    {
      viewer {
        zones(filter: {zoneTag: "%s"}) {
          httpRequests1dGroups(
            limit: 30
            filter: {date_geq: "%s", date_leq: "%s"}
            orderBy: [date_ASC]
          ) {
            dimensions { date }
            sum { requests pageViews bytes threats }
            uniq { uniques }
          }
        }
      }
    }
    """ % (zone_id, date_from, date_to)

    resp = requests.post(GRAPHQL_URL, headers=_headers(token), json={"query": query}, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    zones = data.get("data", {}).get("viewer", {}).get("zones", [])
    if not zones:
        return []
    return zones[0].get("httpRequests1dGroups", [])


def get_zone_errors(token: str, zone_id: str, date_from: str, date_to: str) -> list[dict]:
    """Get HTTP status code breakdown for a zone."""
    query = """
    {
      viewer {
        zones(filter: {zoneTag: "%s"}) {
          httpRequests1dGroups(
            limit: 30
            filter: {date_geq: "%s", date_leq: "%s"}
            orderBy: [date_ASC]
          ) {
            dimensions { date }
            sum {
              responseStatusMap {
                edgeResponseStatus
                requests
              }
            }
          }
        }
      }
    }
    """ % (zone_id, date_from, date_to)

    resp = requests.post(GRAPHQL_URL, headers=_headers(token), json={"query": query}, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    zones = data.get("data", {}).get("viewer", {}).get("zones", [])
    if not zones:
        return []
    return zones[0].get("httpRequests1dGroups", [])


def get_zone_countries(token: str, zone_id: str, date_from: str, date_to: str) -> list[dict]:
    """Get top countries by requests for a zone."""
    query = """
    {
      viewer {
        zones(filter: {zoneTag: "%s"}) {
          httpRequests1dGroups(
            limit: 30
            filter: {date_geq: "%s", date_leq: "%s"}
          ) {
            sum {
              countryMap {
                clientCountryName
                requests
              }
            }
          }
        }
      }
    }
    """ % (zone_id, date_from, date_to)

    resp = requests.post(GRAPHQL_URL, headers=_headers(token), json={"query": query}, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    zones = data.get("data", {}).get("viewer", {}).get("zones", [])
    if not zones:
        return []

    # Aggregate countries across days
    country_totals = {}
    for day in zones[0].get("httpRequests1dGroups", []):
        for c in day.get("sum", {}).get("countryMap", []):
            name = c["clientCountryName"]
            country_totals[name] = country_totals.get(name, 0) + c["requests"]

    return sorted(
        [{"country": k, "requests": v} for k, v in country_totals.items()],
        key=lambda x: x["requests"],
        reverse=True,
    )


def get_ai_crawler_stats(token: str, zone_id: str, dt_from: str, dt_to: str) -> list[dict]:
    """Get AI crawler requests by user-agent pattern for a zone."""
    results = []
    for ua_pattern, label in AI_CRAWLERS:
        query = """
        {
          viewer {
            zones(filter: {zoneTag: "%s"}) {
              httpRequestsAdaptiveGroups(
                filter: {
                  datetime_geq: "%s"
                  datetime_leq: "%s"
                  requestSource: "eyeball"
                  userAgent_like: "%%%s%%"
                }
                limit: 1
              ) {
                count
                sum { edgeResponseBytes }
              }
            }
          }
        }
        """ % (zone_id, dt_from, dt_to, ua_pattern)

        try:
            resp = requests.post(GRAPHQL_URL, headers=_headers(token), json={"query": query}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            zones = data.get("data", {}).get("viewer", {}).get("zones", [])
            if zones:
                groups = zones[0].get("httpRequestsAdaptiveGroups", [])
                total = sum(g["count"] for g in groups)
                total_bytes = sum(g.get("sum", {}).get("edgeResponseBytes", 0) for g in groups)
                if total > 0:
                    results.append({
                        "crawler": label,
                        "ua_pattern": ua_pattern,
                        "requests": total,
                        "bytes": total_bytes,
                    })
        except Exception:
            continue

    return sorted(results, key=lambda x: x["requests"], reverse=True)


def get_ai_referral_traffic(token: str, zone_id: str, dt_from: str, dt_to: str) -> list[dict]:
    """Get traffic referred from AI platforms (ChatGPT, Perplexity, etc.)."""
    results = []
    for domain in AI_REFERRERS:
        query = """
        {
          viewer {
            zones(filter: {zoneTag: "%s"}) {
              httpRequestsAdaptiveGroups(
                filter: {
                  datetime_geq: "%s"
                  datetime_leq: "%s"
                  requestSource: "eyeball"
                  OR: [
                    {clientRefererHost: "%s"}
                    {clientRefererHost_like: "%%25.%s"}
                  ]
                }
                limit: 1
              ) {
                count
              }
            }
          }
        }
        """ % (zone_id, dt_from, dt_to, domain, domain)

        try:
            resp = requests.post(GRAPHQL_URL, headers=_headers(token), json={"query": query}, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            zones = data.get("data", {}).get("viewer", {}).get("zones", [])
            if zones:
                groups = zones[0].get("httpRequestsAdaptiveGroups", [])
                total = sum(g["count"] for g in groups)
                if total > 0:
                    results.append({"referrer": domain, "requests": total})
        except Exception:
            continue

    return sorted(results, key=lambda x: x["requests"], reverse=True)


def get_ai_top_paths(token: str, zone_id: str, dt_from: str, dt_to: str) -> list[dict]:
    """Get top paths requested by AI crawlers."""
    # Build OR filter for all AI crawler user agents
    ua_filters = " ".join(
        '{userAgent_like: "%%%s%%"}' % ua for ua, _ in AI_CRAWLERS[:10]
    )

    query = """
    {
      viewer {
        zones(filter: {zoneTag: "%s"}) {
          httpRequestsAdaptiveGroups(
            filter: {
              datetime_geq: "%s"
              datetime_leq: "%s"
              requestSource: "eyeball"
              OR: [%s]
            }
            limit: 20
            orderBy: [count_DESC]
          ) {
            count
            dimensions { clientRequestPath }
          }
        }
      }
    }
    """ % (zone_id, dt_from, dt_to, ua_filters)

    try:
        resp = requests.post(GRAPHQL_URL, headers=_headers(token), json={"query": query}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        zones = data.get("data", {}).get("viewer", {}).get("zones", [])
        if not zones:
            return []
        return [
            {"path": g["dimensions"]["clientRequestPath"], "requests": g["count"]}
            for g in zones[0].get("httpRequestsAdaptiveGroups", [])
            if g["count"] > 0
        ]
    except Exception:
        return []
