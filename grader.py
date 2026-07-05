#!/usr/bin/env python3
"""
The Review part of the Content Engine — grades every post on a timer.

Per the build spec (v4, item 06), each post gets looked at three times:
  30 min — a grade of the post ITSELF (content quality, from the Videom8
           analysis: hook / value delivery / execution). Not performance —
           it's too early for numbers to mean anything.
  24 hr  — an honest read on WHY it performed the way it did, plus what to
           do differently next time. Written by Gemini from the numbers
           (vs your channel baseline) + the Videom8 critique. Stored on the
           post AND emailed to you — the advice should land in your inbox
           while the next video is still unmade.
  7 day  — the real performance grade (deterministic, saves/shares weighted
           over views) + Instagram vs YouTube head-to-head. This is what
           the Iterate part will learn from.

Runs on the Mac mini via its own cron (every 30 min). Idempotent: the
grades on the post document are the done-markers, so re-runs are safe.
Stats snapshots are written to the `stats` collection with the same
deterministic ids the Next.js app uses (post_platform_checkpoint).

Usage:
  python grader.py               # process all due milestones
  python grader.py --dry-run     # show what would happen, write nothing
  python grader.py --post <code> # force-process one shortcode (testing)
"""

import argparse
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

import requests

from content_engine_sync import _client
from notifier import send_email

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except Exception:
    pass

GRAPH = "https://graph.instagram.com"
YT_API = "https://www.googleapis.com/youtube/v3/videos"
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

MIN_30 = 30 * 60 * 1000
HR_24 = 24 * 3600 * 1000
HR_72 = 72 * 3600 * 1000
DAY_7 = 7 * 24 * 3600 * 1000
DAY_30 = 30 * 24 * 3600 * 1000

# Cap LLM reviews + emails per run so a backlog drains gradually instead of
# flooding the inbox (cron runs every 30 min, so a backlog clears in hours).
MAX_REVIEWS_PER_RUN = 3
MAX_FINALS_PER_RUN = 5

# Engagement weighting per the spec: "Saves and shares should count more
# toward the grade than plain views."
def weighted_score(s):
    return (
        (s.get("views") or 0) * 0.01
        + (s.get("likes") or 0) * 1.0
        + (s.get("comments") or 0) * 3.0
        + (s.get("shares") or 0) * 8.0
        + (s.get("saves") or 0) * 10.0
    )


def ratio_to_letter(r):
    """Map performance-vs-baseline ratio to a letter grade."""
    for cut, letter in [(2.0, "A+"), (1.5, "A"), (1.2, "A-"), (1.0, "B+"),
                        (0.85, "B"), (0.7, "B-"), (0.55, "C+"), (0.4, "C"),
                        (0.25, "D")]:
        if r >= cut:
            return letter
    return "F"


# ---------------------------------------------------------------- Instagram

def ig_config(db):
    doc = db.collection("config").document("instagram").get()
    return doc.to_dict() if doc.exists else None


def ig_shortcode(permalink):
    m = re.search(r"/(?:reel|reels|p|tv)/([^/?#]+)", permalink or "")
    return m.group(1) if m else None


def fetch_ig_media(token, limit=50):
    """Recent media (id, shortcode, likes, comments, timestamp)."""
    fields = "id,caption,media_type,permalink,timestamp,like_count,comments_count"
    res = requests.get(
        f"{GRAPH}/me/media",
        params={"fields": fields, "limit": limit, "access_token": token},
        timeout=30,
    )
    res.raise_for_status()
    out = {}
    for m in res.json().get("data", []):
        code = ig_shortcode(m.get("permalink"))
        if code:
            out[code] = m
    return out


def fetch_ig_insights(token, media_id):
    """Lifetime reach/saved/shares/views for one media. Best-effort."""
    out = {"reach": 0, "saves": 0, "shares": 0, "views": 0}
    try:
        res = requests.get(
            f"{GRAPH}/{media_id}/insights",
            params={"metric": "reach,saved,shares,views", "access_token": token},
            timeout=30,
        )
        if res.ok:
            for row in res.json().get("data", []):
                v = (row.get("values") or [{}])[0].get("value") or 0
                name = row.get("name")
                if name == "saved":
                    out["saves"] = v
                elif name in out:
                    out[name] = v
    except Exception as e:  # noqa: BLE001
        print(f"  (ig insights failed for {media_id}: {e})")
    return out


