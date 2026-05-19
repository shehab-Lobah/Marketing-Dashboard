#!/usr/bin/env python3
"""
Samla Digital — Organic Social Media Fetcher
=============================================
Fetches real-time organic metrics for all tracked platforms:
  - Discord  (public invite API — no auth needed)
  - YouTube  (YouTube Data API v3 — free API key required)
  - X/Twitter (Twitter API v2 — free tier bearer token)
  - TikTok   (public profile scraping via unofficial endpoint)
  - Steam    (SteamSpy public API)

Output: data_pipeline/live_organic_data.js
Usage:  python3 data_pipeline/fetch_organic.py
Schedule: add to crontab — see bottom of this file
"""
import json
import os
import re
import time
import requests
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).parent
CONFIG_PATH = HERE / "organic_config.json"
OUTPUT_PATH = HERE / "live_organic_data.js"

HEADERS = {"User-Agent": "SamlaAnalytics/1.0"}

def load_config():
    """Load config, creating a template if it doesn't exist."""
    default = {
        "discord":  { "invite_code": "samla" },
        "youtube":  { "channel_id": "UCxxx",  "api_key": "" },
        "twitter":  { "username": "SamlaGame", "bearer_token": "" },
        "tiktok":   { "username": "samlagame" },
        "steam":    { "appid": "3988870" }
    }
    if not CONFIG_PATH.exists():
        with open(CONFIG_PATH, "w") as f:
            json.dump(default, f, indent=2)
        print(f"Created config template at {CONFIG_PATH} — fill in your API keys!")
        return default
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    # Merge defaults for any missing keys
    for k, v in default.items():
        if k not in cfg:
            cfg[k] = v
    return cfg


# ─── DISCORD ──────────────────────────────────────────────────────────────────
def fetch_discord(cfg):
    invite = cfg.get("invite_code", "samla")
    try:
        r = requests.get(
            f"https://discord.com/api/v9/invites/{invite}?with_counts=true",
            headers=HEADERS, timeout=10
        )
        d = r.json()
        members = d.get("approximate_member_count", 0)
        online  = d.get("approximate_presence_count", 0)
        guild   = d.get("guild", {})
        return {
            "status":  "success",
            "members": members,
            "online":  online,
            "name":    guild.get("name", ""),
            "invite":  invite,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ─── YOUTUBE (comprehensive) ─────────────────────────────────────────────────
def _yt_parse_duration(iso_dur):
    """Convert ISO 8601 duration (PT1H2M3S) to seconds."""
    if not iso_dur:
        return 0
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_dur)
    if not m:
        return 0
    h, mi, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + s

