# seo-cli

Unified search engine management CLI. One tool to manage all your sites across Google, Bing, Yandex, IndexNow, and Cloudflare.

## What it does

```
seo status              Dashboard: GSC, GA, Cloudflare, hosting at a glance
seo analytics           Search queries from GSC + Yandex
seo ga                  Google Analytics: sessions, pages, channels, countries
seo traffic             Cloudflare: pageviews, uniques, bandwidth, bot/human split
seo compare             GA vs Cloudflare: real users vs bots, landing pages, AI referrals
seo crawlers            AI crawler stats: GPTBot, ClaudeBot, trends, referral ROI
seo inspect URL         Check indexing status (Google)
seo reindex URL         Instant reindexing (Google Indexing API + IndexNow)
seo submit              Submit sitemaps to Google + Bing + Yandex
seo ping                IndexNow ping (Bing + Yandex + Naver + Seznam)
seo add                 Register all sites in all engines
seo launch [SITE]       New site promotion (add + submit + ping + audit)
seo audit [URL]         SEO + GEO audit (meta, schema, speed, keywords, llms.txt)
seo improve [URL]       Audit → fix cycle with priority tracking
seo report              Analytics report with delta comparison
seo monitor             Position tracking with snapshots and deltas
seo competitors QUERY   SERP analysis + competitor SEO extraction
seo keywords QUERY      Google Autocomplete keyword suggestions
```

## Install

```bash
git clone https://github.com/fortunto2/seo-cli.git
cd seo-cli
uv venv && uv pip install -e .

cp config.example.yaml config.yaml
# Edit config.yaml — add your credentials and sites
```

## Setup credentials

### Google Service Account (required for GSC, GA, Indexing)

One service account handles Search Console, Analytics, and Indexing API.

**Step 1 — Create service account:**

