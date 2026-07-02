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
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Dict

import config
from instagram_scraper import scrape_instagram_posts, load_progress, save_progress
from tiktok_uploader import upload_to_tiktok
from youtube_uploader import upload_to_youtube, _youtube_safe_title
from videom8_analyzer import analyze_reel, store_analysis_in_firestore


def _get_last_upload_time() -> Optional[float]:
    """Get the timestamp of the last upload to any platform (YouTube/TikTok)."""
    progress = load_progress()
    last_upload = progress.get("last_upload_time")
    if last_upload is not None:
        return float(last_upload)
    return None


def _is_upload_interval_satisfied() -> bool:
    """Check if at least 3 hours have passed since the last upload.

    If no upload has happened yet, returns True (allow first upload).
    """
    MIN_INTERVAL_HOURS = 3
    MIN_INTERVAL_SECS = MIN_INTERVAL_HOURS * 3600

    last_upload_time = _get_last_upload_time()
    if last_upload_time is None:
        return True  # No prior upload, allow

    elapsed = time.time() - last_upload_time
    return elapsed >= MIN_INTERVAL_SECS


def _record_upload_time():
    """Record the current time as the last upload timestamp."""
    progress = load_progress()
    progress["last_upload_time"] = time.time()
    save_progress(progress)


def _enforce_spacing_guard() -> bool:
    """Enforce that uploads are spaced at least 3 hours apart, with early exit.

    Returns True if the upload should proceed; False if the upload should be skipped
    because we're within 3 hours of the last upload. This guard fires BEFORE any
    database reads or network calls — it's cheap insurance against accidental bursts.
    """
    MIN_INTERVAL_HOURS = 3
    MIN_INTERVAL_SECS = MIN_INTERVAL_HOURS * 3600

    last_upload_time = _get_last_upload_time()
    if last_upload_time is None:
        return True  # No prior upload, allow

    elapsed = time.time() - last_upload_time
    if elapsed < MIN_INTERVAL_SECS:
        # Log for visibility but DON'T raise an exception — just return False
        # so the caller can decide how to handle it (print, log, silent skip).
        return False
    return True


def _lock_upload_cycle():
    """File-based lock to prevent rapid concurrent runs from posting in parallel.

    Once a run starts an upload, all subsequent runs (even in parallel shells) are
    blocked for 3 hours. This is the safety net: even if the script is called 5 times
    in 2 minutes, only the first one posts, and the rest respect the 3h interval.
    """
    LOCK_FILE = Path(__file__).parent / ".upload_lock"

    # Check if lock exists and is recent (< 3h old)
    if LOCK_FILE.exists():
        try:
            lock_time = float(LOCK_FILE.read_text())
            elapsed = time.time() - lock_time
            if elapsed < 3 * 3600:
                # Lock is active. Refuse to proceed.
                return False
        except (ValueError, OSError):
            # Corrupted lock file; treat as stale
            pass

    # Lock is stale or doesn't exist. Create a new one with the current time.
    # **This must happen BEFORE any upload to ensure concurrent runs see the lock.**
    current_time = time.time()
    try:
        LOCK_FILE.write_text(str(current_time))
    except OSError:
        pass  # If we can't write the lock, at least try to run (fail open)

    return True


def mark_uploaded(shortcode: str, platform: str = None):
    """Mark a post as uploaded. If platform specified, tracks per-platform."""
    progress = load_progress()

    if platform:
        key = f"uploaded_{platform}"
        platform_list = progress.get(key, [])
        if shortcode not in platform_list:
            platform_list.append(shortcode)
            progress[key] = platform_list

    # Check if post is done on ALL enabled platforms. A post on the YouTube
    # skip-list (recorded in "skipped_youtube") counts as handled for YouTube.
    all_done = True
    if (config.USE_YOUTUBE
            and shortcode not in progress.get("uploaded_youtube", [])
            and shortcode not in progress.get("skipped_youtube", [])):
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


# --- YouTube skip-list: reels the user has chosen to NEVER post to YouTube ---
SKIP_FILE = Path(__file__).parent / "youtube_skip.json"


def load_youtube_skip() -> set:
    """Return the set of Instagram shortcodes to omit from YouTube."""
    if SKIP_FILE.exists():
        try:
            with open(SKIP_FILE) as f:
                return set(json.load(f))
        except (json.JSONDecodeError, ValueError):
            return set()
    return set()


