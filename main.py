#!/usr/bin/env python3
"""
Instagram to TikTok/YouTube Reposter
Main orchestration script

Usage:
    python main.py download    # Download all Instagram reels
    python main.py upload      # Upload next post to YouTube (and TikTok when ready)
    python main.py run         # Download + upload one post (for cron)
    python main.py status      # Show progress status
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Dict

import config
from instagram_scraper import scrape_instagram_posts, load_progress, save_progress
from tiktok_uploader import upload_to_tiktok
from youtube_uploader import upload_to_youtube


def get_next_post_to_upload() -> Optional[Dict]:
    """Get the next downloaded post that hasn't been uploaded yet"""
    progress = load_progress()
    downloaded = progress.get("downloaded", [])
    uploaded = progress.get("uploaded", [])

    # Find posts that are downloaded but not uploaded
    pending = [sc for sc in downloaded if sc not in uploaded]

    if not pending:
        return None

    # Get the oldest pending post (FIFO order)
    shortcode = pending[0]
    post_dir = config.MEDIA_DIR / shortcode

    if not post_dir.exists():
        print(f"Post directory not found: {post_dir}")
        return None

    # Load metadata
    meta_file = post_dir / "metadata.json"
    if meta_file.exists():
        with open(meta_file) as f:
            return json.load(f)

    return None


def download_command(args):
    """Download Instagram posts"""
    print("=" * 50)
    print("Downloading Instagram posts...")
    print("=" * 50)

    max_posts = args.max or 500
    posts = scrape_instagram_posts(max_posts=max_posts)
    print(f"\nDownloaded {len(posts)} new posts")


def upload_command(args):
    """Upload next post to YouTube (and TikTok if enabled)"""
    print("=" * 50)
    print("Uploading to platforms...")
    print("=" * 50)

    post = get_next_post_to_upload()
    if not post:
        print("No posts pending upload!")
        return

    print(f"Uploading post: {post['shortcode']}")
    print(f"Caption: {post.get('caption', '')[:100]}...")

    # Upload to YouTube
    youtube_success = False
    tiktok_success = False

    print("\n--- YouTube ---")
    youtube_success = upload_to_youtube(post)

    # Upload to TikTok (if enabled and logged in)
    if args.tiktok:
        print("\n--- TikTok ---")
        tiktok_success = upload_to_tiktok(post)

    if youtube_success or tiktok_success:
        # Mark as uploaded
        progress = load_progress()
        uploaded = progress.get("uploaded", [])
        uploaded.append(post["shortcode"])
        progress["uploaded"] = uploaded
        save_progress(progress)
        print(f"\nSuccessfully uploaded: {post['shortcode']}")
    else:
        print(f"\nFailed to upload: {post['shortcode']}")


def run_command(args):
    """Run one cycle: ensure posts are downloaded, upload one"""
    print("=" * 50)
    print("Running repost cycle...")
    print("=" * 50)

    # Check if we have posts to upload
    post = get_next_post_to_upload()

    if not post:
        print("No pending posts, downloading from Instagram...")
        posts = scrape_instagram_posts(max_posts=50)  # Download in batches
        if not posts:
            print("No new posts to download")
            return
        post = get_next_post_to_upload()

    if not post:
        print("No posts available to upload")
        return

    # Check if this is a video
    video_files = [f for f in post.get("media_files", []) if f.endswith(".mp4")]
    if not video_files:
        print(f"Post {post['shortcode']} is not a video, marking as uploaded and skipping...")
        progress = load_progress()
        uploaded = progress.get("uploaded", [])
        uploaded.append(post["shortcode"])
        progress["uploaded"] = uploaded
        save_progress(progress)
        # Try next post
        run_command(args)
        return

    # Upload to YouTube
    print(f"Uploading: {post['shortcode']}")
    youtube_success = upload_to_youtube(post)

    # Optionally upload to TikTok
    tiktok_success = False
    if getattr(args, 'tiktok', False):
        tiktok_success = upload_to_tiktok(post)

    if youtube_success or tiktok_success:
        progress = load_progress()
        uploaded = progress.get("uploaded", [])
        uploaded.append(post["shortcode"])
        progress["uploaded"] = uploaded
        save_progress(progress)
        print(f"Successfully reposted: {post['shortcode']}")
    else:
        print(f"Failed to upload: {post['shortcode']}")


