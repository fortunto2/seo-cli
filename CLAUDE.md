# SEO CLI

Unified search engine management CLI for all sites (Google, Bing, Yandex, IndexNow).

## Project Structure

```
seo-cli/
├── cli.py              # Main CLI entry point (all commands)
├── config.yaml         # Active config with API keys (gitignored)
├── config.example.yaml # Config template
├── engines/
│   ├── google_sc.py    # Google Search Console API (webmasters v3)
│   ├── bing.py         # Bing Webmaster Tools API
│   ├── yandex.py       # Yandex Webmaster API v4
│   └── indexnow.py     # IndexNow protocol (Bing+Yandex+Naver+Seznam)
├── pyproject.toml      # Python deps (requests, pyyaml, google-api-python-client)
└── .venv/              # Python 3.10 venv managed by uv
```

## Commands

```bash
cd /Users/rustam/startups/tools/seo-cli
.venv/bin/python cli.py status          # Show all sites + engine connections
.venv/bin/python cli.py analytics       # Search analytics last 28 days (Google + Yandex)
.venv/bin/python cli.py inspect URL     # Check indexing status of a URL (Google)
.venv/bin/python cli.py submit          # Submit sitemaps to Google + Bing + Yandex
.venv/bin/python cli.py ping            # IndexNow ping all sitemap URLs (instant Bing+Yandex)
.venv/bin/python cli.py add             # Register all sites in all engines
```

## Credentials

- **Google SA:** `~/.config/seo-cli/service-account.json`
- **IndexNow key:** in config.yaml, key file must be placed at each site's root
- **Bing/Yandex:** optional, keys go in config.yaml

## Key Details

- GSC properties can be `sc-domain:` or `https://` format — `_resolve_gsc_url()` in cli.py handles both automatically
- IndexNow sends one POST to api.indexnow.org which notifies Bing, Yandex, Naver, Seznam simultaneously
- Google is NOT part of IndexNow — use `submit` command for Google
- config.yaml is gitignored (contains secrets), config.example.yaml is committed

## Running

```bash
# Always use venv
.venv/bin/python cli.py <command>

# Or install as CLI tool
uv pip install -e .
seo <command>
```
