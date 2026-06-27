#!/usr/bin/env python3
"""
Instagram to TikTok/YouTube Reposter
Main orchestration script

Usage:
    python main.py download    # Download all Instagram reels
    python main.py upload      # Upload next post to YouTube (and TikTok when ready)
    python main.py run         # Download + upload one post (for cron)
    python main.py status      # Show progress status
    python main.py test        # Verify setup (checks all dependencies)
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict

import config
from instagram_scraper import scrape_instagram_posts, load_progress, save_progress
from tiktok_uploader import upload_to_tiktok
from youtube_uploader import upload_to_youtube


def mark_uploaded(shortcode: str, platform: str = None):
    """Mark a post as uploaded. If platform specified, tracks per-platform."""
    progress = load_progress()

    if platform:
        key = f"uploaded_{platform}"
        platform_list = progress.get(key, [])
        if shortcode not in platform_list:
            platform_list.append(shortcode)
            progress[key] = platform_list

    # Check if post is done on ALL enabled platforms
    all_done = True
    if config.USE_YOUTUBE and shortcode not in progress.get("uploaded_youtube", []):
        all_done = False
    if config.USE_TIKTOK and shortcode not in progress.get("uploaded_tiktok", []):
        all_done = False

    # Mark in the main "uploaded" list for backward compat
    if all_done:
        uploaded = progress.get("uploaded", [])
        if shortcode not in uploaded:
            uploaded.append(shortcode)
            progress["uploaded"] = uploaded

    save_progress(progress)


def get_next_post_to_upload() -> Optional[Dict]:
    """Get the next downloaded post that hasn't been uploaded to all platforms"""
    progress = load_progress()
    downloaded = progress.get("downloaded", [])
    uploaded = progress.get("uploaded", [])

    # Find posts that are downloaded but not fully uploaded
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
    dry_run = getattr(args, 'dry_run', False)

    print("=" * 50)
    print("Uploading to platforms..." + (" [DRY RUN]" if dry_run else ""))
    print("=" * 50)

    post = get_next_post_to_upload()
    if not post:
        print("No posts pending upload!")
        return

    shortcode = post['shortcode']
    caption = post.get('caption', '')
    video_files = [f for f in post.get("media_files", []) if f.endswith(".mp4")]

    print(f"Post: {shortcode}")
    print(f"Caption: {caption[:100]}...")
    print(f"Video files: {len(video_files)}")

    if dry_run:
        platforms = []
        if config.USE_YOUTUBE:
            platforms.append("YouTube")
        if args.tiktok or config.USE_TIKTOK:
            platforms.append("TikTok")
        print(f"\n[DRY RUN] Would upload to: {', '.join(platforms)}")
        print(f"[DRY RUN] Video: {video_files[0] if video_files else 'NONE — would skip'}")
        print(f"[DRY RUN] Caption length: {len(caption)} chars")
        if len(caption) > 2200:
            print(f"[DRY RUN] WARNING: Caption will be truncated to 2200 chars for TikTok")
        print("[DRY RUN] No changes made.")
        return

    # Upload to YouTube (skip if already uploaded to YouTube)
    youtube_success = False
    tiktok_success = False
    progress = load_progress()

    if config.USE_YOUTUBE:
        if shortcode in progress.get("uploaded_youtube", []):
            print("\n--- YouTube --- (already uploaded, skipping)")
            youtube_success = True
        else:
            print("\n--- YouTube ---")
            youtube_success = upload_to_youtube(post)
        if youtube_success:
            mark_uploaded(shortcode, "youtube")

    # Upload to TikTok (skip if already uploaded to TikTok)
    if args.tiktok or config.USE_TIKTOK:
        if shortcode in progress.get("uploaded_tiktok", []):
            print("\n--- TikTok --- (already uploaded, skipping)")
            tiktok_success = True
        else:
            print("\n--- TikTok ---")
            tiktok_success = upload_to_tiktok(post)
        if tiktok_success:
            mark_uploaded(shortcode, "tiktok")

    if youtube_success or tiktok_success:
        results = []
        if youtube_success:
            results.append("YouTube")
        if tiktok_success:
            results.append("TikTok")
        print(f"\nUploaded {shortcode} to: {', '.join(results)}")
        if not youtube_success and config.USE_YOUTUBE:
            print("  (YouTube failed — will retry on next run)")
        if not tiktok_success and (args.tiktok or config.USE_TIKTOK):
            print("  (TikTok failed — will retry on next run)")
    else:
        print(f"\nFailed to upload: {post['shortcode']}")