def _yt_fmt_duration(secs):
    """Format seconds to human-readable string like '1:34' or '0:18'."""
    if secs <= 0:
        return "0:00"
    m, s = divmod(secs, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def fetch_youtube(cfg):
    api_key    = cfg.get("api_key", "")
    channel_id = cfg.get("channel_id", "")
    if not api_key:
        return {"status": "no_key", "note": "Add youtube.api_key to organic_config.json"}
    if not channel_id or channel_id == "UCxxx":
        return {"status": "no_channel", "note": "Add youtube.channel_id to organic_config.json"}

    base = "https://www.googleapis.com/youtube/v3"

    try:
        # ── 1) Channel info: snippet + statistics + contentDetails + brandingSettings ──
        ch_url = (
            f"{base}/channels"
            f"?part=snippet,statistics,contentDetails,brandingSettings"
            f"&id={channel_id}&key={api_key}"
        )
        ch_r = requests.get(ch_url, headers=HEADERS, timeout=10)
        ch_d = ch_r.json()
        if ch_d.get("error"):
            return {"status": "error", "error": ch_d["error"].get("message", "API error")}

        items = ch_d.get("items", [])
        if not items:
            return {"status": "error", "error": "Channel not found"}

        ch = items[0]
        stats   = ch.get("statistics", {})
        snippet = ch.get("snippet", {})
        content = ch.get("contentDetails", {})
        branding = ch.get("brandingSettings", {})

        subscribers  = int(stats.get("subscriberCount", 0))
        total_views  = int(stats.get("viewCount", 0))
        video_count  = int(stats.get("videoCount", 0))
        channel_name = snippet.get("title", "")
        channel_desc = snippet.get("description", "")
        custom_url   = snippet.get("customUrl", "")
        country      = snippet.get("country", "")
        profile_pic  = snippet.get("thumbnails", {}).get("high", {}).get("url", "")
        created_at   = snippet.get("publishedAt", "")
        banner_url   = branding.get("image", {}).get("bannerExternalUrl", "")

        # Get uploads playlist ID
        uploads_playlist = content.get("relatedPlaylists", {}).get("uploads", "")

        result = {
            "status":           "success",
            "subscribers":      subscribers,
            "total_views":      total_views,
            "video_count":      video_count,
            "channel_name":     channel_name,
            "channel_description": channel_desc[:300] if channel_desc else "",
            "channel_url":      f"https://youtube.com/{custom_url}" if custom_url else f"https://youtube.com/channel/{channel_id}",
            "custom_url":       custom_url,
            "country":          country,
            "profile_pic":      profile_pic,
            "banner_url":       banner_url,
            "created_at":       created_at,
            "videos":           [],
            "total_likes":      0,
            "total_comments":   0,
            "total_watch_time_seconds": 0,
            "avg_views_per_video": 0,
        }

        # ── 2) Fetch all video IDs from uploads playlist ──────────────────────
        if not uploads_playlist:
            print("    ⚠ No uploads playlist found — skipping video details")
            return result

        video_ids = []
        next_page = None
        max_pages = 3  # Max 150 videos (50 per page) — more than enough

        for _ in range(max_pages):
            pl_url = (
                f"{base}/playlistItems"
                f"?part=snippet&playlistId={uploads_playlist}"
                f"&maxResults=50&key={api_key}"
            )
            if next_page:
                pl_url += f"&pageToken={next_page}"

            pl_r = requests.get(pl_url, headers=HEADERS, timeout=10)
            pl_d = pl_r.json()
            if pl_d.get("error"):
                print(f"    ⚠ Playlist error: {pl_d['error'].get('message', '')}")
                break

            for item in pl_d.get("items", []):
                vid_id = item.get("snippet", {}).get("resourceId", {}).get("videoId", "")
                if vid_id:
                    video_ids.append(vid_id)

            next_page = pl_d.get("nextPageToken")
            if not next_page:
                break

        print(f"    Found {len(video_ids)} videos in uploads playlist")

        # ── 3) Fetch video details (statistics + snippet + contentDetails) ────
        if video_ids:
            videos_data = []
            # Process in batches of 50
            for i in range(0, len(video_ids), 50):
                batch = video_ids[i:i+50]
                vid_url = (
                    f"{base}/videos"
                    f"?part=snippet,statistics,contentDetails"
                    f"&id={','.join(batch)}&key={api_key}"
                )
                vid_r = requests.get(vid_url, headers=HEADERS, timeout=10)
                vid_d = vid_r.json()
                if vid_d.get("error"):
                    print(f"    ⚠ Video batch error: {vid_d['error'].get('message', '')}")
                    continue

                for v in vid_d.get("items", []):
                    v_snippet = v.get("snippet", {})
                    v_stats   = v.get("statistics", {})
                    v_content = v.get("contentDetails", {})

                    views    = int(v_stats.get("viewCount", 0))
                    likes    = int(v_stats.get("likeCount", 0))
                    comments = int(v_stats.get("commentCount", 0))
                    duration_s = _yt_parse_duration(v_content.get("duration", ""))

                    # Thumbnail: prefer maxres, fall back to high, medium, default
                    thumbs = v_snippet.get("thumbnails", {})
                    thumb_url = (
                        thumbs.get("maxres", {}).get("url") or
                        thumbs.get("high", {}).get("url") or
                        thumbs.get("medium", {}).get("url") or
                        thumbs.get("default", {}).get("url", "")
                    )

                    videos_data.append({
                        "id":            v.get("id", ""),
                        "title":         v_snippet.get("title", ""),
                        "published":     v_snippet.get("publishedAt", ""),
                        "thumbnail":     thumb_url,
                        "views":         views,
                        "likes":         likes,
                        "comments":      comments,
                        "duration_s":    duration_s,
                        "duration":      _yt_fmt_duration(duration_s),
                        "description":   v_snippet.get("description", "")[:200],
                    })

            # Sort by views descending
            videos_data.sort(key=lambda x: x["views"], reverse=True)

            total_likes = sum(v["likes"] for v in videos_data)
            total_comments = sum(v["comments"] for v in videos_data)
            total_duration = sum(v["duration_s"] for v in videos_data)
            total_vid_views = sum(v["views"] for v in videos_data)
            avg_views = round(total_vid_views / len(videos_data)) if videos_data else 0

            # Estimate total watch time: views * avg_duration * avg_retention (assume 70%)
            avg_duration = total_duration / len(videos_data) if videos_data else 0
            est_watch_time = int(total_vid_views * avg_duration * 0.70)

            result["videos"] = videos_data
            result["total_likes"] = total_likes
            result["total_comments"] = total_comments
            result["total_watch_time_seconds"] = est_watch_time
            result["avg_views_per_video"] = avg_views

        return result

    except Exception as e:
        return {"status": "error", "error": str(e)}


# ─── TWITTER / X ──────────────────────────────────────────────────────────────
def fetch_twitter(cfg):
    bearer = cfg.get("bearer_token", "")
    username = cfg.get("username", "SamlaGame")
    if not bearer:
        return {"status": "no_key", "note": "Add twitter.bearer_token to organic_config.json"}
    try:
        url = f"https://api.twitter.com/2/users/by/username/{username}?user.fields=public_metrics"
        r = requests.get(
            url,
            headers={**HEADERS, "Authorization": f"Bearer {bearer}"},
            timeout=10
        )
        d = r.json()
        if "errors" in d:
            return {"status": "error", "error": d["errors"][0].get("detail", "API error")}
        metrics = d.get("data", {}).get("public_metrics", {})
        return {
            "status":    "success",
            "followers": metrics.get("followers_count", 0),
            "following": metrics.get("following_count", 0),
            "tweets":    metrics.get("tweet_count", 0),
            "username":  username,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ─── TIKTOK (unofficial public endpoint) ──────────────────────────────────────
def fetch_tiktok(cfg):
    """
    Fetch TikTok user stats by scraping the profile page's embedded JSON.

    TikTok's /api/user/detail endpoint requires a signed X-Bogus param, so we
    fetch the public profile HTML and extract the embedded JSON instead.

    Strategy (in order):
      1. Warm a requests.Session by hitting tiktok.com home first so we collect
         the ms_token / tt_csrf_token / ttwid cookies. TikTok serves a consent
         wall to cookie-less clients.
      2. GET the profile page with the warm session.
      3. Try three known JSON locators (modern, SIGI legacy, __NEXT_DATA__).
      4. If none match, do a permissive sweep — any application/json <script>
         block containing both "userInfo" and "followerCount".
      5. Fall back to TikTok's official oEmbed for at least confirming the user
         exists (limited fields — title + author).
      6. On total failure, dump raw HTML to data_pipeline/_tiktok_debug.html
         so we can inspect what TikTok actually served.
    """
    username = cfg.get("username", "samlagame").lstrip("@")
    profile_url = f"https://www.tiktok.com/@{username}"

    browser_headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        # NOTE: deliberately NOT advertising brotli ("br") here.
        # `requests` only auto-decodes gzip/deflate; if the server returns brotli
        # the body comes through as raw compressed bytes that `r.text` then
        # misinterprets as UTF-8 (we hit this — _tiktok_debug.html was full of
        # decoding garbage). Pinning to gzip/deflate fixes it without adding
        # the optional `brotli` Python package as a dependency.
        "Accept-Encoding": "gzip, deflate",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": '"Google Chrome";v="126", "Chromium";v="126", "Not-A.Brand";v="99"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"macOS"',
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Upgrade-Insecure-Requests": "1",
    }

    try:
        session = requests.Session()
        session.headers.update(browser_headers)

        # 1) Cookie warmup — visit homepage so TikTok sets ms_token/ttwid
        try:
            session.get("https://www.tiktok.com/", timeout=10)
        except requests.exceptions.RequestException:
            pass  # warmup is best-effort; profile fetch can still succeed without it

        # 2) Fetch profile page (Sec-Fetch-Site flips to same-origin after warmup)
        headers2 = {"Sec-Fetch-Site": "same-origin", "Referer": "https://www.tiktok.com/"}
        r = session.get(profile_url, headers=headers2, timeout=15)
        if r.status_code != 200:
            return {"status": "error", "error": f"HTTP {r.status_code}"}
        html = r.text

        # 3) Known locators
        patterns = [
            r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
            r'<script id="SIGI_STATE" type="application/json">(.*?)</script>',
            r'<script id="__NEXT_DATA__" type="application/json"[^>]*>(.*?)</script>',
        ]
        payload = None
        for pat in patterns:
            m = re.search(pat, html, re.DOTALL)
            if m:
                try:
                    payload = json.loads(m.group(1))
                    break
                except json.JSONDecodeError:
                    continue

        # 4) Permissive sweep — any JSON script block with the stats we want
        if not payload:
            for blob in re.finditer(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', html, re.DOTALL):
                txt = blob.group(1)
                if 'followerCount' in txt and 'userInfo' in txt:
                    try:
                        payload = json.loads(txt)
                        break
                    except json.JSONDecodeError:
                        continue

        # 5) Walk known shapes
        user_info = None
        if payload:
            if "__DEFAULT_SCOPE__" in payload:
                user_info = (
                    payload.get("__DEFAULT_SCOPE__", {})
                    .get("webapp.user-detail", {})
                    .get("userInfo")
                )
            elif "UserModule" in payload:
                users = payload.get("UserModule", {}).get("users", {})
                stats_all = payload.get("UserModule", {}).get("stats", {})
                user_obj = users.get(username) or (next(iter(users.values()), None) if users else None)
                stats_obj = stats_all.get(username) or (next(iter(stats_all.values()), None) if stats_all else None)
                if user_obj:
                    user_info = {"user": user_obj, "stats": stats_obj or {}}
            elif "props" in payload:
                user_info = (
                    payload.get("props", {})
                    .get("pageProps", {})
                    .get("userInfo")
                )

        if user_info:
            user = user_info.get("user", {})
            stats = user_info.get("stats") or user_info.get("statsV2") or {}

            def i(v):
                try:
                    return int(v) if v is not None else 0
                except (TypeError, ValueError):
                    return 0

            return {
                "status":       "success",
                "source":       "profile_page",
                "username":     user.get("uniqueId") or username,
                "display_name": user.get("nickname"),
                "verified":     bool(user.get("verified")),
                "bio":          user.get("signature"),
                "profile_pic":  user.get("avatarLarger") or user.get("avatarMedium"),
                "followers":    i(stats.get("followerCount")),
                "following":    i(stats.get("followingCount")),
                "likes":        i(stats.get("heartCount") or stats.get("heart")),
                "videos":       i(stats.get("videoCount")),
                "friends":      i(stats.get("friendCount")),
                "profile_url":  profile_url,
            }

        # 6) Fallback — TikTok official oEmbed (limited fields, but confirms account)
        try:
            oe = requests.get(
                "https://www.tiktok.com/oembed",
                params={"url": profile_url},
                headers={"User-Agent": browser_headers["User-Agent"]},
                timeout=10,
            )
            if oe.status_code == 200 and oe.headers.get("content-type", "").startswith("application/json"):
                oj = oe.json()
                if oj.get("title") or oj.get("author_name"):
                    # Dump HTML for later inspection but return at least a minimal record
                    dbg = HERE / "_tiktok_debug.html"
                    dbg.write_text(html[:200000])  # cap the dump size
                    return {
                        "status":       "partial",
                        "source":       "oembed",
                        "username":     oj.get("author_unique_id") or username,
                        "display_name": oj.get("author_name"),
                        "profile_url":  profile_url,
                        "note":         "Profile page parse failed — used oEmbed fallback. See _tiktok_debug.html for raw page.",
                    }
        except Exception:
            pass

        # 7) Total failure — dump for inspection
        dbg = HERE / "_tiktok_debug.html"
        dbg.write_text(html[:200000])
        return {
            "status": "error",
            "error":  "no embedded JSON found and oEmbed fallback failed — check _tiktok_debug.html",
            "html_chars": len(html),
        }

    except requests.exceptions.RequestException as e:
        return {"status": "error", "error": f"network: {e}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ─── STEAM (SteamSpy public API) ──────────────────────────────────────────────
def fetch_steam(cfg):
    appid = cfg.get("appid", "3988870")
    try:
        r = requests.get(
            f"https://steamspy.com/api.php?request=appdetails&appid={appid}",
            headers=HEADERS, timeout=10
        )
        d = r.json()
        followers = d.get("followers", 0)
        return {
            "status":       "success",
            "followers":    followers,
            "owners":       d.get("owners", "0"),
            "name":         d.get("name", ""),
            "average_2weeks": d.get("average_2weeks", 0),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("Samla Organic Data Fetcher — Starting...")
    print("=" * 55)

    cfg = load_config()
    now = time.time()
    ts  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print(f"[{ts}] Fetching all platforms...")

    results = {
        "_meta": {
            "updated_at": now,
            "timestamp":  ts,
            "version":    "3.0"
        }
    }

    platforms = {
        "discord": (fetch_discord, cfg.get("discord", {})),
        "youtube": (fetch_youtube, cfg.get("youtube", {})),
        "twitter": (fetch_twitter, cfg.get("twitter", {})),
        "tiktok":  (fetch_tiktok,  cfg.get("tiktok",  {})),
        "steam":   (fetch_steam,   cfg.get("steam",   {})),
    }

    for name, (fn, pcfg) in platforms.items():
        try:
            result = fn(pcfg)
            results[name] = result
            status = result.get("status", "?")
            if status == "success":
                extra = ""
                if name == "youtube" and result.get("videos"):
                    extra = f" ({len(result['videos'])} videos, {result.get('total_views', 0):,} total views)"
                print(f"  ✓ {name.capitalize():12s} — OK{extra}")
            elif status == "no_key":
                print(f"  ⚠ {name.capitalize():12s} — No API key")
            else:
                print(f"  ✗ {name.capitalize():12s} — {result.get('error', status)}")
        except Exception as e:
            results[name] = {"status": "error", "error": str(e)}
            print(f"  ✗ {name.capitalize():12s} — Exception: {e}")

    js = f"window.SAMLA_ORGANIC = {json.dumps(results, indent=2)};\nconsole.info('[Samla] Organic data loaded — {ts}');\n"

    with open(OUTPUT_PATH, "w") as f:
        f.write(js)

    print("-" * 55)
    print(f"✓ Written to {OUTPUT_PATH}")
    print()
    print("To run every hour, add this to crontab (crontab -e):")
    print(f'  0 * * * * cd "{HERE.parent}" && python3 data_pipeline/fetch_organic.py >> /tmp/samla_organic.log 2>&1')


if __name__ == "__main__":
    main()
