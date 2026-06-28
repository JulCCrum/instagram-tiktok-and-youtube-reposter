"""Bridge from the reposter to the Content Engine's shared list (Firestore).

After the bot posts a reel to YouTube, it records the outcome in the
`content-engine-jpa` Firestore `posts` collection so the rest of the system
(Review, Dashboard, Iterate) sees it. Each reel is one post document, keyed by
its Instagram shortcode.

Safe by design: every call is wrapped so a sync failure never breaks posting.
Requires a service-account key at content-engine-sa.json (gitignored).
"""

import os
import time
from pathlib import Path

_SA_FILE = Path(__file__).parent / "content-engine-sa.json"
_db = None


def _client():
    """Lazily init the Firestore client. Returns None if unavailable."""
    global _db
    if _db is not None:
        return _db
    if not _SA_FILE.exists():
        print("[content-engine] no service-account key — skipping shared-list sync")
        return None
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            firebase_admin.initialize_app(credentials.Certificate(str(_SA_FILE)))
        _db = firestore.client()
        return _db
    except Exception as e:  # noqa: BLE001
        print(f"[content-engine] could not init Firestore: {e}")
        return None


def record_repost(
    shortcode: str,
    repost_status: str,
    *,
    yt_url: str | None = None,
    yt_title: str | None = None,
    ig_url: str | None = None,
    caption: str | None = None,
) -> bool:
    """Upsert this reel's post in the shared list. Never raises.

    repost_status: 'posted' | 'failed' | 'pending'
    Returns True if the write succeeded.
    """
    db = _client()
    if db is None:
        return False
    try:
        now = int(time.time() * 1000)  # epoch ms, matches the Next.js app
        doc = db.collection("posts").document(shortcode)
        data = {
            "ig_shortcode": shortcode,
            "repost_status": repost_status,
            "updated_at": now,
            # created_at only on first write
            "created_at": firestore_min(doc, now),
        }
        if repost_status == "posted":
            data["status"] = "posted"
        if yt_url:
            data["yt_url"] = yt_url
        if yt_title:
            data["yt_title"] = yt_title
        if ig_url:
            data["ig_url"] = ig_url
        if caption:
            # first line doubles as the on-screen hook for now
            data["hook_screen"] = caption.split("\n", 1)[0][:300]
        doc.set(data, merge=True)
        print(f"[content-engine] recorded {shortcode} -> {repost_status}")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[content-engine] sync failed for {shortcode}: {e}")
        return False


def firestore_min(doc_ref, now: int) -> int:
    """Return existing created_at if the doc already exists, else now."""
    try:
        snap = doc_ref.get()
        if snap.exists:
            existing = snap.to_dict().get("created_at")
            if isinstance(existing, int):
                return existing
    except Exception:  # noqa: BLE001
        pass
    return now
