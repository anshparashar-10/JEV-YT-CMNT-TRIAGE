"""
Fetching, classification and scoring. No UI framework in here on purpose:
this is the part that would survive swapping Streamlit for anything else.
"""

import asyncio
import os
import re
import time

import httpx
import pandas as pd

try:                                   # local dev convenience; absent on Streamlit Cloud
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from questions import (
    DIFFICULTY_LABELS,
    QUESTIONS,
    SENTIMENT_LABELS,
    label_from_score,
)

JEV_URL = "https://api.typesafe.ai/v1/systemone"
YT_URL = "https://www.googleapis.com/youtube/v3/commentThreads"

MAX_COMMENTS = 200      # hard cost ceiling per run. 200 comments ~= one rupee.
CONCURRENCY = 20        # well under the documented 80 rps.
RUNS_PER_DAY = 150      # whole-app ceiling: worst case ~Rs 150/day of Jev spend

USD_PER_1M_TOKENS = 0.042
INR_PER_USD = 96.58     # 2026-10-06. Goes stale; token counts stay correct.
INR_PER_1M_TOKENS = USD_PER_1M_TOKENS * INR_PER_USD

# Buckets for the priority filter. Placeholders - tune on a labelled sample.
ANSWER_AT = 0.50
MAYBE_AT = 0.25

COLUMNS = ["reply_worthy", "type", "sentiment", "difficulty", "comment", "likes", "sure?"]


class Fail(Exception):
    """Anything the user should see as a message rather than a stack trace."""


def keys() -> tuple[str, str]:
    """st.secrets on Streamlit Cloud, .env locally. Read lazily so imports stay cheap."""
    ts = os.getenv("TYPESAFE_API_KEY")
    yt = os.getenv("YOUTUBE_API_KEY")
    if not (ts and yt):
        try:
            import streamlit as st
            ts = ts or st.secrets.get("TYPESAFE_API_KEY")
            yt = yt or st.secrets.get("YOUTUBE_API_KEY")
        except Exception:
            pass
    if not (ts and yt):
        raise Fail("API keys are not configured. Set TYPESAFE_API_KEY and YOUTUBE_API_KEY.")
    return ts, yt


# ------------------------------------------------------------------- daily limit
# Module-level, so it is shared by every browser session hitting this process.
# ponytail: resets on restart and is per-process. The provider-side spend cap is
# the only limit that genuinely cannot be bypassed.

_day = [time.strftime("%Y-%m-%d"), 0]


def check_daily_limit() -> None:
    today = time.strftime("%Y-%m-%d")
    if _day[0] != today:
        _day[0], _day[1] = today, 0
    if _day[1] >= RUNS_PER_DAY:
        raise Fail("This demo has hit its daily limit. Try again tomorrow.")
    _day[1] += 1


def runs_today() -> int:
    return _day[1]


# --------------------------------------------------------------------------- data


def video_id(url: str) -> str | None:
    """Pull the 11-char video ID out of any of the YouTube URL shapes."""
    for p in (r"(?:v=|/shorts/|/live/|/embed/|youtu\.be/)([A-Za-z0-9_-]{11})",
              r"^([A-Za-z0-9_-]{11})$"):
        if m := re.search(p, url.strip()):
            return m.group(1)
    return None


async def fetch_comments(client: httpx.AsyncClient, vid: str, yt_key: str) -> list[dict]:
    out, token = [], None
    while len(out) < MAX_COMMENTS:
        params = {
            "part": "snippet",
            "videoId": vid,
            "maxResults": min(100, MAX_COMMENTS - len(out)),
            # "relevance" re-ranks between calls, so the same URL would return a
            # different sample and different counts each run. "time" is stable.
            "order": "time",
            "textFormat": "plainText",
            "key": yt_key,
        }
        if token:
            params["pageToken"] = token

        r = await client.get(YT_URL, params=params, timeout=30.0)
        if r.status_code != 200:
            reason = r.json().get("error", {}).get("errors", [{}])[0].get("reason", "")
            raise Fail({
                "commentsDisabled": "Comments are disabled on that video.",
                "videoNotFound": "No such video - check the URL.",
                "quotaExceeded": "YouTube daily quota exhausted. Resets at midnight Pacific.",
            }.get(reason, f"YouTube API error ({r.status_code}): {reason or 'unknown'}"))

        data = r.json()
        for item in data.get("items", []):
            s = item["snippet"]["topLevelComment"]["snippet"]
            out.append({"id": item["id"], "text": s["textDisplay"], "likes": s["likeCount"]})

        token = data.get("nextPageToken")
        if not token:
            break

    seen, unique = set(), []           # paging can repeat an item across pages
    for c in out:
        if c["id"] not in seen:
            seen.add(c["id"])
            unique.append(c)
    return unique[:MAX_COMMENTS]


