#!/bin/bash
# Setup cron job for Instagram to TikTok reposter

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_PATH="$SCRIPT_DIR/venv/bin/python"
MAIN_SCRIPT="$SCRIPT_DIR/main.py"
LOG_FILE="$SCRIPT_DIR/cron.log"

# Create the cron job entry
CRON_JOB="0 */3 * * * cd $SCRIPT_DIR && $PYTHON_PATH $MAIN_SCRIPT run >> $LOG_FILE 2>&1"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "instagram-tiktok-reposter"; then
    echo "Cron job already exists. Removing old one..."
    crontab -l | grep -v "instagram-tiktok-reposter" | crontab -
fi

# Add new cron job
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

echo "Cron job installed successfully!"
echo ""
echo "The script will run every 3 hours at minute 0."
echo "Schedule: 12:00 AM, 3:00 AM, 6:00 AM, 9:00 AM, 12:00 PM, 3:00 PM, 6:00 PM, 9:00 PM"
echo ""
echo "Logs will be written to: $LOG_FILE"
echo ""
echo "To verify, run: crontab -l"
echo "To remove, run: crontab -l | grep -v 'instagram-tiktok-reposter' | crontab -"