def ig_stats_for(token, media):
    ins = fetch_ig_insights(token, media["id"])
    return {
        "views": ins["views"],
        "likes": media.get("like_count") or 0,
        "comments": media.get("comments_count") or 0,
        "shares": ins["shares"],
        "saves": ins["saves"],
    }


# ----------------------------------------------------------------- YouTube

def yt_video_id(url):
    m = re.search(r"(?:shorts/|watch\?v=|youtu\.be/|/v/|embed/)([A-Za-z0-9_-]{11})", url or "")
    if m:
        return m.group(1)
    u = (url or "").strip()
    return u if re.fullmatch(r"[A-Za-z0-9_-]{11}", u) else None


def fetch_yt_stats(video_ids):
    """Batch stats for up to 50 ids -> {id: {views, likes, comments}}."""
    key = os.environ.get("YOUTUBE_API_KEY")
    out = {}
    if not key or not video_ids:
        if not key:
            print("  (YOUTUBE_API_KEY not set — skipping YouTube stats)")
        return out
    ids = [i for i in dict.fromkeys(video_ids) if i]
    for i in range(0, len(ids), 50):
        chunk = ids[i : i + 50]
        res = requests.get(
            YT_API,
            params={"part": "statistics", "id": ",".join(chunk), "key": key},
            timeout=30,
        )
        res.raise_for_status()
        for item in res.json().get("items", []):
            s = item.get("statistics", {})
            out[item["id"]] = {
                "views": int(s.get("viewCount", 0)),
                "likes": int(s.get("likeCount", 0)),
                "comments": int(s.get("commentCount", 0)),
                "shares": 0,
                "saves": 0,
            }
    return out


# ------------------------------------------------------------------ Gemini

def gemini_json(prompt):
    """One Gemini call, JSON response. Returns dict or None."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("  (GEMINI_API_KEY not set — skipping LLM review)")
        return None
    try:
        res = requests.post(
            GEMINI_URL,
            params={"key": key},
            json={
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
            timeout=90,
        )
        res.raise_for_status()
        text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except Exception as e:  # noqa: BLE001
        print(f"  (gemini call failed: {e})")
        return None


# ---------------------------------------------------------------- Grading

def videom8_grade(analysis):
    """30-min grade of the post itself, straight from the Videom8 analysis."""
    grades = analysis.get("grades") or {}
    hook = grades.get("hook")
    value = grades.get("value_delivery")
    execution = grades.get("execution")
    score = None
    if all(isinstance(x, int) for x in (hook, value, execution)):
        score = round((hook + value + execution) / 30 * 100)
    return {
        "letter": analysis.get("letter_grade") or "—",
        **({"score": score} if score is not None else {}),
        "reason": analysis.get("verdict_headline")
        or analysis.get("critique_lede")
        or "Videom8 content analysis",
    }


def summarize_videom8(analysis):
    """Compact text summary of the Videom8 critique for the LLM prompt."""
    if not analysis:
        return "(no Videom8 analysis available)"
    parts = []
    for k in ("video_style", "topic", "letter_grade", "verdict_headline", "critique_lede"):
        if analysis.get(k):
            parts.append(f"{k}: {analysis[k]}")
    grades = analysis.get("grades") or {}
    if grades:
        parts.append("scores (0-10): " + ", ".join(f"{k}={v}" for k, v in grades.items()))
    for k in ("takeaways", "actionable_improvements"):
        items = analysis.get(k) or []
        if items:
            lines = []
            for it in items[:5]:
                lines.append(it if isinstance(it, str) else json.dumps(it)[:200])
            parts.append(f"{k}:\n  - " + "\n  - ".join(lines))
    return "\n".join(parts)


def fmt_stats(s):
    if not s:
        return "no data"
    return (f"views {s.get('views', 0):,} · likes {s.get('likes', 0):,} · "
            f"comments {s.get('comments', 0):,} · shares {s.get('shares', 0):,} · "
            f"saves {s.get('saves', 0):,}")


def review_24h(post, ig, yt, ig_base, yt_base, analysis):
    """Gemini writes the honest 24h read. Returns (text, letter) or None."""
    hook = post.get("hook_screen") or post.get("yt_title") or post.get("id", "")
    prompt = f"""You are the Review part of a solo creator's content engine. 24 hours ago he posted a short-form video. Write him an honest, specific read on why it performed the way it did and what to do differently on the NEXT video. He is the only reader; talk to him directly, no fluff, no cheerleading. Ground every claim in the numbers or the critique below — do not invent facts.

