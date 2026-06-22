# Pittasoft CS — Reddit Community Monitor

Internal, read-only monitoring tool for Pittasoft's Customer Support team.

## Purpose

This tool retrieves new public posts (and new comments on already-tracked
posts) from two subreddits — `r/blackvue` and `r/dashcams` — once per day,
so the CS team can identify customer-reported product issues quickly.

**This tool does not post, comment, vote, send messages, or otherwise
write to Reddit in any way.** It is strictly read-only.

- `r/blackvue`: all new posts are retrieved (dedicated brand subreddit).
- `r/dashcams`: only posts matching brand/model keywords (e.g. "BlackVue",
  "DR970X", "Elite 10") are retrieved, since this subreddit covers many
  dashcam brands.

Output is a Markdown + JSON report saved locally (`output/` folder). It is
not published, redistributed, or shared with anyone outside the company's
internal CS team.

## Requirements

```
pip install praw
```

## Setup

1. Register a Reddit "script" app at https://www.reddit.com/prefs/apps
   under a dedicated company account (not a personal account).
2. Set the following environment variables before running:

   | Variable | Description |
   |---|---|
   | `REDDIT_CLIENT_ID` | From the registered app |
   | `REDDIT_CLIENT_SECRET` | From the registered app |
   | `REDDIT_USERNAME` | The dedicated Reddit account username |
   | `REDDIT_PASSWORD` | The dedicated Reddit account password |
   | `REDDIT_USER_AGENT` | e.g. `pittasoft-cs-monitor/1.0 by u/<username>` |

   Example (macOS/Linux shell):
   ```bash
   export REDDIT_CLIENT_ID="..."
   export REDDIT_CLIENT_SECRET="..."
   export REDDIT_USERNAME="..."
   export REDDIT_PASSWORD="..."
   export REDDIT_USER_AGENT="pittasoft-cs-monitor/1.0 by u/pittasoft_cs_monitor"
   ```

   **Never commit credentials to source control.** Use a `.env` file
   (excluded via `.gitignore`) or your scheduler's secret manager.

## Run

```bash
python reddit_monitor.py
```

This produces:
- `output/reddit_daily_<timestamp>.md` — human-readable report
- `output/reddit_daily_<timestamp>.json` — raw structured data

## Scheduling

Intended to run once per day (e.g. via cron, Windows Task Scheduler, or
an internal automation platform). Each run looks back 24 hours
(`LOOKBACK_HOURS` in `reddit_monitor.py`) for new posts/comments.

## Data handling

- Only public post/comment content and basic metadata (author username,
  score, comment count, timestamp, URL) are retrieved.
- No attempt is made to infer sensitive personal characteristics about
  any Reddit user.
- No bulk historical scraping — only new content since the last run.
- Data is used solely for internal CS triage and is not sold, licensed,
  or shared with third parties.
