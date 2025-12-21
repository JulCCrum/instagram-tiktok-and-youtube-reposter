# Instagram to TikTok & YouTube Reposter

Automatically repost your Instagram Reels to TikTok and YouTube Shorts. Download once, schedule uploads to both platforms, and let them publish automatically.

## Features

- **Download Instagram Reels** - Scrapes your profile and downloads all video content
- **Upload to YouTube Shorts** - Uses YouTube Data API with scheduling support
- **Upload to TikTok** - Browser automation with scheduling support
- **Progress Tracking** - Remembers what's been downloaded and uploaded
- **Scheduled Publishing** - Schedule posts to publish automatically (no computer needed)
- **Caption Preservation** - Copies captions and hashtags from Instagram

## Prerequisites

- Python 3.9+
- [ffmpeg](https://ffmpeg.org/) (for video conversion)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (for downloading)
- Google Cloud account (for YouTube API)

### Install System Dependencies

```bash
# macOS
brew install ffmpeg yt-dlp

# Ubuntu/Debian
sudo apt install ffmpeg
pip install yt-dlp
```

## Quick Start

### 1. Clone and Setup

```bash
git clone https://github.com/JulCCrum/instagram-tiktok-reposter.git
cd instagram-tiktok-reposter

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install browsers for automation
playwright install chromium
playwright install firefox  # Required for TikTok
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your Instagram credentials:

```
INSTAGRAM_USERNAME=your_instagram_username
INSTAGRAM_PASSWORD=your_instagram_password
TIKTOK_USERNAME=your_tiktok_username
TIKTOK_PASSWORD=your_tiktok_password
```

### 3. Setup YouTube API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable the **YouTube Data API v3**
4. Create OAuth 2.0 credentials (Desktop application)
5. Download the credentials and save as `client_secrets.json` in the project root

First-time authorization:

```bash
python youtube_uploader.py
```

This opens a browser for Google login. Your token is saved for future use.

### 4. Setup TikTok

The TikTok uploader uses browser automation. First login:

```bash
python main.py init
```

This opens browsers for you to manually log into Instagram and TikTok. Sessions are saved.

### 5. Download Your Instagram Content

```bash
python main.py download --max 500
```

### 6. Upload Content

**Single upload:**
```bash
# YouTube only
python main.py upload

# YouTube + TikTok
python main.py upload --tiktok
```

**Schedule all pending videos:**
```bash
python schedule_all.py
```

This schedules all downloaded videos to publish every 3 hours on both platforms.

## Commands Reference

| Command | Description |
|---------|-------------|
| `python main.py init` | First-time login (saves sessions) |
| `python main.py download` | Download all Instagram reels |
| `python main.py download --max 50` | Download up to 50 reels |
| `python main.py upload` | Upload next video to YouTube |
| `python main.py upload --tiktok` | Upload to YouTube + TikTok |
| `python main.py run --tiktok` | One cycle (download if needed + upload) |
| `python main.py status` | Show progress stats |
| `python schedule_all.py` | Schedule all videos on both platforms |

## Automated Posting (Cron)

To automatically post every 3 hours:

```bash
# Setup cron job
./setup_cron.sh

# Or manually add to crontab:
crontab -e
```

Add this line:
```
0 */3 * * * /path/to/instagram-tiktok-reposter/run_local.sh >> /path/to/cron.log 2>&1
```

## How It Works

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Instagram     │────▶│   Local Media   │────▶│  YouTube Shorts │
│   (Source)      │     │   (Downloaded)  │     │  (Scheduled)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                │
                                │
                                ▼
                        ┌─────────────────┐
                        │     TikTok      │
                        │  (Scheduled)    │
                        └─────────────────┘
```

1. **Download**: Scrapes your Instagram reels using Playwright + yt-dlp
2. **Track**: Records progress in `progress.json`
3. **Convert**: Converts videos for YouTube compatibility (ffmpeg)
4. **Upload**: Uses YouTube API and TikTok browser automation
5. **Schedule**: Both platforms support scheduled publishing

## File Structure

```
instagram-tiktok-reposter/
├── main.py                 # Main CLI script
├── instagram_scraper.py    # Instagram download logic
├── youtube_uploader.py     # YouTube API upload
├── tiktok_uploader.py      # TikTok browser automation
├── schedule_all.py         # Batch scheduling script
├── config.py               # Configuration
├── requirements.txt        # Python dependencies
├── .env.example            # Environment template
├── .env                    # Your credentials (create this)
├── client_secrets.json     # YouTube API credentials (create this)
├── run_local.sh            # Cron wrapper script
├── setup_cron.sh           # Cron setup helper
├── browser_state/          # Saved browser sessions
├── media/                  # Downloaded videos
│   └── {shortcode}/
│       ├── video.mp4
│       └── metadata.json
└── progress.json           # Upload tracking
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
- Posts every 3 hours (8 posts per day)
- Spreads content evenly throughout the day

## Troubleshooting

### "No video file found"
- Instagram post might be an image, not a video
- Only reels/videos are uploaded (images are skipped)

### YouTube upload fails
- Run `python youtube_uploader.py` to re-authorize
- Check that `client_secrets.json` exists

### TikTok upload fails
- Delete `TK_cookies_*.json` files
- Run `python main.py init` to re-login
- TikTok may show walkthrough popups - the script handles these

### Rate limiting
- TikTok may limit uploads if you post too frequently
- Stick to the 3-hour interval to stay safe

## Platform Limits

| Platform | Daily Limit | Notes |
|----------|-------------|-------|
| YouTube | ~100 uploads/day | API quota based |
| TikTok | ~50 uploads/day | Unofficial, varies |

## License

MIT License - Use at your own risk. Comply with Instagram, YouTube, and TikTok Terms of Service.

## Disclaimer

This tool is for personal use to repost your own content. Do not use it to repost content you don't own. Automated posting may violate platform terms of service - use responsibly.
