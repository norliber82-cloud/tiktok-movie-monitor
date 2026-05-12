# TikTok Movie Monitor

Automatically monitor TikTok movie-commentary videos that hit **1M+ views within 3 days** of posting, and push alerts to **Feishu (Lark)**.

## Features

- Scans a curated pool of movie/film hashtags every ~45 minutes via GitHub Actions
- Filters by: posted ≤ 3 days ago, play count ≥ 1,000,000, movie-commentary keywords
- Deduplicates by `video_id` (SQLite)
- Sends structured cards to Feishu via a bot webhook
- 100% free to run (GitHub Actions + TikTok-Api unofficial wrapper)

## How it works

```
GitHub Actions cron  →  src/collector.py  (TikTok-Api + Playwright)
                   →  SQLite (videos.db, committed back to repo)
                   →  src/notifier.py     (Feishu webhook)
```

The SQLite DB is committed back to the repo between runs so we keep dedupe state across runs without needing external storage.

## Setup

### 1. Fork / create this repo on GitHub

Upload everything in this folder.

### 2. Get a TikTok `msToken`

1. Open Chrome in a normal window and go to `https://www.tiktok.com` (no login needed, but a US residential IP helps).
2. Open DevTools → Application → Cookies → `https://www.tiktok.com`.
3. Find the cookie named **`msToken`** and copy its value.

Note: `msToken` expires. If the job starts failing with "empty response", refresh it.

### 3. Create a Feishu custom bot

1. In your Feishu group chat: **Settings → Bots → Add Bot → Custom Bot**.
2. Copy the **Webhook URL**, e.g. `https://open.feishu.cn/open-apis/bot/v2/hook/xxxx-xxxx`.
3. Optional: enable **Signature verification**, copy the secret too.

### 4. Add GitHub repo secrets

Repo → Settings → Secrets and variables → Actions → New repository secret:

| Name | Value |
|---|---|
| `MS_TOKEN` | TikTok `msToken` cookie value |
| `FEISHU_WEBHOOK` | Feishu bot webhook URL |
| `FEISHU_SECRET` | (Optional) Feishu signature secret |

### 5. Enable the workflow

Actions tab → enable workflows → manually trigger `Monitor` once to verify.

After the first successful run, the cron schedule (every 45 min) takes over.

## Configuration

Edit `src/config.py` to tweak:

- `HASHTAGS` — hashtag pool to scan
- `KEYWORDS_IN` / `KEYWORDS_OUT` — caption filter
- `MIN_VIEWS` — view threshold (default 1,000,000)
- `WINDOW_DAYS` — posting-age window (default 3)
- `PER_TAG_LIMIT` — how many videos to fetch per hashtag per run

## Local dev

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
python -m playwright install chromium

set MS_TOKEN=xxx
set FEISHU_WEBHOOK=xxx
python -m src.main
```

## Legal note

TikTok's ToS prohibits automated scraping without authorization. This tool is intended for **personal research and trend monitoring**. Don't republish scraped content or resell the data.
