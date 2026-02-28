# Instagram to TikTok & YouTube Reposter

Automatically repost your Instagram Reels to TikTok and YouTube Shorts. Download once, schedule uploads to both platforms, and let them publish automatically.

## Features

- **Download Instagram Reels** - Scrapes your profile and downloads all video content
- **Upload to YouTube Shorts** - Uses YouTube Data API with scheduling support
- **Upload to TikTok** - Browser automation with scheduling support
- **Progress Tracking** - Remembers what's been downloaded and uploaded (per-platform)
- **Scheduled Publishing** - Schedule posts to publish automatically (no computer needed)
- **Caption Preservation** - Copies captions and hashtags from Instagram
- **Configurable Schedule** - Choose how many posts per day and which platforms
- **Dry Run Mode** - Preview what would happen without actually posting
- **Setup Verification** - `python main.py test` checks everything before you start

## One-Line Setup

### Mac / Linux

```bash
bash <(curl -sSL https://raw.githubusercontent.com/JulCCrum/instagram-tiktok-and-youtube-reposter/main/setup.sh)
```

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/JulCCrum/instagram-tiktok-and-youtube-reposter/main/setup_windows.ps1 | iex
```

This will:
1. Install Python, ffmpeg, and yt-dlp (if missing)
2. Clone the repo and set up a virtual environment
3. Install all Python dependencies and Playwright browsers
4. Walk you through an **interactive configuration wizard** — pick your platforms, enter credentials, set posting frequency, and optionally set up automatic scheduling

After the wizard finishes, follow the on-screen next steps.

## Manual Setup

If you prefer to set things up yourself:

### Prerequisites

- Python 3.9+
- [ffmpeg](https://ffmpeg.org/) (for video conversion)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (for downloading)
- Google Cloud account (for YouTube API — only if using YouTube)

#### Install System Dependencies

```bash
# macOS
brew install ffmpeg yt-dlp

# Ubuntu/Debian
sudo apt install ffmpeg
pip install yt-dlp

# Windows (winget)
winget install Gyan.FFmpeg
winget install yt-dlp.yt-dlp
```

### 1. Clone and Install

```bash
git clone https://github.com/JulCCrum/instagram-tiktok-and-youtube-reposter.git
cd instagram-tiktok-and-youtube-reposter

python3 -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\Activate.ps1

pip install -r requirements.txt
python -m playwright install chromium
python -m playwright install firefox
```

### 2. Configure

**Option A: Interactive wizard (recommended)**

```bash
python configure.py
```

This asks you everything — platforms, credentials, posting schedule — and generates `.env` and `user_config.json` for you.

**Option B: Manual configuration**

```bash
cp .env.example .env
```

Edit `.env`:

```
INSTAGRAM_USERNAME=your_instagram_username
INSTAGRAM_PASSWORD=your_instagram_password
TIKTOK_USERNAME=your_tiktok_username
TIKTOK_PASSWORD=your_tiktok_password
TIKTOK_ACCOUNT_NAME=your_tiktok_handle
```

### 3. Setup YouTube API (if using YouTube)

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the **YouTube Data API v3**
4. Go to **Credentials** → Create **OAuth 2.0 Client ID** (Desktop application)
5. Download the JSON and save as `client_secrets.json` in the project root

First-time authorization:

```bash
python youtube_uploader.py
```

This opens a browser for Google login. Your token is saved for future use.

### 4. Login to Platforms

```bash
python main.py init
```

This opens browsers for you to manually log into Instagram and TikTok. Sessions are saved for automated use.

### 5. Verify Setup

```bash
python main.py test
```

This checks all dependencies, credentials, browser sessions, and API access. Fix anything marked `FAIL` before proceeding.

### 6. Download and Upload

```bash
# Download your Instagram reels
python main.py download

# Preview what would happen (no actual upload)
python main.py run --dry-run

# Upload for real
python main.py run
```

## Commands Reference

| Command | Description |
|---------|-------------|
| `python main.py test` | Verify setup — checks all dependencies and config |
| `python main.py init` | First-time login to Instagram and TikTok (saves sessions) |
| `python main.py download` | Download all Instagram reels |
| `python main.py download --max 50` | Download up to 50 reels |
| `python main.py upload` | Upload next video to enabled platforms |
| `python main.py upload --dry-run` | Preview upload without actually posting |
| `python main.py run` | One cycle: download if needed + upload |
| `python main.py run --dry-run` | Preview a full cycle without changes |
| `python main.py status` | Show progress stats (per-platform breakdown) |
| `python schedule_all.py` | Schedule all pending videos on enabled platforms |
| `python configure.py` | Re-run the configuration wizard |

## Automated Posting

### Mac / Linux (Cron)

The setup wizard can configure this for you. To do it manually:

```bash
crontab -e
```

Add:
```
0 */3 * * * cd /path/to/instagram-tiktok-and-youtube-reposter && ./venv/bin/python main.py run >> cron.log 2>&1
```

### Windows (Task Scheduler)

1. Open **Task Scheduler** (search in Start Menu)
2. **Create Basic Task** → set trigger to repeat every 3 hours
3. Action: **Start a program**
   - Program: `C:\Users\YOU\instagram-tiktok-reposter\venv\Scripts\python.exe`
   - Arguments: `main.py run`
   - Start in: `C:\Users\YOU\instagram-tiktok-reposter`

## How It Works

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Instagram     │────▶│   Local Media   │────▶│  YouTube Shorts │
│   (Source)      │     │   (Downloaded)  │     │  (Scheduled)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                │
                                ▼
                        ┌─────────────────┐
                        │     TikTok      │
                        │  (Scheduled)    │
                        └─────────────────┘
```

