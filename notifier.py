"""
Failure notifications via native macOS desktop notification.

When an upload fails, pop a macOS notification with the platform, post, and a
short reason. No credentials, no accounts, no network — just a local alert.

De-duplicates: a post that keeps failing with the same error only notifies ONCE
per distinct (platform, shortcode, error) signature, so a stuck queue can't
spam you. State lives in notify_state.json (git-ignored).

Everything here is best-effort — a notification problem must never break an
upload run, so every path is wrapped and falls back to a printed message.

NOTE: macOS only delivers notifications inside your logged-in GUI session.
Fired from a plain cron job they can be unreliable. If they don't show up,
install terminal-notifier (`brew install terminal-notifier`) — this module
uses it automatically when present — or run the job via launchd instead of cron.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

# Tracks which failure signatures we've already alerted on, so repeats of the
# same stuck post don't re-notify.
STATE_FILE = Path(__file__).parent / "notify_state.json"


def _load_seen():
    try:
        return set(json.loads(STATE_FILE.read_text()))
    except Exception:
        return set()


def _save_seen(seen):
    try:
        STATE_FILE.write_text(json.dumps(sorted(seen), indent=2))
    except Exception as e:
        print(f"  (notifier: could not save state: {e})")


def _signature(platform, shortcode, error):
    """A stable key for a failure.

    Uses only the first line of the error so volatile trailing details
    (request ids, timestamps) don't make every occurrence look 'new'.
    """
    first = (error or "").strip().splitlines()
    err_key = first[0][:160] if first else "unknown"
    return f"{platform}|{shortcode}|{err_key}"


def _send_macos_notification(title, subtitle, message):
    """Show a macOS notification. Returns True on apparent success."""
    # terminal-notifier is far more reliable from cron/launchd than osascript.
    tn = shutil.which("terminal-notifier")
    if tn:
        try:
            subprocess.run(
                [tn, "-title", title, "-subtitle", subtitle, "-message", message,
                 "-sound", "default"],
                check=True, capture_output=True, timeout=10,
            )
            return True
        except Exception as e:
            print(f"  (notifier: terminal-notifier failed: {e})")

    # Fallback: AppleScript via osascript (may not surface from cron).
    def esc(s):
        return s.replace("\\", "\\\\").replace('"', '\\"')

    script = (
        f'display notification "{esc(message)}" '
        f'with title "{esc(title)}" subtitle "{esc(subtitle)}" '
        f'sound name "default"'
    )
    try:
        subprocess.run(["osascript", "-e", script],
                       check=True, capture_output=True, timeout=10)
        return True
    except Exception as e:
        print(f"  (notifier: osascript failed: {e})")
        return False


def notify_failure(platform, shortcode, error, hint=""):
    """Alert about a failed upload, once per distinct failure signature."""
    if not sys.platform.startswith("darwin"):
        # Desktop notifications are macOS-only here; skip elsewhere.
        return

    sig = _signature(platform, shortcode, error)
    seen = _load_seen()
    if sig in seen:
        print("  (notifier: already alerted on this failure — not re-notifying)")
        return

    first_err = (error or "").strip().splitlines()
    short_err = first_err[0] if first_err else "Unknown error"
    message = hint or short_err

    ok = _send_macos_notification(
        title="Reposter: upload failed",
        subtitle=f"{platform} — {shortcode}",
        message=message,
    )
    if ok:
        print(f"  (notifier: desktop alert shown for {shortcode})")
        seen.add(sig)
        _save_seen(seen)


def send_failure_email(subject, body):
    """Email a failure alert via SMTP. Best-effort; needs SMTP_* env vars.

    Configure in .env:
      SMTP_HOST (default smtp.gmail.com), SMTP_PORT (default 587),
      SMTP_USER, SMTP_PASS (an app password for Gmail/Workspace),
      ALERT_EMAIL_TO (default = SMTP_USER), ALERT_EMAIL_FROM (default = SMTP_USER)

    De-dupes on subject so a stuck post emails only once.
    """
    import os

    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")
    to_addr = os.environ.get("ALERT_EMAIL_TO", user)
    from_addr = os.environ.get("ALERT_EMAIL_FROM", user)

    if not (user and password and to_addr):
        print("  (email: SMTP_USER/SMTP_PASS/ALERT_EMAIL_TO not set — skipping email alert)")
        return False

    sig = "email|" + subject
    seen = _load_seen()
    if sig in seen:
        print("  (email: already emailed this alert — skipping)")
        return False

    import smtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(body)

    try:
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls()
            s.login(user, password)
            s.send_message(msg)
        print(f"  (email: failure alert sent to {to_addr})")
        seen.add(sig)
        _save_seen(seen)
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  (email: send failed: {e})")
        return False