def status_command(args):
    """Show current progress status"""
    print("=" * 50)
    print("Repost Status")
    print("=" * 50)

    progress = load_progress()
    downloaded = progress.get("downloaded", [])
    uploaded = progress.get("uploaded", [])

    print(f"Total downloaded: {len(downloaded)}")
    print(f"Total uploaded:   {len(uploaded)}")
    print(f"Pending upload:   {len(downloaded) - len(uploaded)}")

    # Count videos vs images
    video_count = 0
    image_count = 0
    for shortcode in downloaded:
        post_dir = config.MEDIA_DIR / shortcode
        if post_dir.exists():
            videos = list(post_dir.glob("*.mp4"))
            if videos:
                video_count += 1
            else:
                image_count += 1

    print(f"\nMedia breakdown:")
    print(f"  Videos (can upload): {video_count}")
    print(f"  Images (skip):       {image_count}")


def init_command(args):
    """Initialize the project - login to both platforms"""
    print("=" * 50)
    print("Initializing - Please login to both platforms")
    print("=" * 50)
    print("\nThis will open browsers for you to login manually.")
    print("Your session will be saved for future automated runs.\n")

    # Temporarily disable headless for manual login
    original_headless = config.HEADLESS
    config.HEADLESS = False

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        # Instagram login
        print("Opening Instagram for login...")
        ig_browser = p.chromium.launch_persistent_context(
            user_data_dir=str(config.BROWSER_STATE_DIR / "instagram"),
            headless=False,
            viewport={"width": 1280, "height": 720}
        )
        ig_page = ig_browser.pages[0] if ig_browser.pages else ig_browser.new_page()
        ig_page.goto("https://www.instagram.com/accounts/login/")

        input("Press Enter after you've logged into Instagram...")
        ig_browser.close()
        print("Instagram session saved!\n")

        # TikTok login
        print("Opening TikTok for login...")
        tt_browser = p.chromium.launch_persistent_context(
            user_data_dir=str(config.BROWSER_STATE_DIR / "tiktok"),
            headless=False,
            viewport={"width": 1280, "height": 720}
        )
        tt_page = tt_browser.pages[0] if tt_browser.pages else tt_browser.new_page()
        tt_page.goto("https://www.tiktok.com/login")

        input("Press Enter after you've logged into TikTok...")
        tt_browser.close()
        print("TikTok session saved!\n")

    config.HEADLESS = original_headless
    print("Initialization complete! You can now run automated commands.")


def main():
    parser = argparse.ArgumentParser(
        description="Instagram to TikTok Reposter",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py init        # First time setup - login manually
  python main.py download    # Download all your Instagram posts
  python main.py upload      # Upload next video to TikTok
  python main.py run         # One cycle (download if needed + upload)
  python main.py status      # Check progress
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Init command
    init_parser = subparsers.add_parser("init", help="Initialize - manual login to both platforms")

    # Download command
    download_parser = subparsers.add_parser("download", help="Download Instagram posts")
    download_parser.add_argument("--max", type=int, default=500, help="Max posts to download")

    # Upload command
    upload_parser = subparsers.add_parser("upload", help="Upload next post to YouTube")
    upload_parser.add_argument("--tiktok", action="store_true", help="Also upload to TikTok")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run one cycle (for cron)")
    run_parser.add_argument("--tiktok", action="store_true", help="Also upload to TikTok")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show progress status")

    args = parser.parse_args()

    if args.command == "init":
        init_command(args)
    elif args.command == "download":
        download_command(args)
    elif args.command == "upload":
        upload_command(args)
    elif args.command == "run":
        run_command(args)
    elif args.command == "status":
        status_command(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
