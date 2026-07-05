"""
YouTube title + description generation (build spec item 07).

Before a reel is uploaded, Gemini turns the raw Instagram caption into a
proper short YouTube title and a useful description — and THOSE are what the
upload actually sends. This is wired into the posting path, not a dashboard
suggestion: no action needed for it to take effect.

Best-effort by design: any failure falls back to the old behavior (first
caption line as title, caption as description), so metadata generation can
never block a post.
"""

import json
import os
import re
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except Exception:
    pass

GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)


def _sanitize(text: str) -> str:
    """YouTube rejects '<'/'>' in titles and descriptions."""
    return (text or "").replace("<", " less than ").replace(">", " greater than ")


def generate_metadata(caption: str, shortcode: str):
    """Return {'title': ..., 'description': ...} or None (caller falls back).

    Title: <= 95 chars, curiosity-driven, no clickbait lies, no hashtags.
    Description: a couple of useful sentences + hashtags incl. #Shorts.
    """
    key = os.environ.get("GEMINI_API_KEY")
    if not key or not (caption or "").strip():
        return None

    prompt = f"""You write YouTube Shorts metadata for a personal-finance/tech creator. Below is the Instagram caption of a reel being cross-posted to YouTube Shorts. Write:
1. "title" — a strong YouTube title, max 90 characters. Punchy and specific, in the creator's plain voice. No hashtags, no emojis, no quotes around it, no clickbait that the video can't back up. Never use the characters < or > (write "less than"/"greater than").
2. "description" — a useful 2-4 line description: one or two sentences that say what the viewer gets, then a final line of 3-5 relevant hashtags that MUST include #Shorts. Never use < or >.

INSTAGRAM CAPTION:
{caption[:2000]}

Return JSON exactly: {{"title": "...", "description": "..."}}"""

    try:
        res = requests.post(
            GEMINI_URL,
            params={"key": key},
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
            timeout=45,
        )
        res.raise_for_status()
        out = json.loads(res.json()["candidates"][0]["content"]["parts"][0]["text"])
        title = re.sub(r"\s+", " ", _sanitize(out.get("title", ""))).strip()[:100]
        description = _sanitize(out.get("description", "")).strip()
        if not title or not description:
            return None
        if "#shorts" not in description.lower():
            description += "\n#Shorts"
        print(f"[yt-metadata] generated title: {title}")
        return {"title": title, "description": description}
    except Exception as e:  # noqa: BLE001
        print(f"[yt-metadata] generation failed ({e}) — falling back to caption")
        return None