1. **Download** — Scrapes your Instagram reels using Playwright + yt-dlp
2. **Track** — Records progress in `progress.json` (per-platform)
3. **Convert** — Converts videos for YouTube compatibility (ffmpeg)
4. **Upload** — Uses YouTube API and TikTok browser automation
5. **Schedule** — Both platforms support scheduled publishing

## Configuration

The interactive wizard (`python configure.py`) generates two files:

- **`.env`** — Credentials (Instagram, TikTok). Permissions locked to owner-only.
- **`user_config.json`** — Settings (platforms, posting frequency, schedule).

You can also edit `user_config.json` directly:

```json
{
  "platforms": {
    "youtube": true,
    "tiktok": true
  },
  "posts_per_day": 5,
  "post_interval_hours": 4.8,
  "cron_interval_hours": 3,
  "tiktok_account_name": "your_handle"
}
```

## File Structure

```
instagram-tiktok-and-youtube-reposter/
├── main.py                 # Main CLI (download, upload, run, test, status)
├── instagram_scraper.py    # Instagram download logic
├── youtube_uploader.py     # YouTube API upload
├── tiktok_uploader.py      # TikTok browser automation
├── schedule_all.py         # Batch scheduling script
├── config.py               # Configuration loader
├── configure.py            # Interactive setup wizard
├── setup.sh                # One-line setup (Mac/Linux)
├── setup_windows.ps1       # One-line setup (Windows)
├── requirements.txt        # Python dependencies
├── .env.example            # Environment template
├── .env                    # Your credentials (generated by wizard)
├── user_config.json        # Your settings (generated by wizard)
├── client_secrets.json     # YouTube API credentials (you create this)
├── run_local.sh            # Cron wrapper script
├── setup_cron.sh           # Cron setup helper
├── browser_state/          # Saved browser sessions
├── media/                  # Downloaded videos
│   └── {shortcode}/
│       ├── video.mp4
│       └── metadata.json
└── progress.json           # Upload tracking (per-platform)
```

## Scheduling Details

### YouTube
- Uses YouTube Data API's `publishAt` feature
- Videos are uploaded as private and auto-publish at scheduled time
- No computer needed after scheduling

### TikTok
- Uses TikTok's native scheduling feature
- Schedule time must be in 5-minute intervals
- Can schedule up to 10 days in advance

### Default Schedule
- 5 posts per day (~4.8 hours apart)
- Configurable via `python configure.py` or `user_config.json`

## Troubleshooting

Run `python main.py test` first — it checks everything and tells you exactly what to fix.

### Common Issues

| Problem | Fix |
|---------|-----|
| "No video file found" | Post is an image, not a video — these are skipped automatically |
| YouTube upload fails | Run `python youtube_uploader.py` to re-authorize, or check `client_secrets.json` exists |
| TikTok upload fails | Run `python main.py init` to re-login. TikTok sessions expire after ~30 days |
| "Session expired" | Run `python main.py init` to re-login to Instagram/TikTok |
| Instagram 2FA / verification | Run `python main.py init` to handle verification manually in the browser |
| YouTube quota exceeded | Wait until midnight Pacific Time for daily quota reset |
| TikTok rate limited | Wait a few hours. Stick to 5 or fewer posts/day |
| Uploads succeed on one platform but not the other | Progress tracks per-platform — failed platform will retry on next run |

## Platform Limits

| Platform | Daily Limit | Notes |
|----------|-------------|-------|
| YouTube | ~100 uploads/day | API quota based |
| TikTok | ~50 uploads/day | Unofficial, varies by account age |

## Security Notes

- Credentials are stored in plaintext in `.env` — keep this file private
- The setup wizard sets `.env` to owner-only permissions (chmod 600)
- Never commit `.env`, `client_secrets.json`, or `youtube_token.pickle` to git
- Browser sessions in `browser_state/` contain login cookies — treat as sensitive

## License

MIT License - Use at your own risk. Comply with Instagram, YouTube, and TikTok Terms of Service.

## Disclaimer

This tool is for personal use to repost your own content. Do not use it to repost content you don't own. Automated posting may violate platform terms of service — use responsibly.