1. Go to [Google Cloud Console → IAM → Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
2. Select your project (or create one)
3. Click **Create Service Account**
4. Name: `seo-cli`, click **Create and Continue**
5. Skip role assignment, click **Done**
6. Click on the created account → **Keys** tab → **Add Key** → **Create new key** → **JSON**
7. Save the downloaded file to `~/.config/seo-cli/service-account.json`

**Step 2 — Enable APIs:**

Enable each API by clicking the link and pressing **Enable**:

- [Search Console API](https://console.cloud.google.com/apis/library/searchconsole.googleapis.com) — for `analytics`, `inspect`, `submit`
- [Web Search Indexing API](https://console.cloud.google.com/apis/library/indexing.googleapis.com) — for `reindex`
- [Google Analytics Data API](https://console.cloud.google.com/apis/library/analyticsdata.googleapis.com) — for `ga`, `compare`
- [Google Analytics Admin API](https://console.cloud.google.com/apis/library/analyticsadmin.googleapis.com) — for listing GA properties

**Step 3 — Grant access:**

- **Search Console:** Go to [Search Console](https://search.google.com/search-console) → Settings → Users and permissions → **Add user** → paste the service account email (looks like `seo-cli@project-id.iam.gserviceaccount.com`) → set permission to **Owner**
- **Google Analytics:** Go to [Google Analytics](https://analytics.google.com) → Admin → Property → Property Access Management → **Add users** → paste the service account email → set role to **Viewer** (or Editor if you want to configure)

**Step 4 — Config:**

```yaml
google:
  service_account_file: "~/.config/seo-cli/service-account.json"
```

Find your GA4 property ID: Analytics → Admin → Property Settings → **Property ID** (numeric). Add it to each site:

```yaml
sites:
  - url: "https://example.com"
    name: "MySite"
    ga_property_id: "374549185"
```

### Cloudflare

**Step 1 — Create API token:**

1. Go to [Cloudflare API Tokens](https://dash.cloudflare.com/profile/api-tokens)
2. Click **Create Token**
3. Use **Custom token** template
4. Permissions:
   - **Zone → Analytics → Read** — for `traffic`, `crawlers`, `compare`
   - **Zone → DNS → Read** (optional) — for DNS visibility
5. Zone Resources: **Include → All zones** (or select specific zones)
6. Click **Continue to summary** → **Create Token**
7. Copy the token

**Step 2 — Config:**

```yaml
cloudflare:
  api_token: "your-token-here"
```

### IndexNow

IndexNow notifies Bing, Yandex, Naver, and Seznam simultaneously with one POST request. Google does NOT support IndexNow — use `reindex` or `submit` for Google.

**Step 1 — Generate key:**

```bash
python -c "import secrets; print(secrets.token_hex(16))"
```

**Step 2 — Place key file on each site:**

Create a file named `{key}.txt` containing the key at each site's root:
- **Next.js:** `public/{key}.txt`
- **Astro:** `public/{key}.txt`
- **Static:** root directory `{key}.txt`

Verify it's accessible: `curl https://yoursite.com/{key}.txt`

**Step 3 — Config:**

```yaml
indexnow:
  key: "your-generated-key"
```

### Bing Webmaster (optional)

1. Go to [Bing Webmaster Tools](https://www.bing.com/webmasters) → Settings → API access
2. Copy API key

```yaml
bing:
  api_key: "your-key"
```

### Yandex Webmaster (optional)

1. Create an [OAuth app](https://oauth.yandex.com/client/new):
   - Redirect URI: `https://oauth.yandex.com/verification_code`
   - Scopes: `webmaster:verify`, `webmaster:manage`
2. Get token: visit `https://oauth.yandex.com/authorize?response_type=token&client_id=YOUR_CLIENT_ID`

```yaml
yandex:
  oauth_token: "your-token"
```

## Site config

```yaml
sites:
  - url: "https://example.com"
    sitemap: "https://example.com/sitemap.xml"
    name: "MySite"
    path: "/path/to/local/repo"          # optional, for audit/improve
    github: "user/repo"                   # optional
    framework: "nextjs"                   # optional: nextjs, astro
    hosting: "vercel"                     # optional: vercel, cloudflare, gcp
    ga_property_id: "374549185"           # optional, for ga/compare
    ssh: "user@host"                      # optional, for remote access
```

## Usage

```bash
# Dashboard — see everything at a glance
seo status

# Search analytics
seo analytics --days 7

# Google Analytics
seo ga --days 28 --site MySite

# Compare real users (GA) vs all traffic (CF)
seo compare --site MySite --days 7

# Who's crawling your site?
seo crawlers --days 7

# Published new content? Push it everywhere
seo reindex https://mysite.com/new-post
seo ping

# Launch a new site (add + submit + ping + audit)
seo launch MySite

# SEO audit (works without config too)
seo audit https://any-site.com/page

# Keyword research
seo keywords "best ai tools"
```

## Engine coverage

| Command | Google | Bing | Yandex | Naver/Seznam | Cloudflare | GA4 |
|---------|--------|------|--------|--------------|------------|-----|
| `status` | GSC | — | — | — | zones | overview |
| `analytics` | Search Console | — | Webmaster API | — | — | — |
| `ga` | — | — | — | — | — | Data API |
| `traffic` | — | — | — | — | GraphQL | — |
| `compare` | Search Console | — | — | — | GraphQL + Bot Mgmt | Data API |
| `crawlers` | — | — | — | — | GraphQL | — |
| `inspect` | URL Inspection | — | — | — | — | — |
| `reindex` | Indexing API | IndexNow | IndexNow | IndexNow | — | — |
| `submit` | Search Console | Webmaster API | Webmaster API | — | — | — |
| `ping` | — | IndexNow | IndexNow | IndexNow | — | — |
| `audit` | PageSpeed API | — | — | — | — | — |

> **Note:** Google does not support IndexNow. Use `reindex` or `submit` for Google.

## License

MIT