def add_youtube_skip(shortcode: str):
    """Add a shortcode to the YouTube skip-list (idempotent)."""
    skips = load_youtube_skip()
    skips.add(shortcode)
    with open(SKIP_FILE, "w") as f:
        json.dump(sorted(skips), f, indent=2)


def record_youtube_skip(shortcode: str):
    """Mark a post as intentionally omitted from YouTube (NOT uploaded).

    Records it in "skipped_youtube" for an honest audit trail, then recomputes
    completion so the post leaves the pending queue once every OTHER enabled
    platform is done (with TikTok off, that's immediately).
    """
    progress = load_progress()
    skipped = progress.get("skipped_youtube", [])
    if shortcode not in skipped:
        skipped.append(shortcode)
        progress["skipped_youtube"] = skipped
        save_progress(progress)
    mark_uploaded(shortcode)


def _extract_shortcode(value: str) -> str:
    """Pull the shortcode from an Instagram URL, or pass through a bare code."""
    value = value.strip().rstrip("/")
    m = re.search(r"/(?:reel|reels|p|tv)/([^/?#]+)", value)
    if m:
        return m.group(1)
    return value.split("?")[0].split("/")[-1]


def _record_repost_outcome(post: Dict, shortcode: str, success: bool, video_id):
    """Repost-check: record the YouTube outcome in the Content Engine shared
    list, and email an alert when it failed. Never breaks the run."""
    caption = post.get("caption", "")
    ig_url = f"https://www.instagram.com/reel/{shortcode}/"
    try:
        from content_engine_sync import record_repost
    except Exception as e:  # noqa: BLE001
        print(f"[content-engine] sync unavailable: {e}")
        record_repost = None

    if success:
        yt_url = f"https://youtube.com/shorts/{video_id}" if video_id else None
        title = _youtube_safe_title(caption, shortcode) if caption else None
        if record_repost:
            record_repost(shortcode, "posted", yt_url=yt_url, yt_title=title,
                          ig_url=ig_url, caption=caption)
    else:
        if record_repost:
            record_repost(shortcode, "failed", ig_url=ig_url, caption=caption)
        try:
            from notifier import send_failure_email
            send_failure_email(
                subject=f"Repost FAILED: {shortcode}",
                body=(f"The reel {shortcode} failed to post to YouTube.\n\n"
                      f"Instagram: {ig_url}\n"
                      f"Caption: {caption[:200]}\n\n"
                      f"Check cron.log on the Mac mini."),
            )
        except Exception as e:  # noqa: BLE001
            print(f"[email] could not send failure alert: {e}")


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
            post = json.load(f)

        # Normalize media file paths to current machine (handles migrations across machines)
        if "media_files" in post and post["media_files"]:
            post["media_files"] = [
                str(post_dir / Path(mf).name) for mf in post["media_files"]
            ]

        return post

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

    # Acquire upload cycle lock (prevents rapid direct calls from bursting)
    if not dry_run and not _lock_upload_cycle():
        last_upload_time = _get_last_upload_time()
        elapsed_hours = (time.time() - last_upload_time) / 3600 if last_upload_time else 0
        print(f"Upload cycle locked: posted {elapsed_hours:.1f}h ago (minimum 3h required). Skipping.")
        return

    # Early exit: enforce 3-hour spacing BEFORE any work
    if not _enforce_spacing_guard():
        last_upload_time = _get_last_upload_time()
        elapsed_hours = (time.time() - last_upload_time) / 3600
        print(f"Spacing guard: uploaded {elapsed_hours:.1f}h ago (minimum 3h required). Skipping.")
        return

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
    yt_video_id = None

    if config.USE_YOUTUBE:
        if shortcode in load_youtube_skip():
            print("\n--- YouTube --- (omitted by user — on skip-list)")
            record_youtube_skip(shortcode)
        elif shortcode in progress.get("uploaded_youtube", []):
            print("\n--- YouTube --- (already uploaded, skipping)")
            youtube_success = True
            mark_uploaded(shortcode, "youtube")
        else:
            print("\n--- YouTube ---")
            yt_video_id = upload_to_youtube(post)
            youtube_success = bool(yt_video_id)
            if youtube_success:
                yt_url = f"https://youtube.com/shorts/{yt_video_id}"
                mark_uploaded(shortcode, "youtube")
                # Analyze the reel with Videom8 after successful upload
                print("\n--- Videom8 Analysis ---")
                analysis = analyze_reel(yt_url)
                if analysis:
                    store_analysis_in_firestore(shortcode, analysis, yt_url)

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

        _record_upload_time()
        # Also update the lock file so the 3h window resets from upload completion.
        LOCK_FILE = Path(__file__).parent / ".upload_lock"
        try:
            LOCK_FILE.write_text(str(time.time()))
        except OSError:
            pass
    else:
        print(f"\nFailed to upload: {post['shortcode']}")


