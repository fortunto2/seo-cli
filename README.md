# seo-cli

Unified search engine management CLI. One tool to manage all your sites across Google, Bing, Yandex, and IndexNow.

## What it does

```
seo status          Show all sites + engine connections
seo analytics       Search performance last 28 days (Google + Yandex)
seo inspect URL     Check if a page is indexed (Google)
seo reindex URL     Instant reindexing (Google Indexing API + IndexNow)
seo submit          Submit sitemaps to Google + Bing + Yandex
seo ping            IndexNow ping — notify Bing, Yandex, Naver, Seznam
seo add             Register all sites in all engines
```

## Setup

```bash
# Clone and install
git clone https://github.com/fortunto2/seo-cli.git
cd seo-cli
uv venv && uv pip install -e .

# Configure
cp config.example.yaml config.yaml
# Edit config.yaml with your credentials and sites
```

### Google Search Console

1. Create a [service account](https://console.cloud.google.com/iam-admin/serviceaccounts)
2. Enable [Search Console API](https://console.cloud.google.com/apis/library/searchconsole.googleapis.com)
3. Enable [Web Search Indexing API](https://console.cloud.google.com/apis/library/indexing.googleapis.com) (for `reindex` command)
4. Download the JSON key
5. Add the service account email as **Owner** in [Search Console](https://search.google.com/search-console) → Settings → Users

### IndexNow

1. Generate a key: `python -c "import secrets; print(secrets.token_hex(16))"`
2. Add it to `config.yaml`
3. Place a file named `{key}.txt` containing the key at each site's root (e.g. in `public/` for Next.js/Astro)

One POST to IndexNow notifies Bing, Yandex, Naver, and Seznam simultaneously.

### Bing (optional)

Get API key from [Bing Webmaster Tools](https://www.bing.com/webmasters) → Settings → API access.

### Yandex (optional)

1. Create an [OAuth app](https://oauth.yandex.com/client/new) with `webmaster:verify` and `webmaster:manage` scopes
2. Get token via `https://oauth.yandex.com/authorize?response_type=token&client_id=YOUR_CLIENT_ID`

## Usage

```bash
# Check what's connected
python cli.py status

# See search traffic
python cli.py analytics

# Published new content? Push it everywhere
python cli.py reindex https://mysite.com/new-post
python cli.py ping

# Submit sitemaps to all engines
python cli.py submit
```

## Engine coverage

| Command | Google | Bing | Yandex | Naver/Seznam |
|---------|--------|------|--------|--------------|
| `analytics` | Search Console | — | Webmaster API | — |
| `inspect` | URL Inspection | — | — | — |
| `reindex` | Indexing API | IndexNow | IndexNow | IndexNow |
| `submit` | Search Console | Webmaster API | Webmaster API | — |
| `ping` | — | IndexNow | IndexNow | IndexNow |

> **Note:** Google does not support IndexNow. Use `reindex` or `submit` for Google.

## License

MIT
