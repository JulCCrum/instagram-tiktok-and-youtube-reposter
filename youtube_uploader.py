"""
YouTube Shorts Uploader Module
Uploads videos to YouTube as Shorts using the YouTube Data API
"""

import os
import pickle
from pathlib import Path
from typing import Optional, Dict

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import config

# YouTube API scopes
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']

# Path to credentials
CLIENT_SECRETS_FILE = Path(__file__).parent / "client_secrets.json"
TOKEN_FILE = Path(__file__).parent / "youtube_token.pickle"


def get_authenticated_service():
    """Get authenticated YouTube service"""
    if not CLIENT_SECRETS_FILE.exists():
        print("ERROR: client_secrets.json not found.")
        print("  -> You need YouTube API credentials from Google Cloud Console.")
        print("  -> Steps:")
        print("     1. Go to https://console.cloud.google.com/")
        print("     2. Create a project and enable 'YouTube Data API v3'")
        print("     3. Create OAuth 2.0 credentials (Desktop App)")
        print("     4. Download the JSON and save as 'client_secrets.json'")
        print(f"        in: {CLIENT_SECRETS_FILE.parent}/")
        raise FileNotFoundError("client_secrets.json missing — see instructions above")

    credentials = None

    # Load saved credentials if they exist
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, 'rb') as token:
            credentials = pickle.load(token)

    # Refresh or get new credentials if needed
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
            except Exception as e:
                print(f"WARNING: Could not refresh YouTube token: {e}")
                print("  -> Re-authenticating...")
                credentials = None
        if not credentials or not credentials.valid:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRETS_FILE), SCOPES)
            credentials = flow.run_local_server(port=8080)

        # Save credentials for next run
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(credentials, token)

    return build('youtube', 'v3', credentials=credentials)


def convert_video_for_youtube(input_path: str) -> str:
    """Convert fragmented MP4 to regular MP4 for YouTube compatibility"""
    import subprocess

    output_path = input_path.replace('.mp4', '_youtube.mp4')

    # Skip if already converted
    if os.path.exists(output_path):
        return output_path

    try:
        # Remux fragmented MP4 to regular MP4
        result = subprocess.run([
            'ffmpeg', '-i', input_path,
            '-c', 'copy',  # Copy streams without re-encoding
            '-movflags', '+faststart',  # Move moov atom to beginning
            '-y',  # Overwrite output
            output_path
        ], capture_output=True, text=True, timeout=60)

        if result.returncode == 0 and os.path.exists(output_path):
            print(f"Converted video for YouTube: {output_path}")
            return output_path
        else:
            print(f"ffmpeg error: {result.stderr}")
            return input_path
    except Exception as e:
        print(f"Error converting video: {e}")
        return input_path


def upload_to_youtube(post: Dict) -> bool:
    """Upload a video to YouTube as a Short"""

    # Find video file
    video_files = [f for f in post.get("media_files", []) if f.endswith(".mp4") and "_youtube" not in f]
    if not video_files:
        print("No video file found in post")
        return False

    video_path = video_files[0]

    if not os.path.exists(video_path):
        print(f"Video file not found: {video_path}")
        return False

    # Convert video for YouTube compatibility
    video_path = convert_video_for_youtube(video_path)

    try:
        youtube = get_authenticated_service()

        # Prepare video metadata
        caption = post.get("caption", "")

        # Add #Shorts hashtag if not present (required for YouTube Shorts)
        if "#shorts" not in caption.lower():
            caption = f"{caption}\n\n#Shorts"

        # Truncate title if too long (YouTube limit is 100 chars)
        title = caption[:100] if caption else f"Short - {post['shortcode']}"

        body = {
            'snippet': {
                'title': title,
                'description': caption,
                'tags': ['Shorts'],
                'categoryId': '22'  # People & Blogs
            },
            'status': {
                'privacyStatus': 'public',
                'selfDeclaredMadeForKids': False
            }
        }

        # Upload video
        media = MediaFileUpload(
            video_path,
            mimetype='video/mp4',
            resumable=True
        )

        print(f"Uploading to YouTube: {post['shortcode']}")

        request = youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )

        response = request.execute()

        video_id = response.get('id')
        print(f"Successfully uploaded to YouTube: https://youtube.com/shorts/{video_id}")
        return True

    except FileNotFoundError:
        return False  # Already printed detailed message in get_authenticated_service
    except Exception as e:
        error_msg = str(e).lower()
        print(f"ERROR uploading to YouTube: {e}")
        if "quota" in error_msg or "rateLimitExceeded" in str(e):
            print("  -> YouTube API daily quota exceeded.")
            print("  -> Fix: Wait until midnight Pacific Time for quota reset.")
            print("  -> Or request higher quota at https://console.cloud.google.com/")
        elif "forbidden" in error_msg or "403" in error_msg:
            print("  -> YouTube rejected the upload. Your API credentials may lack permissions.")
            print("  -> Fix: Re-run 'python youtube_uploader.py' to re-authenticate.")
        elif "invalid" in error_msg and "token" in error_msg:
            print("  -> YouTube auth token is invalid or expired.")
            print("  -> Fix: Delete youtube_token.pickle and re-run 'python youtube_uploader.py'")
        elif "network" in error_msg or "connection" in error_msg or "timeout" in error_msg:
            print("  -> Network error. Check your internet connection and try again.")
        else:
            print("  -> If this persists, try deleting youtube_token.pickle and re-authenticating.")
        return False


