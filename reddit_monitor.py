"""
reddit_monitor.py
===================================================================
Pittasoft CS Team - Reddit Community Monitor (read-only)

Purpose:
  Daily read-only retrieval of new posts/comments from r/blackvue and
  r/dashcams (filtered by brand/model keywords) for internal customer
  support monitoring. This tool does NOT post, comment, vote, message,
  or otherwise interact with Reddit users or content.

Scope (per Reddit Data API application):
  - Subreddits: r/blackvue (all posts), r/dashcams (keyword-filtered)
  - Frequency: once per day
  - Output: internal report file only (no external distribution)

Auth:
  Requires a Reddit "script" app (client_id + client_secret) registered
  under a dedicated company account. Credentials are read from
  environment variables — never hardcode them in this file.

  Required env vars:
    REDDIT_CLIENT_ID
    REDDIT_CLIENT_SECRET
    REDDIT_USERNAME
    REDDIT_PASSWORD
    REDDIT_USER_AGENT   (e.g. "pittasoft-cs-monitor/1.0 by u/<username>")

> Run: python reddit_monitor.py
> Requires: pip install praw
"""

import os
import re
import json
from datetime import datetime, timezone, timedelta

try:
    import praw
except ImportError:
    raise SystemExit(
        "Missing dependency. Install with:\n    pip install praw"
    )

# ════════════════════════════════════════════════════════════════
# 설정
# ════════════════════════════════════════════════════════════════

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# 모니터링 대상 서브레딧
TARGET_SUBREDDIT_PRIMARY = "blackvue"     # 전용 서브레딧 — 전체 신규 게시물 수집
TARGET_SUBREDDIT_SECONDARY = "dashcams"   # 범용 서브레딧 — 키워드 필터링 후 수집

# r/dashcams 필터링용 키워드 (대소문자 무관)
BRAND_KEYWORDS = [
    "blackvue",
    "dr970x", "dr900x", "dr900s", "dr750s", "dr750x", "dr590x",
    "elite 10", "elite 9", "elite 8", "elite10", "elite9", "elite8",
    "b-130a", "b-124x", "power magic",
]

# 신규 게시물 판단 기준 — 최근 N시간 이내 (Cowork 매일 1회 실행 가정)
LOOKBACK_HOURS = 24

# 한 번에 가져올 최대 게시물 수 (subreddit.new 호출 시 limit)
FETCH_LIMIT = 100


def get_reddit_client():
    """환경변수에서 인증 정보를 읽어 PRAW Reddit 인스턴스 생성.
    읽기 전용(read_only) 모드로 설정 — 쓰기 작업 일절 수행하지 않음."""
    required = [
        "REDDIT_CLIENT_ID",
        "REDDIT_CLIENT_SECRET",
        "REDDIT_USERNAME",
        "REDDIT_PASSWORD",
        "REDDIT_USER_AGENT",
    ]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise SystemExit(
            f"Missing required environment variables: {', '.join(missing)}\n"
            "Set these before running (see README.md for setup instructions)."
        )

    reddit = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        username=os.environ["REDDIT_USERNAME"],
        password=os.environ["REDDIT_PASSWORD"],
        user_agent=os.environ["REDDIT_USER_AGENT"],
    )
    reddit.read_only = True  # 안전장치: 쓰기 작업 시도 시 예외 발생
    return reddit


def matches_keywords(text, keywords):
    """텍스트에 키워드 중 하나라도 포함되는지 대소문자 무관 검사."""
    if not text:
        return False
    lowered = text.lower()
    return any(kw.lower() in lowered for kw in keywords)


def fetch_new_posts(reddit, subreddit_name, since_dt, keyword_filter=None, limit=FETCH_LIMIT):
    """지정 서브레딧의 신규 게시물 중 since_dt 이후 작성된 것만 수집.
    keyword_filter가 주어지면 제목+본문에 키워드가 있는 것만 포함."""
    results = []
    subreddit = reddit.subreddit(subreddit_name)

    for submission in subreddit.new(limit=limit):
        created = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)
        if created < since_dt:
            # .new()는 최신순이므로, 기준 시각보다 오래된 글이 나오면 중단
            break

        combined_text = f"{submission.title} {submission.selftext or ''}"
        if keyword_filter and not matches_keywords(combined_text, keyword_filter):
            continue

        results.append({
            "subreddit": subreddit_name,
            "id": submission.id,
            "title": submission.title,
            "author": str(submission.author) if submission.author else "[deleted]",
            "created_utc": created.isoformat(),
            "score": submission.score,
            "num_comments": submission.num_comments,
            "url": f"https://www.reddit.com{submission.permalink}",
            "selftext": (submission.selftext or "")[:1500],  # 과도한 길이 방지
        })

    return results


