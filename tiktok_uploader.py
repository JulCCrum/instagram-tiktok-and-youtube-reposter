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

    video_files = [f for f in post.get("media_files", []) if f.endswith(".mp4") and "_youtube" not in f]
    if not video_files:
        print("No video file found")
        return False

    video_path = os.path.abspath(video_files[0])
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
        # Use the TikTok account name (handle, not email)
        # The library will prompt for login on first use and save session
        upload_tiktok(
            video=video_path,
            description=description,
            accountname="jackpotautomations",  # TikTok handle
            hashtags=hashtags if hashtags else None,
            copyrightcheck=False,
            headless=True  # Run in background
        )
        print("Successfully uploaded to TikTok!")
        return True

    except Exception as e:
        print(f"Error uploading to TikTok: {e}")
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
            accountname="jackpotautomations",
            hashtags=hashtags if hashtags else None,
            copyrightcheck=False,
            headless=True,
            schedule=schedule_time,
            day=schedule_day
        )
        print("Successfully scheduled on TikTok!")
        return True

    except Exception as e:
        print(f"Error scheduling on TikTok: {e}")
        return False
