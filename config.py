import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Credentials
INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")
TIKTOK_USERNAME = os.getenv("TIKTOK_USERNAME")
TIKTOK_PASSWORD = os.getenv("TIKTOK_PASSWORD")

# Paths
BASE_DIR = Path(__file__).parent
MEDIA_DIR = BASE_DIR / "media"
PROGRESS_FILE = BASE_DIR / "progress.json"
BROWSER_STATE_DIR = BASE_DIR / "browser_state"

# Settings
HEADLESS = True  # Set to False for debugging
POST_INTERVAL_HOURS = 3
HUMAN_DELAY_MIN = 2  # Minimum seconds between actions
HUMAN_DELAY_MAX = 5  # Maximum seconds between actions
