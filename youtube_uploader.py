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
    credentials = None

    # Load saved credentials if they exist
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, 'rb') as token:
            credentials = pickle.load(token)

    # Refresh or get new credentials if needed
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
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

    except Exception as e:
        print(f"Error uploading to YouTube: {e}")
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

    except Exception as e:
        print(f"Error uploading to YouTube: {e}")
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
