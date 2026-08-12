#!/bin/bash
# Setup cron job for Instagram to TikTok reposter

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WRAPPER="$SCRIPT_DIR/run_reposter.sh"
LOG_FILE="$SCRIPT_DIR/cron.log"

# Create the cron job entries (via the self-healing wrapper, which repairs the
# venv + Playwright browser automatically if they break).
GRADER_JOB="*/30 * * * * cd $SCRIPT_DIR && $WRAPPER grader >> $LOG_FILE 2>&1"
CRON_JOB="0 */3 * * * cd $SCRIPT_DIR && $WRAPPER >> $LOG_FILE 2>&1"

# Idempotent: drop old/bare-python versions of both jobs before re-adding.
crontab -l 2>/dev/null | grep -v "run_reposter.sh" | grep -v "main.py run" | grep -v "grader.py" | crontab -

# Add new cron jobs (both go through the self-healing wrapper)
(crontab -l 2>/dev/null; echo "$CRON_JOB"; echo "$GRADER_JOB") | crontab -

echo "Cron job installed successfully!"
echo ""
echo "The reposter runs every 3 hours at minute 0."
echo "Schedule: 12:00 AM, 3:00 AM, 6:00 AM, 9:00 AM, 12:00 PM, 3:00 PM, 6:00 PM, 9:00 PM"
echo "The grader runs every 30 minutes."
echo ""
echo "Logs will be written to: $LOG_FILE (and grader.log)"
echo ""
echo "To verify, run: crontab -l"
echo "To remove, run: crontab -l | grep -v 'run_reposter.sh' | crontab -"
