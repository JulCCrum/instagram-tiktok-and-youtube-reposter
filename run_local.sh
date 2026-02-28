#!/bin/bash
# Local cron runner for Instagram to TikTok/YouTube reposter
# Auto-detects paths so it works on any machine

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

source venv/bin/activate

# Pass through any args (e.g. --tiktok)
python main.py run "$@" >> "$SCRIPT_DIR/cron.log" 2>&1

echo "--- Run completed at $(date) ---" >> "$SCRIPT_DIR/cron.log"
