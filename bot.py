#!/usr/bin/env python3
"""
X Random Wikipedia Bot
A bot that posts random Turkish Wikipedia article links to X (Twitter).
"""

import os
import sys
import time
import logging
import tempfile
from datetime import datetime, timedelta

import requests
import tweepy
from dotenv import load_dotenv

# Constants
TWITTER_CHAR_LIMIT = 280
TRUNCATION_OVERHEAD = 5  # Space for newlines and ellipsis
DEFAULT_POST_INTERVAL = 3600  # 1 hour in seconds

WIKIPEDIA_RANDOM_API = "https://tr.wikipedia.org/api/rest_v1/page/random/summary"
WIKIPEDIA_QUERY_API = "https://tr.wikipedia.org/w/api.php"
PAGEVIEWS_TOP_API = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/tr.wikipedia"
    "/all-access/{date}"
)

TREND_CANDIDATE_LIMIT = 50
MIN_EXTRACT_LEN = 100
STRONG_EXTRACT_LEN = 200
MIN_PAGE_LEN = 5000
STRONG_PAGE_LEN = 10000

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config():
    """Load configuration from environment variables."""
    load_dotenv()

    # Parse post interval with error handling
    post_interval_str = os.getenv('POST_INTERVAL', str(DEFAULT_POST_INTERVAL))
    try:
        post_interval = int(post_interval_str)
        if post_interval <= 0:
            raise ValueError("POST_INTERVAL must be positive")
    except ValueError as e:
        logger.error(f"Invalid POST_INTERVAL value '{post_interval_str}': {e}")
        logger.info(f"Using default interval: {DEFAULT_POST_INTERVAL} seconds")
        post_interval = DEFAULT_POST_INTERVAL

    config = {
        'api_key': os.getenv('TWITTER_API_KEY'),
        'api_secret': os.getenv('TWITTER_API_SECRET'),
        'access_token': os.getenv('TWITTER_ACCESS_TOKEN'),
        'access_token_secret': os.getenv('TWITTER_ACCESS_TOKEN_SECRET'),
        'post_interval': post_interval
    }

    # Validate required credentials
    required_keys = ['api_key', 'api_secret', 'access_token', 'access_token_secret']
    missing_keys = [key for key in required_keys if not config[key]]

    if missing_keys:
        logger.error(f"Missing required environment variables: {', '.join(missing_keys)}")
        logger.error("Please check your .env file or environment variables.")
        sys.exit(1)

    return config


def get_random_turkish_wikipedia_article():
    """
    Fetch a random Turkish Wikipedia article using the Wikipedia REST API.

    Returns:
        dict: Article information containing title and URL, or None if error occurs.
    """
    try:
        response = requests.get(WIKIPEDIA_RANDOM_API, timeout=10)
        response.raise_for_status()
        data = response.json()

        article = {
            'title': data.get('title', 'Unknown Title'),
            'url': data.get('content_urls', {}).get('desktop', {}).get('page', ''),
            'extract': data.get('extract', ''),
            'thumbnail_url': None,
            'length': None,
            'pageprops': {},
            'views': 0
        }

        logger.info(f"Fetched random article: {article['title']}")
        return article

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching Wikipedia article: {e}")
        return None


def get_trending_page_titles(limit=TREND_CANDIDATE_LIMIT):
    """Fetch top-viewed Turkish Wikipedia titles for yesterday."""
    date = (datetime.utcnow() - timedelta(days=1)).strftime("%Y/%m/%d")
    url = PAGEVIEWS_TOP_API.format(date=date)

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching pageviews: {e}")
        return []

    items = data.get('items', [])
    if not items:
        logger.warning("No pageviews data returned")
        return []

    articles = items[0].get('articles', [])
    candidates = []

    for article in articles:
        title = article.get('article', '')
        views = article.get('views', 0)

        if not title:
            continue
        if title == 'Ana_Sayfa':
            continue
        if ':' in title:
            continue

        candidates.append({
            'title': title.replace('_', ' '),
            'views': views
        })

        if len(candidates) >= limit:
            break

    logger.info(f"Fetched {len(candidates)} trending candidates")
    return candidates


