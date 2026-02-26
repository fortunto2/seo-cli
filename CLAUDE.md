# SEO CLI

Unified search engine management CLI for all sites (Google, Bing, Yandex, IndexNow, Cloudflare).

## Project Structure

```
seo-cli/
├── cli.py              # Main CLI entry point (all commands)
├── config.yaml         # Active config with API keys (gitignored)
├── config.example.yaml # Config template
├── engines/
│   ├── google_sc.py    # Google Search Console API (webmasters v3)
│   ├── google_indexing.py # Google Indexing API (instant reindex)
│   ├── bing.py         # Bing Webmaster Tools API
│   ├── yandex.py       # Yandex Webmaster API v4
│   ├── indexnow.py     # IndexNow protocol (Bing+Yandex+Naver+Seznam)
│   ├── cloudflare.py   # Cloudflare Analytics GraphQL (traffic, errors, AI crawlers)
│   ├── audit.py        # Page SEO + GEO audit (meta, schema, speed, keywords)
│   ├── keywords.py     # Google Autocomplete keyword suggestions
│   ├── serp.py         # Google SERP scraping + competitor SEO extraction
│   └── storage.py      # Local JSON persistence (~/.config/seo-cli/data/)
├── pyproject.toml      # Python deps (requests, pyyaml, google-api-python-client)
└── .venv/              # Python 3.10 venv managed by uv
```

## Commands

```bash
seo status              # Show all sites + engine connections
seo analytics           # Search analytics last 28 days (Google + Yandex)
seo inspect URL         # Check indexing status of a URL (Google)
seo reindex URL         # Instant reindexing (Google Indexing API + IndexNow)
seo submit              # Submit sitemaps to Google + Bing + Yandex
seo ping                # IndexNow ping all sitemap URLs (instant Bing+Yandex)
seo add                 # Register all sites in all engines
seo launch [SITE]       # New site promotion (add + submit + ping + audit)
seo audit [URL]         # Page SEO + GEO audit (meta, schema, speed, keywords)
seo report              # Analytics report with delta comparison
seo competitors QUERY   # Competitor & keyword analysis for a query
seo keywords QUERY      # Google Autocomplete keyword suggestions
seo monitor             # Position tracking (saves snapshots, shows deltas)
seo improve [URL]       # Audit→fix cycle with priority tracking
seo traffic             # Cloudflare traffic analytics (requests, errors, countries)
seo crawlers            # AI crawler stats (GPTBot, ClaudeBot, etc.) via Cloudflare
```

## Credentials

- **Google SA:** `~/.config/seo-cli/service-account.json`
- **IndexNow key:** in config.yaml, key file must be placed at each site's root
- **Cloudflare:** API token in config.yaml (needs Zone > Analytics > Read; add Zone > DNS > Read for DNS access)
- **Bing/Yandex:** optional, keys go in config.yaml

## Key Details

- GSC properties can be `sc-domain:` or `https://` format — `_resolve_gsc_url()` in cli.py handles both automatically
- IndexNow sends one POST to api.indexnow.org which notifies Bing, Yandex, Naver, Seznam simultaneously
- Google is NOT part of IndexNow — use `submit` or `reindex` command for Google
- Cloudflare token (Analytics Read) cannot manage DNS — needs separate DNS Read/Edit permissions for that
- config.yaml is gitignored (contains secrets), config.example.yaml is committed

## Running

```bash
# Always use venv
.venv/bin/python cli.py <command>

# Or install as CLI tool
uv pip install -e .
seo <command>
```
