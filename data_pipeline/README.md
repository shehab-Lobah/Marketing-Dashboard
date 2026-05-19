# Samla Digital — Real-time Ad Data Pipeline

Pulls Google Ads, Meta Ads, LinkedIn Ads, and TikTok Ads totals into a single
JSON the dashboard consumes. Designed to run on a schedule.

## Setup (one-time)

```bash
cd "/Users/shehabeldin/Library/CloudStorage/Dropbox/Samla Digital/data_pipeline"
pip3 install --break-system-packages requests python-dotenv
cp .env.example .env
# edit .env and fill in real credentials
```

## Where to get each credential

**Google Ads**
1. Apply for a developer token: https://ads.google.com/aw/apicenter
2. Create OAuth credentials in Google Cloud Console (Web app type).
3. Mint a refresh token: easiest path is the OAuth Playground
   (https://developers.google.com/oauthplayground) with scope
   `https://www.googleapis.com/auth/adwords` and "Use your own credentials" checked.
4. Find your customer ID at the top of the Google Ads UI (e.g. `123-456-7890`).

**Meta Ads**
1. Open Business Manager → Business Settings → System Users → Add → Admin.
2. Generate Token, give it `ads_read` and `business_management` scopes.
3. Ad account id: in Ads Manager URL, `act_<digits>` is the value.

**LinkedIn Ads**
1. Create an app at https://www.linkedin.com/developers/apps.
2. Request products: "Advertising API" and "Marketing Developer Platform".
3. OAuth a user with scopes `r_ads`, `r_ads_reporting`.
4. Tokens last 60 days — re-mint via your app or `scripts/oauth_linkedin.py`.

**TikTok Ads**
1. Create a TikTok for Business app: https://business-api.tiktok.com/portal/.
2. OAuth in, exchange code for long-lived access token.
3. Advertiser ID is in the Ads Manager URL.

## Running

```bash
python3 fetch_ads.py
```

Writes `live_data.json` next to the script. Each platform is wrapped in
try/except — one missing/expired credential won't break the others.

## Schedule it

Use the workspace's scheduling capability to run `fetch_ads.py` every 30
minutes (or whatever cadence you want). The dashboard reads `live_data.json`
on load, so a fresher JSON = fresher numbers.

## Output shape

```json
{
  "generated_at": "2026-05-04T...",
  "totals": { "spend": 12345.67, "impressions": 9876543, ... },
  "platforms": {
    "google_ads":   { "status": "ok", "spend": ..., "impressions": ..., ... },
    "meta_ads":     { "status": "ok", ... },
    "linkedin_ads": { "status": "error", "error": "missing credentials in .env" },
    "tiktok_ads":   { "status": "ok", ... }
  }
}
```

The dashboard renders error platforms as "needs reconnect" badges so you can
see at a glance which credential is stale.
