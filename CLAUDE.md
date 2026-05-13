# TikTok Movie Monitor — Claude Code Context

## What this project is

Automated monitoring system that scans TikTok and YouTube Shorts for viral movie-commentary videos, evaluates rising creators, and delivers alerts to Feishu + Bitable tables. Runs entirely on GitHub Actions (free, public repo).

## Repo

https://github.com/norliber82-cloud/tiktok-movie-monitor

## Quick commands

```bash
# Check recent runs
gh run list --workflow=monitor.yml --repo norliber82-cloud/tiktok-movie-monitor --limit 5
gh run list --workflow=deep.yml --repo norliber82-cloud/tiktok-movie-monitor --limit 5

# Trigger manually
gh workflow run monitor.yml --repo norliber82-cloud/tiktok-movie-monitor
gh workflow run deep.yml --repo norliber82-cloud/tiktok-movie-monitor

# View run logs
gh run view <RUN_ID> --repo norliber82-cloud/tiktok-movie-monitor --log

# Update msToken (when TikTok blocks requests)
gh secret set MS_TOKEN --repo norliber82-cloud/tiktok-movie-monitor

# Run locally
python -m src.main --mode fast
python -m src.main --mode deep
```

## Architecture

- `src/config.py` — all tunable params (hashtags, thresholds, timing)
- `src/collector.py` — TikTok-Api scraping (Phase A: primary scan, Phase B: discovery, Phase C: creator eval from local DB)
- `src/yt_collector.py` — YouTube Data API v3 collector
- `src/classifier.py` — movie-commentary detection + language + creator evaluation logic
- `src/db.py` — SQLite persistence with auto-migration
- `src/notifier.py` — Feishu webhook cards (3-tier video + creator)
- `src/bitable.py` — Feishu Bitable writer (auto-creates fields)
- `src/views.py` — One-shot script to create Bitable filtered views
- `src/main.py` — Entrypoint (`--mode fast` or `--mode deep`)
- `scripts/export_dashboard.py` — Bitable → JSON for GitHub Pages
- `dashboard/` — Static HTML/CSS/JS dashboard

## Workflows

| File | Schedule | What it does |
|---|---|---|
| `monitor.yml` | Every 45 min | Fast: TikTok scan + YT Shorts + notify + Bitable |
| `deep.yml` | Every hour (:20) | Deep: full scan + discovery + creator eval |
| `dashboard.yml` | Every 30 min | Export Bitable data → deploy GitHub Pages |

## GitHub Secrets

MS_TOKEN, FEISHU_WEBHOOK, FEISHU_APP_ID, FEISHU_APP_SECRET, BITABLE_APP_TOKEN, BITABLE_VIDEOS_TABLE, BITABLE_CREATORS_TABLE, YOUTUBE_API_KEY

## Key design decisions

- TikTok-Api uses `webkit` browser to bypass bot detection
- DB is stored in GitHub Actions cache (not committed to repo)
- Creator evaluation uses local DB aggregation (no extra API calls) because TikTok-Api's user().videos() is unreliable in headless CI
- YouTube uses official Data API v3 (10K free quota/day, we use ~300)
- Tier system: RED (1M+/3d), ORANGE (500K+/24h), YELLOW (200K+/12h)

## When things break

- "EmptyResponseException" → msToken expired, refresh it
- YouTube 0 hits → check API quota at console.cloud.google.com
- Bitable write fails → check app publish status on open.feishu.cn
- Run timeout → usually GitHub runner slowness, will self-recover next run