def run_command(args):
    """Run one cycle: ensure posts are downloaded, upload one"""
    dry_run = getattr(args, 'dry_run', False)

    print("=" * 50)
    print("Running repost cycle..." + (" [DRY RUN]" if dry_run else ""))
    print("=" * 50)

    # Check if we have posts to upload
    post = get_next_post_to_upload()

    if not post:
        if dry_run:
            print("[DRY RUN] No pending posts. Would download from Instagram.")
            return
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
        print(f"Post {post['shortcode']} is not a video, skipping...")
        if not dry_run:
            # Mark as done on all platforms so we skip it
            if config.USE_YOUTUBE:
                mark_uploaded(post["shortcode"], "youtube")
            if config.USE_TIKTOK:
                mark_uploaded(post["shortcode"], "tiktok")
            # Try next post
            run_command(args)
        else:
            print("[DRY RUN] Would skip non-video post and try next")
        return

    if dry_run:
        caption = post.get('caption', '')
        platforms = []
        if config.USE_YOUTUBE:
            platforms.append("YouTube")
        if getattr(args, 'tiktok', False) or config.USE_TIKTOK:
            platforms.append("TikTok")
        print(f"\n[DRY RUN] Would upload: {post['shortcode']}")
        print(f"[DRY RUN] Video: {video_files[0]}")
        print(f"[DRY RUN] Caption: {caption[:80]}...")
        print(f"[DRY RUN] Platforms: {', '.join(platforms)}")
        print("[DRY RUN] No changes made.")
        return

    # Upload to YouTube (skip if already uploaded to YouTube)
    shortcode = post['shortcode']
    print(f"Uploading: {shortcode}")
    youtube_success = False
    progress = load_progress()
    if config.USE_YOUTUBE:
        if shortcode in progress.get("uploaded_youtube", []):
            print("[YouTube] Already uploaded, skipping")
            youtube_success = True
        else:
            youtube_success = upload_to_youtube(post)
        if youtube_success:
            mark_uploaded(shortcode, "youtube")

    # Upload to TikTok (skip if already uploaded to TikTok)
    tiktok_success = False
    if getattr(args, 'tiktok', False) or config.USE_TIKTOK:
        if shortcode in progress.get("uploaded_tiktok", []):
            print("[TikTok] Already uploaded, skipping")
            tiktok_success = True
        else:
            tiktok_success = upload_to_tiktok(post)
        if tiktok_success:
            mark_uploaded(shortcode, "tiktok")

    if youtube_success or tiktok_success:
        results = []
        if youtube_success:
            results.append("YouTube")
        if tiktok_success:
            results.append("TikTok")
        print(f"Reposted {shortcode} to: {', '.join(results)}")
    else:
        print(f"Failed to upload: {shortcode}")


def status_command(args):
    """Show current progress status"""
    print("=" * 50)
    print("Repost Status")
    print("=" * 50)

    progress = load_progress()
    downloaded = progress.get("downloaded", [])
    uploaded = progress.get("uploaded", [])
    uploaded_yt = progress.get("uploaded_youtube", [])
    uploaded_tt = progress.get("uploaded_tiktok", [])

    print(f"Total downloaded:   {len(downloaded)}")
    print(f"Fully uploaded:     {len(uploaded)}")
    print(f"Pending upload:     {len(downloaded) - len(uploaded)}")
    if config.USE_YOUTUBE:
        print(f"  YouTube uploads:  {len(uploaded_yt)}")
    if config.USE_TIKTOK:
        print(f"  TikTok uploads:   {len(uploaded_tt)}")

    # Show posts that succeeded on one platform but not the other
    if config.USE_YOUTUBE and config.USE_TIKTOK:
        yt_only = [sc for sc in uploaded_yt if sc not in uploaded_tt and sc in downloaded]
        tt_only = [sc for sc in uploaded_tt if sc not in uploaded_yt and sc in downloaded]
        if yt_only:
            print(f"  YouTube only (TikTok pending): {len(yt_only)}")
        if tt_only:
            print(f"  TikTok only (YouTube pending): {len(tt_only)}")

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


