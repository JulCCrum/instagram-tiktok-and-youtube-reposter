#!/usr/bin/env python3
"""
Interactive configuration wizard for Instagram/TikTok/YouTube Reposter.
Generates .env, user_config.json, and sets up cron automation.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
ENV_FILE = BASE_DIR / ".env"
CONFIG_FILE = BASE_DIR / "user_config.json"


def ask(prompt: str, default: str = "") -> str:
    """Ask user for input with optional default."""
    if default:
        val = input(f"  {prompt} [{default}]: ").strip()
        return val if val else default
    else:
        while True:
            val = input(f"  {prompt}: ").strip()
            if val:
                return val
            print("    (required)")


def ask_int(prompt: str, min_val: int, max_val: int, default: int = None) -> int:
    """Ask user for an integer within a range."""
    default_hint = f" [{default}]" if default is not None else ""
    while True:
        val = input(f"  {prompt} ({min_val}-{max_val}){default_hint}: ").strip()
        if not val and default is not None:
            return default
        try:
            num = int(val)
            if min_val <= num <= max_val:
                return num
            print(f"    Please enter a number between {min_val} and {max_val}")
        except ValueError:
            print(f"    That's not a number. Please enter a number between {min_val} and {max_val}")


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    """Ask yes/no question."""
    hint = "Y/n" if default else "y/N"
    val = input(f"  {prompt} ({hint}): ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes")


def ask_choice(prompt: str, options: list) -> str:
    """Ask user to pick from numbered options."""
    print(f"  {prompt}")
    for i, opt in enumerate(options, 1):
        print(f"    {i}) {opt}")
    while True:
        val = input(f"  Enter choice (1-{len(options)}): ").strip()
        if val.isdigit() and 1 <= int(val) <= len(options):
            return options[int(val) - 1]
        print(f"    Please enter a number 1-{len(options)}")


def configure():
    print("=" * 50)
    print("  Configuration Wizard")
    print("=" * 50)
    print()

    config = {}

    # --- Platforms ---
    print("[Platforms]")
    print("  Which platforms do you want to post to?")
    use_youtube = ask_yes_no("YouTube Shorts?", default=True)
    use_tiktok = ask_yes_no("TikTok?", default=True)

    if not use_youtube and not use_tiktok:
        print("  You need at least one platform! Defaulting to YouTube.")
        use_youtube = True

    config["platforms"] = {
        "youtube": use_youtube,
        "tiktok": use_tiktok,
    }
    print()

    # --- Instagram credentials ---
    print("[Instagram Account to Repost FROM]")
    ig_username = ask("Instagram username")
    ig_password = ask("Instagram password")
    print()

    # --- TikTok credentials ---
    tk_username = ""
    tk_password = ""
    tk_account_name = ""
    if use_tiktok:
        print("[TikTok Account to Repost TO]")
        tk_account_name = ask("TikTok handle (without @)")
        tk_username = ask("TikTok username/email (for login)")
        tk_password = ask("TikTok password")
        print()

    # --- Posting schedule ---
    print("[Posting Schedule]")
    posts_per_day = ask_int("How many posts per day?", 1, 10, default=5)

    interval_hours = round(24.0 / posts_per_day, 1)
    print(f"  -> That's 1 post every {interval_hours} hours")

    # Cron frequency (how often the script checks for work)
    cron_options = [
        "Every 1 hour",
        "Every 2 hours",
        "Every 3 hours (recommended)",
        "Every 6 hours",
        "Every 12 hours",
    ]
    cron_choice = ask_choice("How often should the automation run?", cron_options)
    cron_hours = {"Every 1 hour": 1, "Every 2 hours": 2, "Every 3 hours (recommended)": 3,
                  "Every 6 hours": 6, "Every 12 hours": 12}[cron_choice]
    print()

    config["posts_per_day"] = posts_per_day
    config["post_interval_hours"] = interval_hours
    config["cron_interval_hours"] = cron_hours
    config["tiktok_account_name"] = tk_account_name

    # --- YouTube API setup ---
    if use_youtube:
        print("[YouTube API Setup]")
        print("  YouTube requires a Google Cloud project with the YouTube Data API v3.")
        print()
        print("  Quick steps:")
        print("    1. Go to https://console.cloud.google.com/")
        print("    2. Create a new project (or select existing)")
        print("    3. Enable 'YouTube Data API v3'")
        print("    4. Go to Credentials -> Create OAuth 2.0 Client ID")
        print("       - Application type: Desktop App")
        print("    5. Download the JSON and save it as 'client_secrets.json'")
        print(f"       in: {BASE_DIR}/")
        print()

        if (BASE_DIR / "client_secrets.json").exists():
            print("  client_secrets.json found!")
        else:
            print("  client_secrets.json NOT found yet.")
            print("  You can add it later before running uploads.")
            print("  Just save it as: client_secrets.json in the project folder.")
        print()

    # --- Write .env ---
    print("Writing configuration files...")

    env_lines = [
        "# Auto-generated by configure.py",
        f"INSTAGRAM_USERNAME={ig_username}",
        f"INSTAGRAM_PASSWORD={ig_password}",
    ]
    if use_tiktok:
        env_lines.extend([
            f"TIKTOK_USERNAME={tk_username}",
            f"TIKTOK_PASSWORD={tk_password}",
            f"TIKTOK_ACCOUNT_NAME={tk_account_name}",
        ])

    with open(ENV_FILE, "w") as f:
        f.write("\n".join(env_lines) + "\n")
    # Lock down permissions (owner read/write only)
    try:
        os.chmod(ENV_FILE, 0o600)
    except OSError:
        pass  # Windows doesn't support Unix permissions
    print(f"  Wrote {ENV_FILE}")
    print("  (Permissions set to owner-only for security)")

    # --- Write user_config.json ---
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    print(f"  Wrote {CONFIG_FILE}")

    print()
    print("  NOTE: Your passwords are stored in plaintext in .env.")
    print("  Keep this file private and never share it or commit it to git.")

    # --- Set up cron ---
    print()
    setup_cron = ask_yes_no("Set up automatic scheduling (cron job)?", default=True)

    if setup_cron:
        script_dir = str(BASE_DIR)
        python_path = f"{script_dir}/venv/bin/python"
        main_script = f"{script_dir}/main.py"
        log_file = f"{script_dir}/cron.log"

        tiktok_flag = " --tiktok" if use_tiktok else ""
        cron_job = f"0 */{cron_hours} * * * cd {script_dir} && {python_path} {main_script} run{tiktok_flag} >> {log_file} 2>&1"

        # Remove old cron job if exists
        try:
            existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            old_cron = existing.stdout if existing.returncode == 0 else ""
            # Filter out old entries
            filtered = "\n".join(
                line for line in old_cron.splitlines()
                if "instagram-tiktok-reposter" not in line and main_script not in line
            )
            new_cron = f"{filtered}\n{cron_job}\n".strip() + "\n"

            proc = subprocess.run(["crontab", "-"], input=new_cron, text=True, capture_output=True)
            if proc.returncode == 0:
                print(f"  Cron job installed! Running every {cron_hours} hour(s).")
                print(f"  Logs: {log_file}")
            else:
                print(f"  Failed to install cron: {proc.stderr}")
                print(f"  You can add this line manually to 'crontab -e':")
                print(f"    {cron_job}")
        except Exception as e:
            print(f"  Could not set up cron: {e}")
            print(f"  Add this line to 'crontab -e':")
            print(f"    {cron_job}")
    print()

    # --- Next steps ---
    print("=" * 50)
    print("  Almost done! Next steps:")
    print("=" * 50)
    print()
    print("  1. Login to your platforms (opens a browser):")
    print("     python main.py init")
    print()
    if use_youtube and not (BASE_DIR / "client_secrets.json").exists():
        print("  2. Add your YouTube API credentials:")
        print("     Save client_secrets.json in the project folder")
        print("     Then run: python youtube_uploader.py")
        print()
    print("  3. Download your Instagram content:")
    print("     python main.py download")
    print()
    print("  4. Start posting (or let cron handle it):")
    tiktok_flag = " --tiktok" if use_tiktok else ""
    print(f"     python main.py run{tiktok_flag}")
    print()
    print("  To reconfigure anytime, run: python configure.py")
    print()


if __name__ == "__main__":
    configure()