async def classify(client, sem, text: str, ts_key: str) -> dict | None:
    payload = {"model": "jev-1.13.0", "state": {"comment": text}, "questions": QUESTIONS}
    headers = {"Authorization": f"Bearer {ts_key}"}
    async with sem:
        for attempt in range(3):
            try:
                r = await client.post(JEV_URL, json=payload, headers=headers, timeout=30.0)
            except httpx.RequestError:
                await asyncio.sleep(2**attempt)
                continue
            if r.status_code in (429, 529):        # documented: back off and retry
                await asyncio.sleep(2**attempt)
                continue
            return r.json() if r.status_code == 200 else None
    return None


def to_row(comment: dict, result: dict) -> dict:
    a = result["answers"]

    # Noul answers have no confidence field - the noul value IS the probability.
    direct = a["rw_direct_question"]["noul"]
    merits = a["rw_merits_response"]["noul"]
    hostile = a["rw_is_hostile_or_spam"]["noul"]

    return {
        "reply_worthy": round(max(direct, merits) * (1 - hostile), 2),
        "type": a["comment_type"]["choice"],
        "sentiment": label_from_score(a["sentiment"]["score"], SENTIMENT_LABELS),
        # difficulty is only meaningful if the comment actually reads as a question
        "difficulty": (label_from_score(a["q_difficulty"]["score"], DIFFICULTY_LABELS)
                       if direct >= 0.5 else "—"),
        "comment": " ".join(comment["text"].split()),
        "likes": comment["likes"],
        "sure?": round(a["comment_type"]["confidence"], 2),
    }


async def _run(vid: str, on_progress) -> tuple[pd.DataFrame, int, int]:
    ts_key, yt_key = keys()

    async with httpx.AsyncClient(http2=True) as client:
        on_progress(0.05, "Fetching comments…")
        comments = await fetch_comments(client, vid, yt_key)
        if not comments:
            raise Fail("That video has no comments.")

        total = len(comments)
        on_progress(0.25, f"Classifying {total} comments…")
        sem = asyncio.Semaphore(CONCURRENCY)

        # gather() reports nothing until everything finishes, so count completions
        # ourselves. Writing into a pre-sized list keeps results aligned to comments.
        results: list[dict | None] = [None] * total
        done = 0

        async def one(i: int, text: str):
            nonlocal done
            results[i] = await classify(client, sem, text, ts_key)
            done += 1
            on_progress(0.25 + 0.75 * done / total, f"Classified {done} of {total}…")

        await asyncio.gather(*(one(i, c["text"]) for i, c in enumerate(comments)))

    rows = [to_row(c, r) for c, r in zip(comments, results) if r]
    if not rows:
        raise Fail("Every classification call failed — check the TypeSafe key and credit.")

    df = pd.DataFrame(rows).sort_values("reply_worthy", ascending=False).reset_index(drop=True)
    tokens = sum(r["usage"]["input_tokens"] for r in results if r)
    return df, tokens, len(results) - len(rows)


def analyse(url: str, on_progress=lambda *_: None) -> dict:
    """Validate, charge the daily quota, then fetch + classify. Blocking by design."""
    if not url or not url.strip():
        raise Fail("Paste a YouTube URL first.")
    vid = video_id(url)
    if not vid:
        raise Fail("That doesn't look like a YouTube video URL.")

    # charge the quota only once the URL is valid, so typos don't burn an allowance
    check_daily_limit()

    df, tokens, failed = asyncio.run(_run(vid, on_progress))
    return {
        "df": df,
        "tokens": tokens,
        "failed": failed,
        "cost": tokens / 1_000_000 * INR_PER_1M_TOKENS,
    }


def apply_filters(df: pd.DataFrame, types: list[str], bucket: str) -> pd.DataFrame:
    if df is None or not len(df):
        return pd.DataFrame(columns=COLUMNS)
    out = df[df["type"].isin(types)] if types else df
    if bucket == "Answer these":
        out = out[out["reply_worthy"] >= ANSWER_AT]
    elif bucket == "Maybe":
        out = out[(out["reply_worthy"] >= MAYBE_AT) & (out["reply_worthy"] < ANSWER_AT)]
    elif bucket == "Ignore":
        out = out[out["reply_worthy"] < MAYBE_AT]
    return out
