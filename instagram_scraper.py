"""
Instagram Scraper Module
Downloads posts from your Instagram profile using Playwright
"""

import json
import random
import time
from pathlib import Path
from typing import Optional, List, Dict
from playwright.sync_api import sync_playwright, Page, Browser
import config


def human_delay(min_sec: float = None, max_sec: float = None):
    """Add random delay to simulate human behavior"""
    min_sec = min_sec or config.HUMAN_DELAY_MIN
    max_sec = max_sec or config.HUMAN_DELAY_MAX
    time.sleep(random.uniform(min_sec, max_sec))


def login_instagram(page: Page) -> bool:
    """Login to Instagram if not already logged in"""
    page.goto("https://www.instagram.com/", timeout=60000)
    human_delay(5, 7)

    # Handle cookie popup if present
    try:
        cookie_btn = page.locator('button:has-text("Allow all cookies"), button:has-text("Accept")')
        if cookie_btn.count() > 0:
            cookie_btn.first.click()
            human_delay(2, 3)
    except:
        pass

    # Check if already logged in with multiple indicators
    logged_in_indicators = [
        '[aria-label="Home"]',
        'svg[aria-label="Home"]',
        'a[href="/direct/inbox/"]',
        'span[aria-label="Profile"]',
    ]

    for selector in logged_in_indicators:
        try:
            if page.locator(selector).count() > 0:
                print("Already logged into Instagram")
                return True
        except:
            pass

    # Check if we're on the feed (another indicator of being logged in)
    if "instagram.com" in page.url and "login" not in page.url and "accounts" not in page.url:
        try:
            # Wait a bit and check for main content
            page.wait_for_timeout(3000)
            if page.locator('article').count() > 0 or page.locator('main').count() > 0:
                print("Already logged into Instagram (detected feed)")
                return True
        except:
            pass

    # Not logged in, proceed with login
    print("Logging into Instagram...")
    page.goto("https://www.instagram.com/accounts/login/")
    human_delay(3, 5)

    # Wait for login form
    try:
        page.wait_for_selector('input[name="username"]', timeout=10000)
    except Exception:
        print("ERROR: Could not find Instagram login form.")
        print("  -> Instagram may have changed their page layout.")
        print("  -> Try running 'python main.py init' to login manually instead.")
        return False

    # Fill credentials
    page.fill('input[name="username"]', config.INSTAGRAM_USERNAME)
    human_delay(0.5, 1)
    page.fill('input[name="password"]', config.INSTAGRAM_PASSWORD)
    human_delay(0.5, 1)

    # Click login
    page.click('button[type="submit"]')
    human_delay(8, 12)

    # Handle "Save Login Info" popup
    try:
        not_now = page.locator('button:has-text("Not Now"), div[role="button"]:has-text("Not Now")')
        if not_now.count() > 0:
            not_now.first.click()
            human_delay(2, 3)
    except:
        pass

    # Handle notifications popup
    try:
        not_now = page.locator('button:has-text("Not Now"), div[role="button"]:has-text("Not Now")')
        if not_now.count() > 0:
            not_now.first.click()
            human_delay(2, 3)
    except:
        pass

    # Verify login actually worked
    human_delay(3, 5)
    current_url = page.url

    # Check for challenge/verification pages
    if "challenge" in current_url or "two_factor" in current_url:
        print("WARNING: Instagram is requesting verification (2FA or suspicious login).")
        print("  -> Run 'python main.py init' to login manually in a browser.")
        return False

    # Check we're not still on the login page
    if "login" in current_url or "accounts/login" in current_url:
        print("WARNING: Login may have failed — still on login page.")
        print("  -> Check your credentials in .env")
        print("  -> Or run 'python main.py init' to login manually.")
        return False

    print("Logged into Instagram successfully")
    return True


def get_profile_posts(page: Page, username: str, max_posts: int = 500) -> List[Dict]:
    """Get list of posts from profile (posts tab + reels tab)"""
    posts = []

    # Only scrape reels (TikTok only accepts videos anyway)
    tabs_to_scrape = [
        (f"https://www.instagram.com/{username}/reels/", "reels"),
    ]

    for tab_url, tab_name in tabs_to_scrape:
        if len(posts) >= max_posts:
            break

        print(f"Fetching {tab_name} from @{username}...")
        page.goto(tab_url)
        human_delay(3, 5)

        last_height = 0
        scroll_attempts = 0
        max_scroll_attempts = 100  # Limit scrolling per tab

        while len(posts) < max_posts and scroll_attempts < max_scroll_attempts:
            # Find all post links (updated selector for current Instagram layout)
            post_links = page.locator('main a[href*="/p/"], main a[href*="/reel/"], a[href*="/p/"], a[href*="/reel/"]').all()

            for link in post_links:
                href = link.get_attribute("href")
                if href and href not in [p["url"] for p in posts]:
                    # Only include posts from this user's profile
                    if f"/{username}/" not in href:
                        continue
                    # Determine if it's a reel or regular post
                    is_reel = "/reel/" in href
                    posts.append({
                        "url": href,
                        "full_url": f"https://www.instagram.com{href}" if href.startswith("/") else href,
                        "is_reel": is_reel,
                        "shortcode": href.split("/")[-2] if href.endswith("/") else href.split("/")[-1]
                    })

            print(f"Found {len(posts)} posts so far...")

            # Scroll down
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            human_delay(2, 4)

            # Check if we've reached the bottom
            new_height = page.evaluate("document.body.scrollHeight")
            if new_height == last_height:
                scroll_attempts += 1
                if scroll_attempts > 3:
                    break
            else:
                scroll_attempts = 0
            last_height = new_height

    print(f"Found {len(posts)} total posts")
    return posts


