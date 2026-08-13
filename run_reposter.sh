#!/bin/bash
#
# Self-healing cron wrapper for the Content System reposter + grader.
#
# WHY THIS EXISTS
# ----------------
# The reposter silently stopped posting for ~6 weeks because two things
# broke with no safety net:
#   1. the venv/ directory was deleted, and
#   2. Playwright's browser binary went missing after a `playwright` upgrade.
# In both cases `venv/bin/python` failed, so the cron "ran" but crashed
# every time and nothing was ever posted again.
#
# This wrapper runs on EVERY cron tick and guarantees the environment is
# healthy before launching the job. If something is missing it repairs
# itself, so a future break cannot silently kill the automation again.
#
# Usage:
#   run_reposter.sh            # repost cycle (default)
#   run_reposter.sh grader     # grader job
#
# Install once with setup_cron.sh. Logs go to selfheal.log so fixes are
# visible + auditable.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---- 0. Make sure tools like ffmpeg/yt-dlp are on PATH ----------------
# Cron runs with a minimal PATH that does NOT include Homebrew's bin dir,
# so `ffmpeg` (installed at /opt/homebrew/bin) was invisible and every
# YouTube conversion silently fell back to the un-converted file. Add the
# common Homebrew + macOS tool dirs (covers Intel + Apple Silicon both).
PATH=/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/local/sbin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH
export PATH

PY=venv/bin/python
SELFHEAL_LOG="$SCRIPT_DIR/selfheal.log"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$SELFHEAL_LOG"; }

# ---- 1. Recreate the venv if it's missing or has no python ----
if [ ! -x "$PY" ]; then
    log "[self-heal] venv missing/broken — recreating"
    # Remove a half-corrupt venv so `python -m venv` starts clean.
    rm -rf venv
    if python3 -m venv venv >> "$SELFHEAL_LOG" 2>&1; then
        log "[self-heal] venv created; installing requirements"
        venv/bin/pip install --quiet --upgrade pip >> "$SELFHEAL_LOG" 2>&1
        venv/bin/pip install --quiet -r requirements.txt >> "$SELFHEAL_LOG" 2>&1
    else
        log "[self-heal] ERROR: could not recreate venv — aborting this run"
        exit 1
    fi
fi

# ---- 2. Ensure Playwright chromium is installed (browser drops on upgrade) ----
# Cheap guard: if the browser dir is missing, run `playwright install`.
if ! venv/bin/python -c "from playwright.sync_api import sync_playwright" >> "$SELFHEAL_LOG" 2>&1; then
    log "[self-heal] playwright package missing — installing"
    venv/bin/pip install --quiet playwright >> "$SELFHEAL_LOG" 2>&1
fi
# Check whether a chromium browser is actually launchable; if not, install it.
if ! venv/bin/python - <<'EOF' >>"$SELFHEAL_LOG" 2>&1
try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        b.close()
except Exception:
    raise SystemExit(1)
EOF
then
    log "[self-heal] Playwright browser missing — running install"
    venv/bin/python -m playwright install chromium >> "$SELFHEAL_LOG" 2>&1 || log "[self-heal] ERROR: playwright install failed"
fi

# ---- 3. Run the requested job ----
JOB="${1:-run}"
if [ "$JOB" = "grader" ]; then
    log "[grader] starting"
    venv/bin/python grader.py >> "$SCRIPT_DIR/grader.log" 2>&1
    log "[grader] finished (exit=$?)"
else
    log "[run] starting repost cycle"
    venv/bin/python main.py run "$@" >> "$SCRIPT_DIR/cron.log" 2>&1
    log "[run] finished repost cycle (exit=$?)"
fi
