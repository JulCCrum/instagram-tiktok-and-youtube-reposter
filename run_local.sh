#!/bin/bash
# Local cron runner for Instagram to TikTok reposter
# This script is designed to run from cron on your Mac

cd /Users/chasecrummedyo/instagram-tiktok-reposter

# Activate virtual environment
source venv/bin/activate

# Run the reposter (uploads to both YouTube and TikTok)
python main.py run --tiktok >> /Users/chasecrummedyo/instagram-tiktok-reposter/cron.log 2>&1

# Add timestamp
echo "--- Run completed at $(date) ---" >> /Users/chasecrummedyo/instagram-tiktok-reposter/cron.log
