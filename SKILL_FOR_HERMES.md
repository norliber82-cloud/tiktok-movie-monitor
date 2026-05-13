---
name: tiktok-movie-monitor
description: "Monitor TikTok & YouTube Shorts for viral movie-commentary videos, evaluate rising creators, push to Feishu + Bitable."
version: 1.0.0
author: norliber82-cloud
license: MIT
platforms: [linux, macos, windows]
prerequisites:
  commands: [gh]
metadata:
  hermes:
    tags: [tiktok, youtube, movie, film, monitoring, feishu, social-media]
    homepage: https://github.com/norliber82-cloud/tiktok-movie-monitor
---

# TikTok Movie Monitor

Repo: https://github.com/norliber82-cloud/tiktok-movie-monitor
Dashboard: https://norliber82-cloud.github.io/tiktok-movie-monitor/

## Quick Commands

```bash
# Check status
gh run list --workflow=monitor.yml --repo norliber82-cloud/tiktok-movie-monitor --limit 5

# Trigger scan
gh workflow run monitor.yml --repo norliber82-cloud/tiktok-movie-monitor
gh workflow run deep.yml --repo norliber82-cloud/tiktok-movie-monitor

# View logs
gh run view <RUN_ID> --repo norliber82-cloud/tiktok-movie-monitor --log

# Update msToken
gh secret set MS_TOKEN --repo norliber82-cloud/tiktok-movie-monitor
```

## System Overview

- Scans 27+ TikTok hashtags + 7 YouTube queries every 45 min
- 3-tier alerts: RED (1M+/3d), ORANGE (500K+/24h), YELLOW (200K+/12h)
- Auto-detects language (EN/JA/ZH)
- Evaluates rising creators (median 10K-100K plays + viral signal + vertical)
- Pushes to Feishu webhook + writes Bitable tables
- Static dashboard on GitHub Pages

## Maintenance

| Issue | Fix |
|---|---|
| No alerts | msToken expired → `gh secret set MS_TOKEN` |
| YouTube 0 hits | Check API quota at console.cloud.google.com |
| Bitable fails | Re-publish Feishu app at open.feishu.cn |

## Config

Edit `src/config.py` in the repo to change hashtags, thresholds, or timing.
