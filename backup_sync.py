"""Backup sync: polls the content-engine shared list (Firestore) and maintains a
local JSON backup with change notifications.

Usage:
  python backup_sync.py init     # pull all posts, save to backup.json
  python backup_sync.py poll     # poll once and merge into backup.json, emit events
  python backup_sync.py run      # poll in a loop (every 5 minutes)
"""

import json
import os
import time
import smtplib
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Optional, List


BACKUP_FILE = Path.home() / ".instagram-tiktok-reposter" / "backup.json"
BACKUP_FILE.parent.mkdir(parents=True, exist_ok=True)

# Email config (optional: notifications only if all env vars are set)
NOTIFY_EMAIL = os.getenv("BACKUP_NOTIFY_EMAIL", "chas3.crummedyo@gmail.com")
SMTP_USER = os.getenv("GMAIL_BACKUP_USER", "")
SMTP_PASS = os.getenv("GMAIL_BACKUP_PASS", "")
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _firestore_client():
    """Initialize Firebase/Firestore client."""
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        sa_file = Path(__file__).parent / "content-engine-sa.json"
        if not sa_file.exists():
            print("[backup] no service-account key — cannot reach Firestore")
            return None

        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(str(sa_file)))
        return firestore.client()
    except Exception as e:
        print(f"[backup] Firestore init failed: {e}")
        return None


def fetch_all_posts() -> Optional[Dict[str, Dict]]:
    """Fetch all posts from Firestore. Returns dict keyed by shortcode, or None."""
    db = _firestore_client()
    if db is None:
        return None

    try:
        posts = {}
        for doc in db.collection("posts").stream():
            data = doc.to_dict()
            if data:
                posts[data.get("ig_shortcode")] = data
        print(f"[backup] fetched {len(posts)} posts from Firestore")
        return posts
    except Exception as e:
        print(f"[backup] fetch failed: {e}")
        return None


def load_backup() -> Dict[str, Dict]:
    """Load the local backup JSON. Returns empty dict if missing."""
    if BACKUP_FILE.exists():
        try:
            with open(BACKUP_FILE) as f:
                data = json.load(f)
                print(f"[backup] loaded {len(data)} posts from {BACKUP_FILE}")
                return data
        except Exception as e:
            print(f"[backup] load failed: {e}")
    return {}


def save_backup(posts: Dict[str, Dict]):
    """Save posts to local JSON."""
    try:
        with open(BACKUP_FILE, "w") as f:
            json.dump(posts, f, indent=2)
        print(f"[backup] saved {len(posts)} posts to {BACKUP_FILE}")
    except Exception as e:
        print(f"[backup] save failed: {e}")


def detect_changes(old_posts: Dict[str, Dict], new_posts: Dict[str, Dict]) -> List[Dict]:
    """Compare old and new post dicts. Return list of change events."""
    events = []

    # New posts
    for shortcode, new_post in new_posts.items():
        if shortcode not in old_posts:
            events.append({
                "type": "new",
                "shortcode": shortcode,
                "status": new_post.get("repost_status", "unknown"),
                "timestamp": datetime.now().isoformat(),
            })
        else:
            old_post = old_posts[shortcode]
            old_status = old_post.get("repost_status")
            new_status = new_post.get("repost_status")
            if old_status != new_status:
                events.append({
                    "type": "status_change",
                    "shortcode": shortcode,
                    "old_status": old_status,
                    "new_status": new_status,
                    "yt_url": new_post.get("yt_url"),
                    "timestamp": datetime.now().isoformat(),
                })

    # Deleted posts (from old but not in new) — rare, but log it
    for shortcode in old_posts:
        if shortcode not in new_posts:
            events.append({
                "type": "deleted",
                "shortcode": shortcode,
                "timestamp": datetime.now().isoformat(),
            })

    return events


def send_notification(event: Dict):
    """Send email notification for a change event."""
    if not NOTIFY_EMAIL:
        return

    subject = None
    body = None

    if event["type"] == "new":
        subject = f"📹 New post: {event['shortcode']} ({event['status']})"
        body = f"""New post detected:
Shortcode: {event['shortcode']}
Status: {event['status']}
Time: {event['timestamp']}
"""

    elif event["type"] == "status_change":
        subject = f"✏️ Status change: {event['shortcode']} → {event['new_status']}"
        body = f"""Post status updated:
Shortcode: {event['shortcode']}
Old status: {event['old_status']}
New status: {event['new_status']}
YouTube: {event.get('yt_url', 'N/A')}
Time: {event['timestamp']}
"""

    elif event["type"] == "deleted":
        subject = f"🗑️ Post deleted: {event['shortcode']}"
        body = f"""Post removed from shared list:
Shortcode: {event['shortcode']}
Time: {event['timestamp']}
"""

    if not subject or not body:
        return

    if not SMTP_USER or not SMTP_PASS:
        print(f"[backup] skipping email (no GMAIL_BACKUP_USER/GMAIL_BACKUP_PASS): {subject}")
        return

    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = NOTIFY_EMAIL
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        print(f"[backup] sent notification: {subject}")

    except Exception as e:
        print(f"[backup] email failed: {e}")


def init():
    """Pull all posts and save baseline."""
    new_posts = fetch_all_posts()
    if new_posts is None:
        print("[backup] init failed — could not reach Firestore")
        return

    save_backup(new_posts)
    print(f"[backup] initialized with {len(new_posts)} posts")


def poll():
    """Poll Firestore, merge into local backup, emit events."""
    new_posts = fetch_all_posts()
    if new_posts is None:
        print("[backup] poll skipped — could not reach Firestore")
        return

    old_posts = load_backup()
    events = detect_changes(old_posts, new_posts)

    if events:
        print(f"[backup] detected {len(events)} change(s)")
        for event in events:
            print(f"  - {event['type']}: {event['shortcode']}")
            send_notification(event)
    else:
        print("[backup] no changes detected")

    save_backup(new_posts)


def run(interval_seconds: int = 300):
    """Poll in a loop every `interval_seconds` (default 5 min)."""
    print(f"[backup] polling every {interval_seconds} seconds")
    try:
        while True:
            poll()
            print(f"[backup] sleeping {interval_seconds}s until next poll")
            time.sleep(interval_seconds)
    except KeyboardInterrupt:
        print("[backup] stopped by user")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "init":
        init()
    elif cmd == "poll":
        poll()
    elif cmd == "run":
        interval = int(sys.argv[2]) if len(sys.argv) > 2 else 300
        run(interval)
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