def fetch_new_comments_on_known_threads(reddit, posts, since_dt):
    """이미 수집된 게시물들에 달린 신규 댓글만 수집 (해당 스레드 내부 한정).
    임의 서브레딧 전체 댓글 스트림을 훑지 않음 — 스코프를 최소화."""
    comments_by_post = {}
    for post in posts:
        try:
            submission = reddit.submission(id=post["id"])
            submission.comments.replace_more(limit=0)
            new_comments = []
            for comment in submission.comments.list():
                created = datetime.fromtimestamp(comment.created_utc, tz=timezone.utc)
                if created >= since_dt:
                    new_comments.append({
                        "author": str(comment.author) if comment.author else "[deleted]",
                        "created_utc": created.isoformat(),
                        "score": comment.score,
                        "body": (comment.body or "")[:1000],
                    })
            if new_comments:
                comments_by_post[post["id"]] = new_comments
        except Exception as e:
            # 개별 스레드 실패가 전체 작업을 막지 않도록 함
            print(f"  [warn] failed to fetch comments for post {post['id']}: {e}")
    return comments_by_post


def build_report(primary_posts, secondary_posts, comments_by_post, since_dt, until_dt):
    """수집 결과를 마크다운 보고서로 정리."""
    lines = [
        "# Reddit Community Monitor — Daily Report",
        f"Period: {since_dt.strftime('%Y-%m-%d %H:%M')} UTC - {until_dt.strftime('%Y-%m-%d %H:%M')} UTC",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
        "",
        "---",
        "",
        "## Summary",
        f"- r/{TARGET_SUBREDDIT_PRIMARY}: {len(primary_posts)} new post(s)",
        f"- r/{TARGET_SUBREDDIT_SECONDARY} (keyword-matched): {len(secondary_posts)} new post(s)",
        f"- Total new comments on tracked threads: "
        f"{sum(len(c) for c in comments_by_post.values())}",
        "",
    ]

    all_posts = [("r/" + TARGET_SUBREDDIT_PRIMARY, primary_posts),
                 ("r/" + TARGET_SUBREDDIT_SECONDARY, secondary_posts)]

    if not primary_posts and not secondary_posts:
        lines += ["> No new posts in this period.", ""]
    else:
        lines += ["## New Posts", ""]
        for label, posts in all_posts:
            if not posts:
                continue
            lines.append(f"### {label}")
            lines.append("")
            for p in posts:
                lines.append(f"**{p['title']}**")
                lines.append(f"- Author: u/{p['author']} | Score: {p['score']} | "
                              f"Comments: {p['num_comments']} | Posted: {p['created_utc']}")
                lines.append(f"- URL: {p['url']}")
                if p["selftext"]:
                    lines.append("")
                    lines.append(p["selftext"])
                new_comments = comments_by_post.get(p["id"])
                if new_comments:
                    lines.append("")
                    lines.append(f"  New comments ({len(new_comments)}):")
                    for c in new_comments:
                        lines.append(f"  - u/{c['author']} ({c['created_utc']}): {c['body'][:300]}")
                lines.append("")
                lines.append("---")
                lines.append("")

    return "\n".join(lines)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    reddit = get_reddit_client()

    until_dt = datetime.now(timezone.utc)
    since_dt = until_dt - timedelta(hours=LOOKBACK_HOURS)

    print(f"Fetching posts since {since_dt.isoformat()}...")

    primary_posts = fetch_new_posts(
        reddit, TARGET_SUBREDDIT_PRIMARY, since_dt, keyword_filter=None
    )
    print(f"  r/{TARGET_SUBREDDIT_PRIMARY}: {len(primary_posts)} new post(s)")

    secondary_posts = fetch_new_posts(
        reddit, TARGET_SUBREDDIT_SECONDARY, since_dt, keyword_filter=BRAND_KEYWORDS
    )
    print(f"  r/{TARGET_SUBREDDIT_SECONDARY} (filtered): {len(secondary_posts)} new post(s)")

    all_posts = primary_posts + secondary_posts
    comments_by_post = fetch_new_comments_on_known_threads(reddit, all_posts, since_dt)

    report = build_report(primary_posts, secondary_posts, comments_by_post, since_dt, until_dt)

    ts = until_dt.strftime("%Y%m%d_%H%M")
    report_path = os.path.join(OUTPUT_DIR, f"reddit_daily_{ts}.md")
    json_path = os.path.join(OUTPUT_DIR, f"reddit_daily_{ts}.json")

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "since": since_dt.isoformat(),
            "until": until_dt.isoformat(),
            "primary_posts": primary_posts,
            "secondary_posts": secondary_posts,
            "comments_by_post": comments_by_post,
        }, f, ensure_ascii=False, indent=2)

    print(f"\nDone. Report saved to: {report_path}")
    print(f"Raw data saved to: {json_path}")
    return report_path


if __name__ == "__main__":
    main()
