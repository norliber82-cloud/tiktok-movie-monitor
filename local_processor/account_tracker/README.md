# Account Tracker

Local-only runner that uses cookie-authenticated TikTok endpoints to:

1. Track newly-added follows on `@powerfuljourney` (US) and `@kariasxshf9` (JP)
2. Capture every newly-liked video and pull its author's profile
3. Find any followed creator who hits **1M+ plays in 3 days** and write to the main `videos` table
4. Recurse one level into peers' following lists, keeping `1-5w fans + 7-day-active` creators

## Why local, not GitHub Actions

Cookies have an IP fingerprint. Cloud runners trip risk control. **Run on the same machine where you exported the cookies.**

## Files on disk

- Cookies: `D:\搬运\.cookies\us.json`, `D:\搬运\.cookies\jp.json`
- State:   `D:\搬运\.account_state\{us|jp}_following.json`, `{us|jp}_liked_seen.json`

## Running

```cmd
:: Both regions, full pipeline (heavy — runs Playwright)
D:\搬运\.venv\Scripts\python.exe -m local_processor.account_tracker.account_runner

:: Only one region
D:\搬运\.venv\Scripts\python.exe -m local_processor.account_tracker.account_runner --only us

:: Skip the recursive discovery (cheaper)
D:\搬运\.venv\Scripts\python.exe -m local_processor.account_tracker.account_runner --skip-recurse

:: Dry-run: read everything, write nothing
D:\搬运\.venv\Scripts\python.exe -m local_processor.account_tracker.account_runner --dry-run
```

## Bitable destinations

| Job | Table | Field |
|---|---|---|
| `job_following_diff` | `tblRc6b9FrxMu4Gv` (following_creators) | 来源 = `following_us` / `following_jp` |
| `job_liked_videos` (videos) | `tblzY8kdXrffenE9` (liked_videos) | 来源账号 = `us` / `jp` |
| `job_liked_videos` (authors) | `tblRc6b9FrxMu4Gv` | 来源 = `liked_us` / `liked_jp` |
| `job_following_viral` | `BITABLE_VIDEOS_TABLE` (main) | 等级 = `RED`, 匹配标签 = `following_us`/`following_jp` |
| `job_recursive_discover` | `tblRc6b9FrxMu4Gv` | 来源 = `recurse_us` / `recurse_jp` |

## Rate-limit notes

TikTok soft-blocks after frequent follow-list calls — it returns HTTP 200 with an **empty body**. The runner detects this and stops paginating; just back off and try again later (typically an hour). Don't run more than 2-3 times a day on the same cookie set.

## Known limitations

- `get_liked_videos` only returns data if the account's likes are public.
- Pagination of `/api/user/list/` will repeat indefinitely if you trust `hasMore`; we dedupe by `uniqueId` and stop on no-progress.
- The `/api/post/item_list/` endpoint needs URL signing — we use `TikTokApi` (Playwright) for that. Requires `MS_TOKEN` in the env.