def run_command(args):
    """Run one cycle: ensure posts are downloaded, upload one"""
    dry_run = getattr(args, 'dry_run', False)

    print("=" * 50)
    print("Running repost cycle..." + (" [DRY RUN]" if dry_run else ""))
    print("=" * 50)

    # Acquire upload cycle lock (prevents parallel runs from bursting)
    if not dry_run and not _lock_upload_cycle():
        last_upload_time = _get_last_upload_time()
        elapsed_hours = (time.time() - last_upload_time) / 3600 if last_upload_time else 0
        print(f"Upload cycle locked: posted {elapsed_hours:.1f}h ago (minimum 3h required). Skipping.")
        return

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

    # Honor the YouTube skip-list. With TikTok disabled this omits the post
    # entirely; advance to the next pending post so the run still works.
    shortcode = post['shortcode']
    if shortcode in load_youtube_skip():
        print(f"Post {shortcode} is on the YouTube skip-list (omitted by user), skipping...")
        if not dry_run:
            record_youtube_skip(shortcode)
            run_command(args)  # try the next post
        else:
            print("[DRY RUN] Would omit this post and try the next")
        return

    # Check posting interval before attempting upload
    if not _enforce_spacing_guard():
        last_upload_time = _get_last_upload_time()
        elapsed_hours = (time.time() - last_upload_time) / 3600
        print(f"Spacing guard: uploaded {elapsed_hours:.1f}h ago (minimum 3h required). Skipping.")
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
    video_id = None
    progress = load_progress()
    if config.USE_YOUTUBE:
        if shortcode in progress.get("uploaded_youtube", []):
            print("[YouTube] Already uploaded, skipping")
            youtube_success = True
        else:
            video_id = upload_to_youtube(post)
            youtube_success = bool(video_id)
            # Repost-check: record the outcome to the shared list + alert on failure
            _record_repost_outcome(post, shortcode, youtube_success, video_id)
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

        # Analyze the uploaded reel with Videom8 if YouTube upload succeeded
        if youtube_success:
            yt_url = f"https://youtube.com/shorts/{video_id}"
            print(f"\n--- Videom8 Analysis ---")
            analysis = analyze_reel(yt_url)
            if analysis:
                store_analysis_in_firestore(shortcode, analysis, yt_url)
            else:
                print(f"[videom8] Analysis skipped for {shortcode}")

        _record_upload_time()
        # Also update the lock file so the 3h window resets from upload completion.
        # This ensures the lock file and progress.json stay in sync.
        LOCK_FILE = Path(__file__).parent / ".upload_lock"
        try:
            LOCK_FILE.write_text(str(time.time()))
        except OSError:
            pass
    else:
        print(f"Failed to upload: {shortcode}")


def skip_command(args):
    """Manage the YouTube skip-list (reels to never post to YouTube)."""
    if args.list or not args.items:
        skips = sorted(load_youtube_skip())
        print(f"YouTube skip-list ({len(skips)} reel(s) — never posted to YouTube):")
        for sc in skips:
            print(f"  {sc}")
        if not skips:
            print("  (empty)")
        if not args.items:
            return

    codes = [_extract_shortcode(x) for x in args.items]
    if args.remove:
        skips = load_youtube_skip()
        for c in codes:
            skips.discard(c)
        with open(SKIP_FILE, "w") as f:
            json.dump(sorted(skips), f, indent=2)
        print(f"Removed from skip-list: {', '.join(codes)}")
    else:
        for c in codes:
            add_youtube_skip(c)
        print(f"Added to YouTube skip-list (will never post to YouTube): {', '.join(codes)}")
    print(f"Skip-list is now: {sorted(load_youtube_skip())}")


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

    # Skip command (manage the YouTube skip-list)
    skip_parser = subparsers.add_parser("skip", help="Omit reels from YouTube (skip-list)")
    skip_parser.add_argument("items", nargs="*", help="Instagram reel URLs or shortcodes to omit")
    skip_parser.add_argument("--list", action="store_true", help="Show the current skip-list")
    skip_parser.add_argument("--remove", action="store_true", help="Remove the given items from the skip-list")

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
    elif args.command == "skip":
        skip_command(args)
    elif args.command == "status":
        status_command(args)
    elif args.command == "test":
        test_command(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