def upload_to_youtube_scheduled(post: Dict, publish_time) -> bool:
    """Upload a video to YouTube as a Short with scheduled publish time"""
    from datetime import datetime

    # Find video file
    video_files = [f for f in post.get("media_files", []) if f.endswith(".mp4") and "_youtube" not in f]
    if not video_files:
        print("No video file found in post")
        return False

    video_path = video_files[0]

    if not os.path.exists(video_path):
        print(f"Video file not found: {video_path}")
        return False

    # Convert video for YouTube compatibility
    video_path = convert_video_for_youtube(video_path)

    try:
        youtube = get_authenticated_service()

        # Prepare video metadata
        caption = post.get("caption", "")

        # Add #Shorts hashtag if not present
        if "#shorts" not in caption.lower():
            caption = f"{caption}\n\n#Shorts"

        # Truncate title if too long
        title = caption[:100] if caption else f"Short - {post['shortcode']}"

        # Format publish time for YouTube API (ISO 8601)
        publish_at = publish_time.strftime('%Y-%m-%dT%H:%M:%S.000Z')

        body = {
            'snippet': {
                'title': title,
                'description': caption,
                'tags': ['Shorts'],
                'categoryId': '22'
            },
            'status': {
                'privacyStatus': 'private',  # Must be private for scheduling
                'publishAt': publish_at,
                'selfDeclaredMadeForKids': False
            }
        }

        media = MediaFileUpload(
            video_path,
            mimetype='video/mp4',
            resumable=True
        )

        print(f"Uploading to YouTube (scheduled for {publish_time.strftime('%I:%M %p')})...")

        request = youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )

        response = request.execute()

        video_id = response.get('id')
        print(f"Scheduled on YouTube: https://youtube.com/shorts/{video_id}")
        return True

    except FileNotFoundError:
        return False
    except Exception as e:
        error_msg = str(e).lower()
        print(f"ERROR scheduling on YouTube: {e}")
        if "quota" in error_msg or "rateLimitExceeded" in str(e):
            print("  -> YouTube API daily quota exceeded. Wait until midnight PT.")
        elif "forbidden" in error_msg or "403" in error_msg:
            print("  -> Permission denied. Re-authenticate: python youtube_uploader.py")
        else:
            print("  -> If this persists, delete youtube_token.pickle and re-authenticate.")
        return False


def authorize_youtube():
    """Run authorization flow to get YouTube credentials"""
    print("Starting YouTube authorization...")
    try:
        youtube = get_authenticated_service()
        # Test the connection
        youtube.channels().list(part='snippet', mine=True).execute()
        print("YouTube authorization successful!")
        return True
    except Exception as e:
        print(f"YouTube authorization failed: {e}")
        return False


if __name__ == "__main__":
    authorize_youtube()
