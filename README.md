# X-Random-Wikipedia-Bot

A Python bot that automatically posts random Turkish Wikipedia article links to X (Twitter) at scheduled intervals.

## Features

- 🤖 Automatically fetches random Turkish Wikipedia articles
- 🐦 Posts article links to X (Twitter) with proper formatting
- ⏰ Configurable posting intervals
- 🔒 Secure credential management using environment variables
- 📝 Comprehensive logging
- 🔄 Continuous operation with error handling

## Requirements

- Python 3.7 or higher
- X (Twitter) Developer Account with API credentials
- Internet connection

## Installation

1. Clone the repository:
```bash
git clone https://github.com/ehenden/X-Random-Wikipedia-Bot.git
cd X-Random-Wikipedia-Bot
```

2. Install required dependencies:
```bash
pip install -r requirements.txt
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
- Post a random Turkish Wikipedia article
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

## Configuration

Edit the `.env` file to configure the bot:

- `TWITTER_API_KEY`: Your X API key
- `TWITTER_API_SECRET`: Your X API secret
- `TWITTER_ACCESS_TOKEN`: Your access token
- `TWITTER_ACCESS_TOKEN_SECRET`: Your access token secret
- `POST_INTERVAL`: Time between posts in seconds (default: 3600 = 1 hour)

## How It Works

1. The bot connects to the Turkish Wikipedia API (`tr.wikipedia.org`)
2. Fetches a random article using the REST API endpoint
3. Extracts the article title and URL
4. Formats a tweet with the article information
5. Posts the tweet to X using the Twitter API
6. Waits for the configured interval before repeating

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