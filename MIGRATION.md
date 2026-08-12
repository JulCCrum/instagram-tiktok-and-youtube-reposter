# Mac Mini Migration — Instagram/TikTok/YouTube Reposter

This SSD folder (`instagram-tiktok-reposter-archive/`) is a complete, self-contained
transfer kit. Everything the bot needs that is NOT on GitHub is here:

- `media/`           — all 266 already-posted videos (byte-verified)
- `browser_state/`   — Instagram/TikTok/YouTube login sessions (cache stripped)
- `.env`             — Instagram + TikTok credentials
- `client_secrets.json`, `youtube_token.pickle` — Google/YouTube auth
- `progress.json`    — record of what's already posted (prevents duplicate posts)
- `notify_state.json`, `tiktok_cookies.json`, `TK_cookies_*.json`

The code itself lives on GitHub: https://github.com/JulCCrum/instagram-tiktok-and-youtube-reposter

---

## Steps — run these ON THE MAC MINI

```bash
# 1. Prereqs (skip any already installed)
brew install python@3.12 terminal-notifier

# 2. Get the code
cd ~/Projects/content-system
git clone https://github.com/JulCCrum/instagram-tiktok-and-youtube-reposter.git reposter

# 3. Plug in this SSD, then copy the kit INTO the repo
rsync -rth --modify-window=1 \
  "/Volumes/Extreme SSD/instagram-tiktok-reposter-archive/" \
  ~/Projects/content-system/reposter/

# 4. Re-tighten the secret file permission (exFAT dropped it)
chmod 600 ~/Projects/content-system/reposter/.env

# 5. Build venv, deps, Playwright, cron — all automated
cd ~/Projects/content-system/reposter
./migrate_setup.sh

# 6. Verify state BEFORE it posts
source venv/bin/activate && python main.py status
```

If `status` shows **266 uploaded**, the migration succeeded and the bot is live.

---

## LAST STEP — back on the OLD Mac, only after the mini is confirmed working

Kill the old cron so both machines don't double-post:

```bash
crontab -l | grep -v 'instagram-tiktok-reposter' | crontab -
```

---

## Notes / gotchas

- Harmless `._`-prefixed files (e.g. `._client_secrets.json`) on this SSD are macOS
  AppleDouble metadata from copying to exFAT. The mini ignores them.
- This `MIGRATION.md` and the `migrate_setup.sh` referenced in step 5 will both be
  present after step 3 copies the kit in (migrate_setup.sh also comes from the git clone).
- If Instagram/TikTok/YouTube logins fail on the mini (new IP/device), just log in
  once on the mini to regenerate the session — the rest of the setup is unaffected.
- `media/` is optional for the bot to function (everything is already posted), but
  it's included here as your archive.