def test_command(args):
    """Verify that everything is set up correctly without posting anything"""
    print("=" * 50)
    print("Setup Verification")
    print("=" * 50)
    print()

    passed = 0
    failed = 0
    warnings = 0

    def check(name, condition, fix=""):
        nonlocal passed, failed
        if condition:
            print(f"  PASS  {name}")
            passed += 1
        else:
            print(f"  FAIL  {name}")
            if fix:
                print(f"         -> Fix: {fix}")
            failed += 1

    def warn(name, condition, note=""):
        nonlocal passed, warnings
        if condition:
            print(f"  PASS  {name}")
            passed += 1
        else:
            print(f"  WARN  {name}")
            if note:
                print(f"         -> {note}")
            warnings += 1

    # Python version
    py_version = sys.version_info
    check(
        f"Python {py_version.major}.{py_version.minor}.{py_version.micro}",
        py_version >= (3, 9),
        "Install Python 3.9 or newer"
    )

    # ffmpeg
    check(
        "ffmpeg installed",
        shutil.which("ffmpeg") is not None,
        "Install ffmpeg: brew install ffmpeg (Mac) or sudo apt install ffmpeg (Linux)"
    )

    # yt-dlp
    check(
        "yt-dlp installed",
        shutil.which("yt-dlp") is not None,
        "Install yt-dlp: brew install yt-dlp (Mac) or pip install yt-dlp"
    )

    # Playwright
    try:
        from playwright.sync_api import sync_playwright
        check("Playwright installed", True)
    except ImportError:
        check("Playwright installed", False, "Run: pip install playwright && python -m playwright install")

    # Playwright browsers
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "--dry-run"],
            capture_output=True, text=True, timeout=10
        )
        # If dry-run doesn't error, browsers are likely installed
        check("Playwright browsers", True)
    except Exception:
        warn("Playwright browsers", False, "Run: python -m playwright install chromium")

    # .env file
    check(
        ".env file exists",
        (config.BASE_DIR / ".env").exists(),
        "Run: python configure.py"
    )

    # Credentials
    check(
        "Instagram username configured",
        bool(config.INSTAGRAM_USERNAME),
        "Add INSTAGRAM_USERNAME to .env or run: python configure.py"
    )
    check(
        "Instagram password configured",
        bool(config.INSTAGRAM_PASSWORD),
        "Add INSTAGRAM_PASSWORD to .env or run: python configure.py"
    )

    # user_config.json
    warn(
        "user_config.json exists",
        config.USER_CONFIG_FILE.exists(),
        "Run: python configure.py (optional — defaults will be used)"
    )

    # Platform-specific checks
    print()
    print("  --- Platform: YouTube ---")
    if config.USE_YOUTUBE:
        check(
            "client_secrets.json exists",
            (config.BASE_DIR / "client_secrets.json").exists(),
            "Download OAuth credentials from Google Cloud Console\n"
            "         See: https://console.cloud.google.com/ -> APIs -> Credentials"
        )
        warn(
            "YouTube token (authenticated)",
            (config.BASE_DIR / "youtube_token.pickle").exists(),
            "Run: python youtube_uploader.py to authenticate"
        )
    else:
        print("  SKIP  YouTube disabled in config")

    print()
    print("  --- Platform: TikTok ---")
    if config.USE_TIKTOK:
        check(
            "TikTok account name configured",
            bool(config.TIKTOK_ACCOUNT_NAME),
            "Add TIKTOK_ACCOUNT_NAME to .env or run: python configure.py"
        )
        warn(
            "TikTok browser session exists",
            (config.BROWSER_STATE_DIR / "tiktok").exists(),
            "Run: python main.py init to login"
        )
    else:
        print("  SKIP  TikTok disabled in config")

    # Browser sessions
    print()
    print("  --- Browser Sessions ---")
    warn(
        "Instagram browser session",
        (config.BROWSER_STATE_DIR / "instagram").exists(),
        "Run: python main.py init to login"
    )

    # .env permissions (Unix only)
    env_path = config.BASE_DIR / ".env"
    if env_path.exists() and os.name != "nt":
        perms = oct(env_path.stat().st_mode)[-3:]
        warn(
            f".env file permissions ({perms})",
            perms == "600",
            "Run: chmod 600 .env (currently readable by others)"
        )

    # Summary
    print()
    print("=" * 50)
    total = passed + failed + warnings
    print(f"  Results: {passed}/{total} passed, {failed} failed, {warnings} warnings")
    if failed == 0:
        print("  Your setup looks good!")
    else:
        print(f"  Fix the {failed} failed check(s) above before running.")
    print("=" * 50)

    return failed == 0


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
    upload_parser.add_argument("--dry-run", action="store_true", help="Show what would happen without uploading")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run one cycle (for cron)")
    run_parser.add_argument("--tiktok", action="store_true", help="Also upload to TikTok")
    run_parser.add_argument("--dry-run", action="store_true", help="Show what would happen without uploading")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show progress status")

    # Test command
    test_parser = subparsers.add_parser("test", help="Verify setup (checks all dependencies)")

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
    elif args.command == "test":
        test_command(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
