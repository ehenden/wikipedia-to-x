# AGENTS.md

GUIDELINE (project)

Goal
- Post a Turkish Wikipedia article to X with minimal effort.
- Prefer trending topics, keep randomness, avoid repeats.
- No database; use a small local history file for de-duplication.

Scope
- Fetch: trending candidates from Wikimedia pageviews; fall back to random.
- Random candidates use `action=query&list=random` with size filter.
- Details: `action=query` for extract, thumbnail, page length, and URL.
- Post: title + short extract + URL, with thumbnail as media when available.
- Scheduling: simple sleep loop; support `--once` for cron.

Configuration
- Read from `.env` (via dotenv) or environment variables.
- Required: `TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_TOKEN_SECRET`.
- Optional: `POST_INTERVAL` (seconds, default 3600).
- Optional: `HISTORY_DAYS`, `TOPIC_DAYS`, `RN_MINSIZE`.

Behavior
- If tweet exceeds 280 chars, truncate title and append `...`.
- Skip short or low-quality pages (no thumbnail, short extract, short page length).
- Avoid repeating the same article for `HISTORY_DAYS`.
- Reduce topic repetition for `TOPIC_DAYS` using token overlap.
- If trending fetch fails, fall back to random; log and retry later.
- For `--once`, exit 0 on success and 1 on failure.

Non-goals
- No DB, no queues.
- No UI, no web server.

Coding style
- Keep logic in `bot.py` with small, readable functions.
- Minimal dependencies (requests, tweepy, python-dotenv).
- Log to console with timestamps.

Tests
- Unit tests only; mock external calls.
- Avoid network in tests.
