"""
TikTok Uploader Module
Uploads videos to TikTok using TikTokAutoUploader library
"""

import os
from datetime import datetime
from typing import Dict
from tiktokautouploader import upload_tiktok
import config


def upload_to_tiktok(post: Dict) -> bool:
    """Upload a video to TikTok using tiktokautouploader"""

    if not config.TIKTOK_ACCOUNT_NAME:
        print("ERROR: TikTok account name not configured.")
        print("  -> Run 'python configure.py' or add TIKTOK_ACCOUNT_NAME to .env")
        return False

    video_files = [f for f in post.get("media_files", []) if f.endswith(".mp4") and "_youtube" not in f]
    if not video_files:
        print("ERROR: No video file found for this post.")
        print("  -> The post may be an image, or the download was incomplete.")
        print("  -> Try re-downloading: python main.py download")
        return False

    video_path = os.path.abspath(video_files[0])

    if not os.path.exists(video_path):
        print(f"ERROR: Video file missing: {video_path}")
        print("  -> The file may have been deleted. Re-download with: python main.py download")
        return False

    caption = post.get("caption", "")[:2200]

    # Extract hashtags from caption
    hashtags = [word for word in caption.split() if word.startswith("#")]

    # Clean caption (remove hashtags as they'll be added separately)
    description = caption
    for tag in hashtags:
        description = description.replace(tag, "").strip()

    # If no description left, use a default
    if not description.strip():
        description = "Check this out!"

    print(f"Uploading to TikTok: {post.get('shortcode', 'unknown')}")
    print(f"Video: {video_path}")
    print(f"Description: {description[:50]}...")

    try:
        upload_tiktok(
            video=video_path,
            description=description,
            accountname=config.TIKTOK_ACCOUNT_NAME,
            hashtags=hashtags if hashtags else None,
            copyrightcheck=False,
            headless=True
        )
        print("Successfully uploaded to TikTok!")
        return True

    except Exception as e:
        error_msg = str(e).lower()
        print(f"ERROR uploading to TikTok: {e}")
        if "login" in error_msg or "auth" in error_msg or "session" in error_msg:
            print("  -> Your TikTok session may have expired.")
            print("  -> Fix: Run 'python main.py init' to re-login.")
        elif "captcha" in error_msg or "verify" in error_msg:
            print("  -> TikTok is requesting verification (CAPTCHA).")
            print("  -> Fix: Run 'python main.py init' to login manually.")
        elif "rate" in error_msg or "limit" in error_msg or "too many" in error_msg:
            print("  -> TikTok rate limit hit. Too many uploads too fast.")
            print("  -> Fix: Wait a few hours before retrying.")
        elif "network" in error_msg or "connection" in error_msg or "timeout" in error_msg:
            print("  -> Network error. Check your internet connection.")
        else:
            print("  -> If this persists, try: python main.py init")
        return False


def upload_to_tiktok_scheduled(post: Dict, publish_time: datetime) -> bool:
    """Upload a video to TikTok with scheduled publish time"""

    video_files = [f for f in post.get("media_files", []) if f.endswith(".mp4") and "_youtube" not in f]
    if not video_files:
        print("No video file found")
        return False

    video_path = os.path.abspath(video_files[0])
    caption = post.get("caption", "")[:2200]

    # Extract hashtags from caption
    hashtags = [word for word in caption.split() if word.startswith("#")]

    # Clean caption
    description = caption
    for tag in hashtags:
        description = description.replace(tag, "").strip()

    if not description.strip():
        description = "Check this out!"

    # Format schedule time for TikTok (HH:MM in 24h format, must be multiple of 5)
    minute = (publish_time.minute // 5) * 5  # Round down to nearest 5
    schedule_time = f"{publish_time.hour:02d}:{minute:02d}"
    schedule_day = publish_time.day

    print(f"Uploading to TikTok (scheduled for {publish_time.strftime('%m/%d %I:%M %p')})...")
    print(f"Video: {video_path}")

    try:
        upload_tiktok(
            video=video_path,
            description=description,
            accountname=config.TIKTOK_ACCOUNT_NAME,
            hashtags=hashtags if hashtags else None,
            copyrightcheck=False,
            headless=True,
            schedule=schedule_time,
            day=schedule_day
        )
        print("Successfully scheduled on TikTok!")
        return True

    except Exception as e:
        error_msg = str(e).lower()
        print(f"ERROR scheduling on TikTok: {e}")
        if "login" in error_msg or "session" in error_msg:
            print("  -> TikTok session expired. Run 'python main.py init' to re-login.")
        elif "schedule" in error_msg or "day" in error_msg:
            print("  -> TikTok only allows scheduling up to 10 days in advance.")
        else:
            print("  -> If this persists, try: python main.py init")
        return False
