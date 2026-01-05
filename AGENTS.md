# AGENTS.md

GUIDELINE (project)

Goal
- Post a random Turkish Wikipedia article to X with minimal effort.
- No database, no persistent state.

Scope
- Fetch: use `https://tr.wikipedia.org/api/rest_v1/page/random/summary`.
- Post: title + blank line + URL.
- Scheduling: simple sleep loop; support `--once` for cron.

Configuration
- Read from `.env` (via dotenv) or environment variables.
- Required: `TWITTER_API_KEY`, `TWITTER_API_SECRET`, `TWITTER_ACCESS_TOKEN`, `TWITTER_ACCESS_TOKEN_SECRET`.
- Optional: `POST_INTERVAL` (seconds, default 3600).

Behavior
- If tweet exceeds 280 chars, truncate title and append `...`.
- If Wikipedia fetch fails or URL missing, log and retry later.
- For `--once`, exit 0 on success and 1 on failure.

Non-goals
- No DB, no history, no de-duplication, no queues.
- No UI, no web server.

Coding style
- Keep logic in `bot.py` with small, readable functions.
- Minimal dependencies (requests, tweepy, python-dotenv).
- Log to console with timestamps.

Tests
- Unit tests only; mock external calls.
- Avoid network in tests.