def get_page_details(candidates):
    """Fetch details for candidate titles from the Wikipedia query API."""
    if not candidates:
        return []

    title_to_views = {item['title']: item.get('views', 0) for item in candidates}
    titles = [item['title'] for item in candidates]

    params = {
        'action': 'query',
        'format': 'json',
        'titles': '|'.join(titles),
        'prop': 'extracts|pageimages|info|pageprops',
        'exintro': 1,
        'explaintext': 1,
        'exsentences': 2,
        'pithumbsize': 600,
        'inprop': 'url',
        'redirects': 1
    }

    try:
        response = requests.get(WIKIPEDIA_QUERY_API, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching page details: {e}")
        return []

    pages = data.get('query', {}).get('pages', {})
    results = []

    for page in pages.values():
        title = page.get('title', '')
        if not title:
            continue

        results.append({
            'title': title,
            'url': page.get('fullurl', ''),
            'extract': page.get('extract', ''),
            'thumbnail_url': page.get('thumbnail', {}).get('source'),
            'length': page.get('length'),
            'pageprops': page.get('pageprops', {}),
            'views': title_to_views.get(title, 0)
        })

    return results


def score_article(article):
    """Score article based on extract length, page length, views, and thumbnail."""
    if article.get('pageprops', {}).get('disambiguation') is not None:
        return float('-inf')

    score = 0.0

    if article.get('thumbnail_url'):
        score += 5
    else:
        score -= 5

    extract_len = len(article.get('extract', '') or '')
    if extract_len >= STRONG_EXTRACT_LEN:
        score += 3
    elif extract_len >= MIN_EXTRACT_LEN:
        score += 1

    page_len = article.get('length') or 0
    if page_len >= STRONG_PAGE_LEN:
        score += 2
    elif page_len >= MIN_PAGE_LEN:
        score += 1

    views = article.get('views') or 0
    if views > 0:
        score += min(5.0, views / 10000.0)

    return score


def pick_best_article(articles):
    """Pick the best article by score, preferring those with thumbnails."""
    if not articles:
        return None

    with_thumb = [item for item in articles if item.get('thumbnail_url')]
    candidates = with_thumb or articles

    best = None
    best_score = float('-inf')

    for article in candidates:
        score = score_article(article)
        if score > best_score:
            best_score = score
            best = article

    return best


def get_trending_article():
    """Get a trending article with details and scoring."""
    candidates = get_trending_page_titles()
    if not candidates:
        return None

    details = get_page_details(candidates)
    if not details:
        return None

    best = pick_best_article(details)
    if best:
        logger.info(f"Selected trending article: {best['title']}")

    return best


def truncate_text(text, max_len):
    if max_len <= 0:
        return ''
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    return text[:max_len - 3] + '...'


def format_tweet(article):
    """
    Format a tweet with the article information.

    Args:
        article (dict): Article information containing title, URL, and extract.

    Returns:
        str: Formatted tweet text.
    """
    title = article.get('title', '').strip()
    url = article.get('url', '').strip()
    extract = (article.get('extract', '') or '').strip()

    if not extract:
        tweet = f"{title}\n\n{url}"
        if len(tweet) > TWITTER_CHAR_LIMIT:
            max_title_length = TWITTER_CHAR_LIMIT - len(url) - TRUNCATION_OVERHEAD
            title = truncate_text(title, max_title_length)
            tweet = f"{title}\n\n{url}"
        return tweet

    tweet = f"{title}\n\n{extract}\n\n{url}"
    if len(tweet) <= TWITTER_CHAR_LIMIT:
        return tweet

    available = TWITTER_CHAR_LIMIT - len(title) - len(url) - 4
    if available <= 0:
        max_title_length = TWITTER_CHAR_LIMIT - len(url) - TRUNCATION_OVERHEAD
        title = truncate_text(title, max_title_length)
        return f"{title}\n\n{url}"

    extract = truncate_text(extract, available)
    return f"{title}\n\n{extract}\n\n{url}"


def create_twitter_clients(config):
    """
    Create and authenticate Twitter API clients.

    Returns:
        tuple: (tweepy.Client, tweepy.API)
    """
    try:
        client = tweepy.Client(
            consumer_key=config['api_key'],
            consumer_secret=config['api_secret'],
            access_token=config['access_token'],
            access_token_secret=config['access_token_secret']
        )
        auth = tweepy.OAuth1UserHandler(
            config['api_key'],
            config['api_secret'],
            config['access_token'],
            config['access_token_secret']
        )
        api_v1 = tweepy.API(auth)
        logger.info("Successfully authenticated with X API")
        return client, api_v1
    except Exception as e:
        logger.error(f"Error creating Twitter client: {e}")
        sys.exit(1)


def upload_media(api_v1, image_url):
    """Download an image and upload to X, returning media_id."""
    if not image_url:
        return None

    temp_path = None
    try:
        response = requests.get(image_url, stream=True, timeout=10)
        response.raise_for_status()

        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    tmp_file.write(chunk)
            temp_path = tmp_file.name

        media = api_v1.media_upload(temp_path)
        return media.media_id_string
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to download thumbnail: {e}")
        return None
    except tweepy.TweepyException as e:
        logger.warning(f"Failed to upload media: {e}")
        return None
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                logger.warning("Failed to remove temp image file")


def post_tweet(client, tweet_text, media_id=None):
    """
    Post a tweet to X (Twitter).

    Args:
        client (tweepy.Client): Authenticated Twitter API client.
        tweet_text (str): The text to tweet.
        media_id (str): Optional media id to attach.

    Returns:
        bool: True if successful, False otherwise.
    """
    try:
        if media_id:
            client.create_tweet(text=tweet_text, media_ids=[media_id])
        else:
            client.create_tweet(text=tweet_text)
        logger.info(f"Successfully posted tweet: {tweet_text[:50]}...")
        return True
    except tweepy.TweepyException as e:
        logger.error(f"Error posting tweet: {e}")
        return False


def run_bot_once(client, api_v1):
    """
    Run the bot once: fetch an article and post it.

    Args:
        client (tweepy.Client): Authenticated Twitter API client.
        api_v1 (tweepy.API): Authenticated Twitter API v1 client.

    Returns:
        bool: True if successful, False otherwise.
    """
    # Prefer trending articles with thumbnails
    article = get_trending_article()
    if not article or not article.get('url'):
        logger.warning("Falling back to random article")
        article = get_random_turkish_wikipedia_article()

    if not article or not article.get('url'):
        logger.error("Failed to fetch article or article has no URL")
        return False

    # Format tweet
    tweet_text = format_tweet(article)

    # Upload media if available
    media_id = None
    if article.get('thumbnail_url'):
        media_id = upload_media(api_v1, article['thumbnail_url'])

    # Post tweet
    return post_tweet(client, tweet_text, media_id)


def run_bot_loop(config):
    """
    Run the bot in a continuous loop, posting at scheduled intervals.

    Args:
        config (dict): Configuration containing API credentials and settings.
    """
    client, api_v1 = create_twitter_clients(config)

    logger.info(f"Bot started. Will post every {config['post_interval']} seconds.")
    logger.info("Press Ctrl+C to stop.")

    try:
        while True:
            success = run_bot_once(client, api_v1)

            if success:
                logger.info(f"Waiting {config['post_interval']} seconds until next post...")
            else:
                logger.warning("Failed to post. Retrying in 60 seconds...")
                time.sleep(60)
                continue

            time.sleep(config['post_interval'])

    except KeyboardInterrupt:
        logger.info("\nBot stopped by user.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


def main():
    """Main entry point for the bot."""
    logger.info("Starting X Random Wikipedia Bot...")

    # Load configuration
    config = load_config()

    # Check if running once or in loop mode
    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        # Run once and exit
        client, api_v1 = create_twitter_clients(config)
        success = run_bot_once(client, api_v1)
        sys.exit(0 if success else 1)
    else:
        # Run in continuous loop
        run_bot_loop(config)


if __name__ == "__main__":
    main()
