#!/usr/bin/env python3
"""
Schedule all pending videos to post 5 times per day (~5 hours apart)
Uploads to both YouTube and TikTok with scheduled publish times
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict

import config
from instagram_scraper import load_progress, save_progress


def get_pending_posts() -> List[Dict]:
    """Get all pending posts that haven't been uploaded yet"""
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
                    # Check if it's a video
                    video_files = [f for f in post.get("media_files", []) if f.endswith(".mp4")]
                    if video_files:
                        pending.append(post)

    return pending


def schedule_youtube(post: Dict, publish_time: datetime) -> bool:
    """Upload to YouTube with scheduled publish time"""
    from youtube_uploader import upload_to_youtube_scheduled
    return upload_to_youtube_scheduled(post, publish_time)


def schedule_tiktok(post: Dict, publish_time: datetime) -> bool:
    """Upload to TikTok with scheduled publish time"""
    from tiktok_uploader import upload_to_tiktok_scheduled
    return upload_to_tiktok_scheduled(post, publish_time)


def main():
    print("=" * 60)
    print("SCHEDULING ALL PENDING VIDEOS")
    print("=" * 60)

    pending = get_pending_posts()

    if not pending:
        print("No pending videos to schedule!")
        return

    interval_hours = config.POST_INTERVAL_HOURS
    posts_per_day = config.POSTS_PER_DAY

    print(f"\nFound {len(pending)} videos to schedule")
    print(f"Posting {posts_per_day}x/day (every ~{interval_hours} hours) starting now.\n")

    start_time = datetime.now() + timedelta(minutes=10)

    success_count = 0

    for i, post in enumerate(pending):
        publish_time = start_time + timedelta(hours=i * interval_hours)

        print(f"\n{'='*60}")
        print(f"Video {i+1}/{len(pending)}: {post['shortcode']}")
        print(f"Caption: {post.get('caption', '')[:50]}...")
        print(f"Scheduled for: {publish_time.strftime('%Y-%m-%d %I:%M %p')}")
        print("=" * 60)

        youtube_ok = False
        tiktok_ok = False

        # Schedule on YouTube
        if config.USE_YOUTUBE:
            print("\n[YouTube] Uploading and scheduling...")
            try:
                youtube_ok = schedule_youtube(post, publish_time)
                if youtube_ok:
                    print("[YouTube] SUCCESS - Scheduled!")
                else:
                    print("[YouTube] FAILED")
            except Exception as e:
                print(f"[YouTube] ERROR: {e}")

        # Schedule on TikTok
        if config.USE_TIKTOK:
            print("\n[TikTok] Uploading and scheduling...")
            try:
                tiktok_ok = schedule_tiktok(post, publish_time)
                if tiktok_ok:
                    print("[TikTok] SUCCESS - Scheduled!")
                else:
                    print("[TikTok] FAILED")
            except Exception as e:
                print(f"[TikTok] ERROR: {e}")

        # Track per-platform results
        if youtube_ok or tiktok_ok:
            progress = load_progress()
            shortcode = post["shortcode"]
            if youtube_ok:
                yt_list = progress.get("uploaded_youtube", [])
                if shortcode not in yt_list:
                    yt_list.append(shortcode)
                    progress["uploaded_youtube"] = yt_list
            if tiktok_ok:
                tt_list = progress.get("uploaded_tiktok", [])
                if shortcode not in tt_list:
                    tt_list.append(shortcode)
                    progress["uploaded_tiktok"] = tt_list
            # Mark fully uploaded if all enabled platforms succeeded
            all_done = True
            if config.USE_YOUTUBE and not youtube_ok:
                all_done = False
            if config.USE_TIKTOK and not tiktok_ok:
                all_done = False
            if all_done:
                uploaded = progress.get("uploaded", [])
                if shortcode not in uploaded:
                    uploaded.append(shortcode)
                    progress["uploaded"] = uploaded
            save_progress(progress)
            success_count += 1
            print(f"\n[OK] Marked {shortcode} as scheduled")

    print("\n" + "=" * 60)
    print(f"DONE! Scheduled {success_count}/{len(pending)} videos")
    print("=" * 60)

    # Print schedule summary
    print("\nSchedule Summary:")
    for i, post in enumerate(pending[:success_count]):
        publish_time = start_time + timedelta(hours=i * interval_hours)
        print(f"  {publish_time.strftime('%m/%d %I:%M %p')} - {post['shortcode']}")


if __name__ == "__main__":
    main()
