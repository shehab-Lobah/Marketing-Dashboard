# GitHub Actions auto-refresh — setup

This repo runs `data_pipeline/fetch_organic.py` every hour on a US-based GitHub
Actions runner. The fresh `live_organic_data.js` is committed back to the repo,
so the dashboard always has live numbers.

## Why GitHub Actions?

TikTok's WAF (slardar) was serving a bot challenge to requests from Saudi IPs,
so the fetcher couldn't read the profile page locally. GitHub-hosted runners
exit through US Azure IPs, which TikTok serves the normal page to — no code
change needed, just a different exit IP.

## One-time setup

### 1. Push this folder to a GitHub repo

```
cd "/Users/shehabeldin/Library/CloudStorage/Dropbox/Samla Digital"
git init
git add .
git commit -m "Initial commit — Samla Digital analytics dashboard"
git branch -M main
git remote add origin https://github.com/shehab-Lobah/Marketing-Dashboard.git
git push -u origin main
```

The `.gitignore` is already configured to keep `.env`, the real
`organic_config.json`, debug HTML, and old dashboard versions out.

### 2. Add the API keys as GitHub Secrets

In your repo → **Settings → Secrets and variables → Actions → New repository
secret**. Add each of these:

| Name              | Where to get it                                                | Required? |
|-------------------|----------------------------------------------------------------|-----------|
| `YT_API_KEY`      | Google Cloud Console → YouTube Data API v3 → Credentials       | yes (for YouTube) |
| `YT_CHANNEL_ID`   | YouTube channel URL → `/channel/UCxxxx...` part                | yes (for YouTube) |
| `TW_BEARER`       | developer.x.com → project → Bearer Token                       | optional  |
| `DISCORD_INVITE`  | invite code part of `discord.gg/<this>`                        | optional (defaults to `samla`) |
| `TIKTOK_USERNAME` | TikTok handle without the `@`                                  | optional (defaults to `samlagame`) |
| `STEAM_APPID`     | Steam store URL → `/app/<this>/...`                            | optional (defaults to `3988870`) |

You can copy the values directly from your local
`data_pipeline/organic_config.json` (the file with the real keys —
that file is gitignored, so it stays only on your Mac).

### 3. Enable Actions (if first time on this repo)

Repo → **Actions** tab → enable workflows if prompted.

### 4. Trigger a first run to verify

Repo → **Actions** → "Refresh organic data" → **Run workflow** → pick `main`
→ Run. After ~30 seconds you should see a green check and a new commit
`chore(data): hourly organic refresh [skip ci]` on `main`.

## Workflow cadence

Currently runs **every hour, on the hour (UTC)**.

To change frequency, edit `.github/workflows/refresh-organic.yml` — the
`cron:` line:

```yaml
- cron: "0 * * * *"      # every hour
- cron: "*/30 * * * *"   # every 30 min
- cron: "0 */6 * * *"    # every 6 hours
```

GitHub's cron has up to ~15 min jitter under heavy load — fine for our needs.

## Local runs still work

On your Mac you can still run the fetcher whenever:

```
python3 data_pipeline/fetch_organic.py
```

It reads `data_pipeline/organic_config.json` (the gitignored real-keys file).
If that file is missing, copy `organic_config.example.json` to
`organic_config.json` and fill in the keys.

## Pulling the latest data on the dashboard

The dashboard's `<script src="data_pipeline/live_organic_data.js">` tag reads
the local copy. To pick up the latest auto-refreshed data:

- **Option A:** `git pull` in this folder before opening the dashboard.
- **Option B:** click the "Refresh data" button in the sidebar — wired to
  fetch the latest `live_organic_data.js` from GitHub raw and update
  `window.SAMLA_ORGANIC` in place. Requires the dashboard to know your
  repo URL (set `window.SAMLA_REPO` near the top of `Samla_Dashboard_v5.html`
  — see comment block there).
