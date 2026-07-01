#!/usr/bin/env python3
"""
Videom8 Reel Analyzer Integration
Calls the Videom8 Cloud Run service to analyze a reel after it's been posted.
Stores the analysis in Firestore via the content engine.
"""

import requests
import json
import sys
from typing import Optional, Dict

VIDEOM8_API = "https://videom8-api-358448469721.us-central1.run.app/api/analyze"
TIMEOUT_SECS = 120  # 2 minutes — Videom8 takes ~40–60s


def analyze_reel(yt_url: str) -> Optional[Dict]:
    """
    Call Videom8 to analyze a reel. Returns the analysis object (video_style,
    topic, verdict_headline, takeaways, etc.) or None if the call fails.
    """
    if not yt_url:
        print("[videom8] No YouTube URL provided, skipping analysis")
        return None

    try:
        files = {"a_url": (None, yt_url)}
        print(f"[videom8] Analyzing {yt_url[:50]}...")
        res = requests.post(VIDEOM8_API, files=files, timeout=TIMEOUT_SECS)

        if not res.ok:
            error_text = res.text[:200] if res.text else f"HTTP {res.status_code}"
            print(f"[videom8] Error {res.status_code}: {error_text}")
            return None

        data = res.json()
        analysis = data.get("a")
        if not analysis:
            print("[videom8] No analysis in response")
            return None

        print(f"[videom8] ✓ Analysis complete: {analysis.get('video_style', 'unknown')} style")
        return analysis

    except requests.Timeout:
        print(f"[videom8] Timeout after {TIMEOUT_SECS}s")
        return None
    except requests.RequestException as e:
        print(f"[videom8] Request failed: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"[videom8] Invalid JSON response: {e}")
        return None
    except Exception as e:  # noqa: BLE001
        print(f"[videom8] Unexpected error: {e}")
        return None


def store_analysis_in_firestore(shortcode: str, analysis: Dict, yt_url: str) -> bool:
    """
    Store the analysis in Firestore via the content engine's record_repost API.
    This updates the post doc with videom8_analysis + videom8_analyzed_at.
    """
    try:
        from content_engine_sync import record_repost
    except ImportError:
        print("[videom8] content_engine_sync not available, skipping Firestore store")
        return False

    try:
        # record_repost accepts videom8_analysis dict which will be merged
        # into the post doc
        record_repost(shortcode, "analyzed", yt_url=yt_url,
                      videom8_analysis=analysis)
        print("[videom8] ✓ Analysis stored in Firestore")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[videom8] Failed to store analysis: {e}")
        return False


if __name__ == "__main__":
    # Simple CLI for testing
    if len(sys.argv) < 2:
        print("Usage: python videom8_analyzer.py <youtube_url>")
        sys.exit(1)

    url = sys.argv[1]
    result = analyze_reel(url)
    if result:
        print(json.dumps(result, indent=2))
    else:
        print("Analysis failed")
        sys.exit(1)
