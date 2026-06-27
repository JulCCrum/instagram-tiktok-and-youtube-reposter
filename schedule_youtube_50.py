#!/usr/bin/env python3
"""
Schedule 50 pending videos to YouTube only (not TikTok)
Posts every 4.8 hours (5 posts/day)
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

import config
from instagram_scraper import load_progress, save_progress

LIMIT = 50  # Only schedule this many

def get_pending_posts(limit: int = LIMIT) -> List[Dict]:
    """Get pending posts that haven't been uploaded yet (limited)"""
    progress = load_progress()
    downloaded = progress.get("downloaded", [])
    uploaded = progress.get("uploaded", [])

    pending = []
    for shortcode in downloaded:
        if shortcode not in uploaded:
            post_dir = config.MEDIA_DIR / shortcode
            meta_file = post_dir / "metadata.json"
            if meta_file.exists():
                with open(meta_file) as f:
                    post = json.load(f)
                    video_files = [f for f in post.get("media_files", []) if f.endswith(".mp4")]
                    if video_files:
                        pending.append(post)
                        if len(pending) >= limit:
                            break
    return pending


def schedule_youtube(post: Dict, publish_time: datetime) -> bool:
    """Upload to YouTube with scheduled publish time"""
    from youtube_uploader import upload_to_youtube_scheduled
    return upload_to_youtube_scheduled(post, publish_time)


def main():
    print("=" * 60)
    print(f"SCHEDULING {LIMIT} VIDEOS TO YOUTUBE ONLY")
    print("=" * 60)

    pending = get_pending_posts(LIMIT)

    if not pending:
        print("No pending videos to schedule!")
        return

    print(f"\nFound {len(pending)} videos to schedule")
    print("They will be scheduled every ~5 hours (5 posts/day) starting in 10 min.\n")

    # Calculate schedule times
    start_time = datetime.now() + timedelta(minutes=10)
    interval_hours = 4.8

    success_count = 0

    for i, post in enumerate(pending):
        publish_time = start_time + timedelta(hours=i * interval_hours)

        print(f"\n{'='*60}")
        print(f"Video {i+1}/{len(pending)}: {post['shortcode']}")
        print(f"Caption: {post.get('caption', '')[:50]}...")
        print(f"Scheduled for: {publish_time.strftime('%Y-%m-%d %I:%M %p')}")
        print("=" * 60)

        print("\n[YouTube] Uploading and scheduling...")
        try:
            youtube_ok = schedule_youtube(post, publish_time)
            if youtube_ok:
                print("[YouTube] SUCCESS - Scheduled!")
                # Mark as uploaded
                progress = load_progress()
                uploaded = progress.get("uploaded", [])
                uploaded.append(post["shortcode"])
                progress["uploaded"] = uploaded
                save_progress(progress)
                success_count += 1
                print(f"[OK] Marked {post['shortcode']} as scheduled")
            else:
                print("[YouTube] FAILED")
        except Exception as e:
            print(f"[YouTube] ERROR: {e}")

    print("\n" + "=" * 60)
    print(f"DONE! Scheduled {success_count}/{len(pending)} videos to YouTube")
    print("=" * 60)

    # Print schedule summary
    print("\nSchedule Summary:")
    for i in range(min(success_count, 10)):
        publish_time = start_time + timedelta(hours=i * interval_hours)
        print(f"  {publish_time.strftime('%m/%d %I:%M %p')}")
    if success_count > 10:
        print(f"  ... and {success_count - 10} more")


if __name__ == "__main__":
    main()
