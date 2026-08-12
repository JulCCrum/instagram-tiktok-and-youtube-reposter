#!/bin/bash
# Run this ON THE MAC MINI, from inside the cloned repo, AFTER you've rsynced
# the secrets/state/media over from the old Mac.
#
#   cd ~/Projects/content-system/reposter
#   ./migrate_setup.sh
#
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> 1/6  Checking prerequisites"
command -v python3.12 >/dev/null 2>&1 || { echo "    Python 3.12 not found. Run: brew install python@3.12"; exit 1; }
command -v brew >/dev/null 2>&1 || { echo "    Homebrew not found. Install from https://brew.sh first."; exit 1; }

echo "==> 2/6  Verifying required secret/state files are present"
MISSING=0
for f in .env client_secrets.json youtube_token.pickle progress.json; do
  if [ ! -e "$f" ]; then echo "    MISSING: $f  (rsync it from the old Mac)"; MISSING=1; fi
done
[ -d browser_state ] || { echo "    MISSING: browser_state/  (Instagram login session)"; MISSING=1; }
[ "$MISSING" = "1" ] && { echo "    Aborting — copy the missing files first."; exit 1; }
echo "    All required state files present."

echo "==> 3/6  Building fresh virtualenv (do NOT copy venv from the old Mac)"
rm -rf venv
python3.12 -m venv venv
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "==> 4/6  Installing Playwright browser binaries"
playwright install chromium

echo "==> 5/6  Installing terminal-notifier (for cron failure alerts)"
brew list terminal-notifier >/dev/null 2>&1 || brew install terminal-notifier

echo "==> 6/6  Installing the cron job (every 3 hours)"
./setup_cron.sh

echo ""
echo "Done. Now verify state transferred correctly BEFORE it posts:"
echo "    source venv/bin/activate && python main.py status"
echo "If the uploaded/pending counts look right, you're live."
