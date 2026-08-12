#!/usr/bin/env python3
"""Verify which Instagram reels are actually on YouTube.

Uses the existing upload token but requests an additional read-only scope.
This SHOULD trigger a one-time consent so the account we're already
connected to gets read access. Afterwards the same token works for both
upload + read going forward.
"""
import json
import pickle
from pathlib import Path

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

CLIENT_SECRETS_FILE = Path(__file__).parent / "client_secrets.json"
TOKEN_FILE = Path(__file__).parent / "youtube_token.pickle"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]


def list_shorts():
    if not CLIENT_SECRETS_FILE.exists():
        print("ERROR: client_secrets.json not found")
        return

    credentials = None
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, "rb") as tk:
            credentials = pickle.load(tk)

    if credentials and credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(Request())
        except Exception as e:
            print(f"Refresh failed: {e}")
            credentials = None

    if not credentials or not credentials.valid or "readonly" not in credentials.scopes:
        print("A browser tab will open for a one-time read consent (you're already logged in).")
        flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRETS_FILE), SCOPES)
        credentials = flow.run_local_server(port=9090)
        with open(TOKEN_FILE, "wb") as tk:
            pickle.dump(credentials, tk)

    youtube = build("youtube", "v3", credentials=credentials)

    channels = youtube.channels().list(part="contentDetails", mine=True).execute()
    if not channels.get("items"):
        print("No channel found.")
        return

    uploads_playlist_id = channels["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    print(f"Uploads playlist: {uploads_playlist_id}")

    all_video_ids = []
    next_page_token = None
    while True:
        resp = youtube.playlistItems().list(
            part="snippet",
            playlistId=uploads_playlist_id,
            maxResults=50,
            pageToken=next_page_token,
        ).execute()
        for item in resp.get("items", []):
            all_video_ids.append(item["snippet"]["resourceId"]["videoId"])
        next_page_token = resp.get("nextPageToken")
        if not next_page_token:
            break

    print(f"Found {len(all_video_ids)} videos on YouTube channel.\n")

    yt_captions = {}
    for i in range(0, len(all_video_ids), 50):
        batch = all_video_ids[i:i+50]
        resp = youtube.videos().list(part="snippet", id=",".join(batch)).execute()
        for item in resp.get("items", []):
            yt_captions[item["id"]] = {
                "title": item["snippet"].get("title", "").strip(),
                "description": item["snippet"].get("description", "").strip(),
            }

    media_dir = Path(__file__).parent / "media"
    local_reels = {}
    for meta_file in sorted(media_dir.glob("*/metadata.json")):
        with open(meta_file) as f:
            meta = json.load(f)
        sc = meta.get("shortcode", "")
        caption = meta.get("caption", "")
        local_reels[sc] = {"first_line": caption.split("\n", 1)[0].strip(), "full": caption}

    matched = set()
    for vid, yt_data in yt_captions.items():
        blob = yt_data["description"] + " \n " + yt_data["title"]
        for sc, local in local_reels.items():
            if sc in matched:
                continue
            fl = local["first_line"]
            full = local["full"]
            if fl and len(fl) > 10 and (fl in blob or fl[:60] in blob):
                matched.add(sc)
            elif full and len(full) > 20 and full[:100] in blob:
                matched.add(sc)

    not_matched = set(local_reels.keys()) - matched
    print("=== RESULTS ===")
    print(f"Videos on YouTube channel: {len(all_video_ids)}")
    print(f"Local reels matched to YouTube: {len(matched)}")
    print(f"Local reels NOT found on YouTube: {len(not_matched)}")
    print()
    if not_matched:
        print("Reels NOT found on YouTube (first 40):")
        for sc in sorted(not_matched)[:40]:
            print(f"  https://www.instagram.com/reel/{sc}/")
            print(f"    -> {local_reels[sc]['first_line'][:80]}")
    return {"youtube_count": len(all_video_ids), "matched": len(matched), "unmatched": sorted(not_matched)}


if __name__ == "__main__":
    list_shorts()