THE POST
Hook / topic: {hook}
Instagram at ~24h: {fmt_stats(ig)}
YouTube at ~24h: {fmt_stats(yt)}

CHANNEL BASELINE (median LIFETIME numbers of his recent posts — a 24h-old post is normally still below these):
Instagram baseline: {fmt_stats(ig_base)}
YouTube baseline: {fmt_stats(yt_base)}

VIDEOM8 CONTENT CRITIQUE (automated analysis of the video itself):
{summarize_videom8(analysis)}

Return JSON exactly like:
{{"letter": "B+", "why": "2-4 sentences on why it performed this way, tying numbers to content choices", "advice": ["concrete change #1 for the next video", "concrete change #2", "optional #3"]}}"""
    out = gemini_json(prompt)
    if not out or not out.get("why"):
        return None
    letter = out.get("letter") or "?"
    advice = out.get("advice") or []
    text = f"[{letter}] {out['why']}"
    if advice:
        text += "\nDo differently:\n" + "\n".join(f"- {a}" for a in advice)
    return text, letter, out


def final_grade(ig, yt, ig_base, yt_base):
    """Deterministic 7-day grade + platform head-to-head."""
    score = weighted_score(ig or {}) + weighted_score(yt or {})
    base = weighted_score(ig_base or {}) + weighted_score(yt_base or {})
    r = score / base if base > 0 else 1.0
    letter = ratio_to_letter(r)
    grade = {
        "letter": letter,
        "score": min(100, round(r * 50)),  # 1.0x baseline -> 50, 2.0x -> 100
        "reason": f"{r:.2f}x your channel baseline (saves/shares weighted)",
    }
    ig_v, yt_v = (ig or {}).get("views") or 0, (yt or {}).get("views") or 0
    if ig_v == 0 and yt_v == 0:
        vs = {"winner": "tie", "note": "no views recorded on either platform"}
    elif ig_v >= yt_v:
        mult = f"{ig_v / yt_v:.1f}x" if yt_v else "∞"
        vs = {"winner": "instagram", "note": f"IG {ig_v:,} vs YT {yt_v:,} views ({mult})"}
    else:
        mult = f"{yt_v / ig_v:.1f}x" if ig_v else "∞"
        vs = {"winner": "youtube", "note": f"YT {yt_v:,} vs IG {ig_v:,} views ({mult})"}
    return grade, vs


def median_stats(stats_list):
    """Field-wise median across a list of stats dicts."""
    if not stats_list:
        return None
    out = {}
    for k in ("views", "likes", "comments", "shares", "saves"):
        vals = [s.get(k) or 0 for s in stats_list]
        out[k] = int(statistics.median(vals)) if vals else 0
    return out


# ------------------------------------------------------------------- Main

def run(dry_run=False, only_post=None):
    db = _client()
    if db is None:
        print("no Firestore client — aborting")
        return 1
    now = int(time.time() * 1000)

    posts = []
    for doc in db.collection("posts").where("status", "==", "posted").stream():
        p = doc.to_dict()
        p["id"] = doc.id
        posts.append(p)

    due = []
    for p in posts:
        if only_post and p["id"] != only_post:
            continue
        created = p.get("created_at") or 0
        age = now - created
        if age > DAY_30 and not only_post:
            continue  # too old to grade retroactively
        jobs = []
        if age >= MIN_30 and not p.get("grade_30min"):
            jobs.append("30min")
        # The 24h read is only useful near the 24h mark; past 72h the 7-day
        # final covers it (also keeps the first backlog run from flooding email).
        if HR_24 <= age < HR_72 and not p.get("review_24h"):
            jobs.append("24hr")
        if age >= DAY_7 and not p.get("grade_final"):
            jobs.append("7day")
        if only_post and not jobs:
            jobs = ["30min", "24hr", "7day"]  # force everything when testing
        if jobs:
            due.append((p, jobs))

    if not due:
        print("nothing due")
        return 0
    print(f"{len(due)} post(s) with due milestones")

    # --- fetch stats once per run
    cfg = ig_config(db)
    token = (cfg or {}).get("access_token")
    ig_media = {}
    if token:
        try:
            ig_media = fetch_ig_media(token)
        except Exception as e:  # noqa: BLE001
            print(f"  (ig media fetch failed: {e})")

    # IG baseline: insights on recent media (skip the ones due anyway — they
    # get fetched below and merged in).
    ig_stats_cache = {}
    for code, m in list(ig_media.items())[:25]:
        ig_stats_cache[code] = ig_stats_for(token, m) if token else None
    ig_baseline = median_stats([s for s in ig_stats_cache.values() if s])

    # YT: batch every video id in the collection -> stats + baseline
    all_yt_ids = {p["id"]: yt_video_id(p.get("yt_url")) for p in posts}
    yt_stats_by_id = fetch_yt_stats(list(all_yt_ids.values()))
    yt_baseline = median_stats(list(yt_stats_by_id.values()))

    reviews_sent = finals_sent = 0
    for p, jobs in due:
        code = p["id"]
        print(f"\n{code}: {', '.join(jobs)}")
        ig = ig_stats_cache.get(code)
        if ig is None and code in ig_media and token:
            ig = ig_stats_for(token, ig_media[code])
        yt = yt_stats_by_id.get(all_yt_ids.get(code))
        analysis = p.get("videom8_analysis") or p.get("videom8")
        patch = {}

        for when in jobs:
            # snapshot the numbers at this checkpoint (same doc ids as the app)
            for platform, s in (("instagram", ig), ("youtube", yt)):
                if s and not dry_run:
                    db.collection("stats").document(f"{code}_{platform}_{when}").set(
                        {"post_id": code, "platform": platform, "when": when,
                         **s, "captured_at": now},
                        merge=True,
                    )

            if when == "30min":
                if analysis:
                    patch["grade_30min"] = videom8_grade(analysis)
                elif (now - (p.get("created_at") or 0)) > 3 * 3600 * 1000:
                    patch["grade_30min"] = {
                        "letter": "—",
                        "reason": "no Videom8 analysis available for this post",
                    }
                # else: analysis may still be coming — retry next run
                print(f"  30min -> {patch.get('grade_30min', {}).get('letter', '(waiting on Videom8)')}")

            elif when == "24hr":
                if reviews_sent >= MAX_REVIEWS_PER_RUN:
                    print("  24hr -> deferred (review cap this run)")
                    continue
                if dry_run:
                    print("  24hr -> would run Gemini review + email")
                    continue
                result = review_24h(p, ig, yt, ig_baseline, yt_baseline, analysis)
                if not result:
                    print("  24hr -> review failed, will retry next run")
                    continue
                text, letter, out = result
                patch["review_24h"] = text
                hook = (p.get("hook_screen") or code)[:60]
                body = (
                    f"{hook}\n\n"
                    f"Instagram (24h): {fmt_stats(ig)}\n"
                    f"YouTube  (24h): {fmt_stats(yt)}\n\n"
                    f"Why it performed this way:\n{out.get('why', '')}\n\n"
                    "Do differently on the next video:\n"
                    + "\n".join(f"- {a}" for a in out.get("advice", []))
                    + f"\n\nIG: {p.get('ig_url', '—')}\nYT: {p.get('yt_url', '—')}"
                )
                send_email(f"24h review [{letter}]: {hook}", body)
                reviews_sent += 1
                print(f"  24hr -> [{letter}] review stored + emailed")

            elif when == "7day":
                if finals_sent >= MAX_FINALS_PER_RUN:
                    print("  7day -> deferred (finals cap this run)")
                    continue
                grade, vs = final_grade(ig, yt, ig_baseline, yt_baseline)
                if dry_run:
                    print(f"  7day -> would grade {grade['letter']} ({vs['note']})")
                    continue
                patch["grade_final"] = grade
                patch["vs_platform"] = vs
                patch["status"] = "graded"
                hook = (p.get("hook_screen") or code)[:60]
                send_email(
                    f"7-day grade [{grade['letter']}]: {hook}",
                    f"{hook}\n\nFinal grade: {grade['letter']} — {grade['reason']}\n"
                    f"Head-to-head: {vs['winner']} won — {vs['note']}\n\n"
                    f"Instagram (7d): {fmt_stats(ig)}\nYouTube  (7d): {fmt_stats(yt)}",
                )
                finals_sent += 1
                print(f"  7day -> {grade['letter']} · {vs['winner']} won")

        if patch and not dry_run:
            patch["updated_at"] = now
            db.collection("posts").document(code).set(patch, merge=True)

    print(f"\ndone — {reviews_sent} review(s), {finals_sent} final(s)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--post", help="force-process one shortcode")
    args = ap.parse_args()
    sys.exit(run(dry_run=args.dry_run, only_post=args.post))
