# Claude Automation Guide for Instagram-TikTok Reposter

**Read this before running automation commands.**

---

## Built-In Safeguards (Already in Code)

### 1. Scheduled Posting (NOT Immediate)
- `schedule_all.py` schedules posts starting **10 minutes from now**
- Each subsequent post is scheduled **4.8 hours apart** (5 posts/day)
- Videos are NOT posted all at once

### 2. No Duplicate Posts
- `progress.json` tracks all uploaded video shortcodes
- Before scheduling, the script checks if a video is already in the "uploaded" list
- If already uploaded, it's **automatically skipped**

### 3. File Validation
- Script verifies `metadata.json` exists before processing
- Script verifies `.mp4` video file exists before adding to pending queue
- Missing files are **automatically skipped**

---

## Correct Commands

### Check Status First
```bash
cd /Users/chasecrummedyo/instagram-tiktok-reposter
python main.py status
```

### Schedule All Pending Videos
```bash
python schedule_all.py
```
This will:
- Find all videos in "downloaded" that aren't in "uploaded"
- Skip any without valid video files
- Schedule them 4.8 hours apart starting 10 min from now
- Mark each as "uploaded" in progress.json after successful scheduling

### Download New Videos from Instagram
```bash
python main.py download --max 50
```

### Upload Single Video Immediately (Not Scheduled)
```bash
python main.py upload
```

---

## File Locations

| File | Path |
|------|------|
| Main script | `/Users/chasecrummedyo/instagram-tiktok-reposter/main.py` |
| Scheduler | `/Users/chasecrummedyo/instagram-tiktok-reposter/schedule_all.py` |
| Progress tracker | `/Users/chasecrummedyo/instagram-tiktok-reposter/progress.json` |
| Media directory | `/Users/chasecrummedyo/instagram-tiktok-reposter/media/{shortcode}/` |
| Video files | `/Users/chasecrummedyo/instagram-tiktok-reposter/media/{shortcode}/*.mp4` |
| Metadata | `/Users/chasecrummedyo/instagram-tiktok-reposter/media/{shortcode}/metadata.json` |

---

## Workflow for Claude

1. **Always run status first:**
   ```bash
   cd /Users/chasecrummedyo/instagram-tiktok-reposter
   python main.py status
   ```

2. **Report to user:** "Found X videos pending, Y already uploaded"

3. **If user wants to schedule:** Run `python schedule_all.py`

4. **Report results:** Note any errors, confirm how many were scheduled

---

## Schedule Timing

With default settings (4.8 hour intervals):
- Video 1: 10 minutes from now
- Video 2: ~5 hours from now
- Video 3: ~10 hours from now
- Video 4: ~15 hours from now
- Video 5: ~19 hours from now
- (Pattern continues for all pending videos)

---

## If Issues Occur

**"Video not found" errors:** The video was likely never downloaded or was deleted. Re-run `python main.py download`.

**Duplicate posts on platform:** Check if `progress.json` was corrupted or script was interrupted. The shortcode should be in the "uploaded" array.

**Videos posted immediately:** You likely ran `python main.py upload` instead of `python schedule_all.py`. The `upload` command posts immediately; `schedule_all.py` schedules for later.
