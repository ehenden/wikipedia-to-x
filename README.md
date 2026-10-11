# X-Random-Wikipedia-Bot

A Python bot that posts Turkish Wikipedia articles to X (Twitter) at scheduled intervals.

## Features

- Prefers trending topics, with random fallback
- Filters out low-quality pages (short extract, short page, no thumbnail)
- Avoids repeats with a lightweight local history file
- Posts title + short extract + URL, with thumbnail as media
- Configurable posting intervals
- Dry-run mode for safe local testing

## Requirements

- Python 3.7 or higher
- X (Twitter) Developer Account with API credentials
- Internet connection

## Free hosted publishing with Buffer

The GitHub workflow publishes through Buffer rather than calling the X API directly.
Connect the intended X account to Buffer Free, verify your email, and create a personal
API key. Add `BUFFER_API_KEY` and `BUFFER_CHANNEL_ID` to GitHub Actions repository secrets.
Never put the API key in source code or workflow files.

The workflow runs every three hours at minute 17 UTC (03:17, 06:17, 09:17, 12:17,
15:17, 18:17, 21:17, and 00:17 in Istanbul). GitHub scheduled runs can be delayed.
It uses `shareNow`, so Buffer's queue posting slots are not used.

Article history is stored on the `bot-state` branch using the workflow's temporary
GitHub token. Actual history updates create repository activity, reducing the risk
of the public-repository schedule being disabled after 60 days without activity.
History synchronization fails closed on API errors. Runs are serialized.

Buffer accepting a post does not prove it was published on X. Inspect Buffer and X
for publication failures or account reconnection requests. A failed or uncertain
submission is recorded in history and is not automatically resubmitted, avoiding
duplicate posts after timeouts. History contains only public article metadata and
Buffer post IDs; it contains no credentials.

For local Buffer use, set `PUBLISH_PROVIDER=buffer`, `BUFFER_API_KEY`, and
`BUFFER_CHANNEL_ID` in your ignored `.env`. Direct X publishing remains available
with `PUBLISH_PROVIDER=twitter` and the existing Twitter credentials.

References: [Buffer API](https://developers.buffer.com/guides/posts-and-scheduling.html),
[Buffer Free limits](https://support.buffer.com/en-us/articles/what-is-buffers-api-GtIYIQilz5).

## Installation

1. Clone the repository:
```bash
git clone https://github.com/ehenden/X-Random-Wikipedia-Bot.git
cd X-Random-Wikipedia-Bot
```

2. Install required dependencies:
```bash
python -m pip install -r requirements.txt
```

3. Set up your environment variables:
   - Copy `.env.example` to `.env`:
     ```bash
     cp .env.example .env
     ```
   - Edit `.env` and add your X API credentials:
     ```
     TWITTER_API_KEY=your_api_key_here
     TWITTER_API_SECRET=your_api_secret_here
     TWITTER_ACCESS_TOKEN=your_access_token_here
     TWITTER_ACCESS_TOKEN_SECRET=your_access_token_secret_here
     POST_INTERVAL=3600
     HISTORY_DAYS=60
     TOPIC_DAYS=14
     RN_MINSIZE=8000
     ```

## Getting X API Credentials

1. Go to [Twitter Developer Portal](https://developer.twitter.com/)
2. Create a new app or use an existing one
3. Navigate to "Keys and Tokens" section
4. Generate/copy the following:
   - API Key (Consumer Key)
   - API Secret Key (Consumer Secret)
   - Access Token
   - Access Token Secret
5. Ensure your app has "Read and Write" permissions

## Usage

### Run continuously (posts at scheduled intervals)
```bash
python bot.py
```

The bot will:
- Post a Turkish Wikipedia article
- Wait for the specified interval (default: 1 hour)
- Repeat indefinitely

Press `Ctrl+C` to stop the bot.

### Run once (post a single article and exit)
```bash
python bot.py --once
```

This is useful for:
- Testing your configuration
- Running via cron jobs
- One-time posts

### Dry-run (no tweet is posted)
```bash
python bot.py --once --dry-run
```

## Configuration

Edit the `.env` file to configure the bot:

- `TWITTER_API_KEY`: Your X API key
- `TWITTER_API_SECRET`: Your X API secret
- `TWITTER_ACCESS_TOKEN`: Your access token
- `TWITTER_ACCESS_TOKEN_SECRET`: Your access token secret
- `POST_INTERVAL`: Time between posts in seconds (default: 3600 = 1 hour)
- `HISTORY_DAYS`: Do not repeat the same article for N days (default: 60)
- `TOPIC_DAYS`: Reduce topic repetition for N days (default: 14)
- `RN_MINSIZE`: Random page minimum size in bytes (default: 8000)

## How It Works

1. Pulls a pool of trending articles from Wikimedia pageviews
2. Samples candidates, fetches details (extract, thumbnail, length, URL)
3. Filters by quality and recent history
4. Scores and selects a candidate with randomness
5. Posts title + short extract + URL with thumbnail as media
6. Falls back to random candidates if needed

## Scheduling with Cron

To run the bot at specific times using cron:

1. Make the script executable:
```bash
chmod +x bot.py
```

2. Add to crontab (edit with `crontab -e`):
```bash
# Post every hour
0 * * * * cd /path/to/X-Random-Wikipedia-Bot && /usr/bin/python3 bot.py --once

# Post every 6 hours
0 */6 * * * cd /path/to/X-Random-Wikipedia-Bot && /usr/bin/python3 bot.py --once
```

## History Cache

The bot stores a small local history file in `.bot_state/history.json` to avoid repeats.
This folder is ignored by git in the code branch. GitHub Actions persists it separately
on the `bot-state` branch between runs.

## Logging

The bot logs all activities including:
- Successful posts
- API errors
- Article fetch operations
- Timing information

Logs are displayed in the console with timestamps.

## Troubleshooting

**Error: Missing required environment variables**
- Ensure your `.env` file exists and contains all required credentials
- Check that variable names match exactly

**Error: Authentication failed**
- Verify your API credentials are correct
- Ensure your X app has "Read and Write" permissions
- Check that tokens haven't expired

**Error: Rate limit exceeded**
- X has rate limits on API calls
- Increase `POST_INTERVAL` to post less frequently
- Wait for the rate limit window to reset

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Disclaimer

This bot is for educational purposes. Make sure to comply with:
- X (Twitter) Terms of Service
- X Developer Agreement and Policy
- Wikipedia Terms of Use
- Responsible bot behavior guidelines
