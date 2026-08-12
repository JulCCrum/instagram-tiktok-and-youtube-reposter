# Instagram-TikTok-YouTube Reposter

Part of the **Content System** — automated reel distribution pipeline.

## What it does

- Reposts reels from a queue to **YouTube**, **Instagram**, and **TikTok**
- Calls `videom8-analyzer` to analyze each reel (style, verdict, scores)
- Records metadata to Firestore (`content-engine-jpa` project)
- Enforces spacing (3-hour minimum between posts via cron)

## Runs on

**Mac mini** — `cron` every 3 hours (no timeout, reliable for long Videom8 analysis)

## Key files

- `main.py` — entry point; orchestrates repost-check → post → analyze → record
- `videom8_analyzer.py` — calls Cloud Run `videom8-api`, stores results
- `youtube_uploader.py` — uploads to YouTube (fixed: angle brackets in descriptions)
- `.env` — credentials (YouTube API key, Instagram/TikTok session tokens)
- `setup_cron.sh` — installs the 3-hour cron job

## Related projects

- **Content Engine** (`~/Projects/content-system/content-engine/`) — web app + daily stats crons
- **Reel Analyzer** (`~/Projects/content-system/reel-analyzer/`) — Videom8 backend on Cloud Run

## Notes

- After migration to Mac mini, venv paths were rebuilt to point to the new location
- Session tokens expire; re-run `main.py run` to refresh logins if the next cron fails
- The old Mac's cron should be disabled to avoid double-posting (remove the old crontab entry)
