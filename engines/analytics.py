"""Client for the superduper-analytics MCP server.

WHY THIS LIVES IN THE SEO CLI

`seo agent-audit` answers whether a page CAN be found and read. It cannot answer whether
anyone came, and a perfect score on a page nobody visits is not a result. This closes the
loop in one tool: audit the site, then ask the analytics what actually happened.

It speaks MCP rather than a private REST endpoint on purpose. The same server answers Claude
and ChatGPT, so there is one contract to keep working instead of two, and anything added for
an agent shows up here for free.

The server is deliberately blunt about uncertainty — it says when sampling was active and
labels the people figure a lower bound — and this client passes that through verbatim rather
than tidying it into a number that looks confident.
"""

import json
import urllib.error
import urllib.request

PROTOCOL_VERSION = "2025-11-25"
CLIENT = {"name": "seo-cli", "version": "1.0.0"}

# Cloudflare's Browser Integrity Check answers 403 with error 1010 to the default
# `Python-urllib/3.x` agent, so the first version of this client could not reach its own
# server while curl could. Any MCP client with an unfamiliar agent hits the same wall.
USER_AGENT = "seo-cli/1.0 (+https://github.com/fortunto2) MCP client"
TIMEOUT = 45


class AnalyticsError(RuntimeError):
    """Raised with a message meant for a human reading a terminal."""


def _rpc(url: str, key: str, method: str, params: dict | None = None, rid: int = 1) -> dict:
    body = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params is not None:
        body["params"] = params

    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {key}",
            "MCP-Protocol-Version": PROTOCOL_VERSION,
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read().decode()
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise AnalyticsError(
                "analytics rejected the key (401). Check `analytics.key` in config.yaml — it is "
                "the same DASHBOARD_KEY the dashboard uses."
            ) from exc
        raise AnalyticsError(f"analytics answered {exc.code}: {exc.read().decode()[:200]}") from exc
    except urllib.error.URLError as exc:
        raise AnalyticsError(f"could not reach {url}: {exc.reason}") from exc

    if not raw.strip():
        raise AnalyticsError(f"{method} returned an empty body")

    payload = json.loads(raw)
    if "error" in payload:
        raise AnalyticsError(f"{method}: {payload['error'].get('message', payload['error'])}")
    return payload.get("result", {})


def connect(url: str, key: str) -> dict:
    """Handshake first, like any MCP client. Also proves the server is the one we expect."""
    result = _rpc(url, key, "initialize", {
        "protocolVersion": PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": CLIENT,
    })
    # The notification is required by the lifecycle and answered with 202 and no body.
    try:
        _rpc(url, key, "notifications/initialized")
    except (AnalyticsError, json.JSONDecodeError):
        pass
    return result


def call_tool(url: str, key: str, name: str, arguments: dict | None = None) -> str:
    """Returns the tool's text verbatim. The server writes for a reader; do not reformat it."""
    result = _rpc(url, key, "tools/call", {"name": name, "arguments": arguments or {}}, rid=2)
    parts = [c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"]
    text = "\n".join(p for p in parts if p)
    if result.get("isError"):
        raise AnalyticsError(text or f"{name} failed without saying why")
    return text


def list_tools(url: str, key: str) -> list[dict]:
    return _rpc(url, key, "tools/list", rid=3).get("tools", [])


def config_from(cfg: dict) -> tuple[str, str]:
    """Reads `analytics.url` and `analytics.key`, failing with instructions rather than a KeyError."""
    section = cfg.get("analytics") or {}
    url = str(section.get("url") or "").rstrip("/")
    key = str(section.get("key") or "")
    if not url or not key:
        raise AnalyticsError(
            "analytics is not configured. Add to config.yaml:\n"
            "\n"
            "  analytics:\n"
            "    url: https://analytics.superduperai.co/mcp\n"
            "    key: <the DASHBOARD_KEY Worker secret>\n"
        )
    return url, key