def download_post(page: Page, post: dict, save_dir: Path) -> Optional[Dict]:
    """Download a single post using yt-dlp for proper video format and caption"""
    import subprocess

    shortcode = post["shortcode"]
    save_path = save_dir / shortcode
    save_path.mkdir(exist_ok=True)

    print(f"Downloading post {shortcode}...")

    result = {
        "shortcode": shortcode,
        "url": post["full_url"],
        "is_reel": post["is_reel"],
        "media_files": [],
        "caption": "",
    }

    # Use yt-dlp to download video and get caption
    video_path = save_path / "video.mp4"
    try:
        # Get cookies from browser for authentication
        cookies_path = save_path / "cookies.txt"

        # Export cookies from playwright browser
        cookies = page.context.cookies()
        with open(cookies_path, 'w') as f:
            f.write("# Netscape HTTP Cookie File\n")
            for cookie in cookies:
                domain = cookie.get('domain', '')
                if 'instagram' in domain:
                    secure = "TRUE" if cookie.get('secure') else "FALSE"
                    http_only = "TRUE" if cookie.get('httpOnly') else "FALSE"
                    expires = str(int(cookie.get('expires', 0)))
                    f.write(f"{domain}\tTRUE\t{cookie.get('path', '/')}\t{secure}\t{expires}\t{cookie.get('name')}\t{cookie.get('value')}\n")

        # Get caption with yt-dlp
        caption_cmd = [
            'yt-dlp',
            '--cookies', str(cookies_path),
            '--print', '%(description)s',
            '--no-warnings',
            '--quiet',
            post["full_url"]
        ]
        caption_result = subprocess.run(caption_cmd, capture_output=True, text=True, timeout=30)
        if caption_result.returncode == 0 and caption_result.stdout.strip():
            result["caption"] = caption_result.stdout.strip()

        # Download video with yt-dlp
        download_cmd = [
            'yt-dlp',
            '--cookies', str(cookies_path),
            '-o', str(video_path),
            '--no-warnings',
            '--quiet',
            post["full_url"]
        ]
        subprocess.run(download_cmd, capture_output=True, timeout=120)

        # Clean up cookies file
        if cookies_path.exists():
            cookies_path.unlink()

        if video_path.exists():
            result["media_files"].append(str(video_path))
            print(f"Downloaded video: {video_path}")
        else:
            print(f"yt-dlp did not create video file")

    except Exception as e:
        print(f"Error downloading with yt-dlp: {e}")

    if result["media_files"]:
        # Save metadata
        meta_path = save_path / "metadata.json"
        with open(meta_path, "w") as f:
            json.dump(result, f, indent=2)
        return result

    return None


def scrape_instagram_posts(username: str = None, max_posts: int = 500) -> List[Dict]:
    """Main function to scrape Instagram posts"""
    username = username or config.INSTAGRAM_USERNAME
    config.MEDIA_DIR.mkdir(exist_ok=True)
    config.BROWSER_STATE_DIR.mkdir(exist_ok=True)

    with sync_playwright() as p:
        # Launch browser with persistent context to save login state
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(config.BROWSER_STATE_DIR / "instagram"),
            headless=config.HEADLESS,
            viewport={"width": 1280, "height": 720},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        page = browser.pages[0] if browser.pages else browser.new_page()

        try:
            # Login
            if not login_instagram(page):
                print("ERROR: Could not log into Instagram.")
                print("  -> Run 'python main.py init' to re-login manually.")
                return []

            # Verify session by navigating to profile
            page.goto(f"https://www.instagram.com/{username}/", timeout=30000)
            human_delay(3, 5)
            if "login" in page.url:
                print("ERROR: Instagram session expired — got redirected to login.")
                print("  -> Run 'python main.py init' to re-login manually.")
                return []

            # Get posts list
            posts = get_profile_posts(page, username, max_posts)

            # Load progress to skip already downloaded
            progress = load_progress()
            downloaded = progress.get("downloaded", [])

            results = []
            for post in posts:
                if post["shortcode"] in downloaded:
                    print(f"Skipping already downloaded: {post['shortcode']}")
                    continue

                result = download_post(page, post, config.MEDIA_DIR)
                if result:
                    results.append(result)
                    downloaded.append(post["shortcode"])
                    save_progress({"downloaded": downloaded, "uploaded": progress.get("uploaded", [])})

                human_delay(2, 4)

            return results

        finally:
            browser.close()


def load_progress() -> dict:
    """Load progress from file"""
    if config.PROGRESS_FILE.exists():
        with open(config.PROGRESS_FILE) as f:
            return json.load(f)
    return {"downloaded": [], "uploaded": []}


def save_progress(progress: dict):
    """Save progress to file"""
    with open(config.PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


if __name__ == "__main__":
    # Test scraping
    posts = scrape_instagram_posts(max_posts=5)
    print(f"Downloaded {len(posts)} posts")
