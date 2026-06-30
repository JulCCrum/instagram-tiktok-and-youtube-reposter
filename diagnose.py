#!/usr/bin/env python3
"""
Simple pipeline diagnostic — shows what's at each stage without fetching/running anything.
Usage: python diagnose.py
"""
import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime

def get_latest_posts(count=10):
    """Get latest N posts from the local posts.json file."""
    posts_file = Path('posts.json')
    if not posts_file.exists():
        return []

    with open(posts_file) as f:
        posts = json.load(f).get('posts', [])

    # Sort by date descending, return latest N
    posts.sort(key=lambda p: p.get('date', ''), reverse=True)
    return posts[:count]

def get_media_queue():
    """List media files queued for upload (in media/downloads)."""
    media_dir = Path('media/downloads')
    if not media_dir.exists():
        return []

    files = list(media_dir.glob('*.mp4')) + list(media_dir.glob('*.mkv'))
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)

    return [
        {
            'file': f.name,
            'size_mb': round(f.stat().st_size / 1024 / 1024, 1),
            'time': datetime.fromtimestamp(f.stat().st_mtime).isoformat()
        }
        for f in files[:10]
    ]

def get_firestore_state():
    """Show recent Firestore sync activity (from logs or last_sync marker)."""
    last_sync_file = Path('.last_sync')
    if last_sync_file.exists():
        with open(last_sync_file) as f:
            last_sync = f.read().strip()
        return {'last_firestore_sync': last_sync}
    return {'last_firestore_sync': 'never'}

def main():
    print("\n" + "="*60)
    print("INSTAGRAM-TIKTOK REPOSTER: PIPELINE DIAGNOSTIC")
    print("="*60 + "\n")

    # Stage 1: Recent posts in posts.json
    print("📱 STAGE 1: Posts.json (Instagram scraper output)")
    print("-" * 60)
    posts = get_latest_posts(5)
    if posts:
        for i, post in enumerate(posts, 1):
            code = post.get('code', 'unknown')
            date = post.get('date', 'unknown')[:10]
            reposted = post.get('reposted', False)
            status = "✅ reposted" if reposted else "⏳ pending repost"
            print(f"  {i}. {code} ({date}) — {status}")
    else:
        print("  (no posts found)")

    # Stage 2: Media queue
    print("\n📹 STAGE 2: Media queue (downloads waiting for upload)")
    print("-" * 60)
    queue = get_media_queue()
    if queue:
        for i, media in enumerate(queue[:5], 1):
            print(f"  {i}. {media['file']} ({media['size_mb']}MB) — {media['time']}")
    else:
        print("  (queue empty — all files uploaded or none downloaded yet)")

    # Stage 3: Firestore sync
    print("\n☁️  STAGE 3: Firestore shared list")
    print("-" * 60)
    sync_state = get_firestore_state()
    print(f"  Last sync: {sync_state['last_firestore_sync']}")

    print("\n" + "="*60)
    print("NEXT STEPS:")
    print("  - Post new content to Instagram")
    print("  - Run: python main.py run")
    print("  - Then run: python diagnose.py")
    print("  - Content should progress: posts.json → media queue → Firestore")
    print("="*60 + "\n")

if __name__ == '__main__':
    main()
