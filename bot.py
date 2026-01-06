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
import random
import json
import re
import math
from datetime import datetime, timedelta, timezone

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
WIKIMEDIA_HEADERS = {
    "User-Agent": "x-random-wikipedia-bot/1.0 (https://github.com/ehenden/X-Random-Wikipedia-Bot)"
}

STATE_DIR_NAME = ".bot_state"
HISTORY_FILENAME = "history.json"
DEFAULT_HISTORY_DAYS = 60
DEFAULT_TOPIC_DAYS = 14
TOPIC_TOKEN_LIMIT = 12

TREND_POOL_SIZE = 500
TREND_SAMPLE_SIZE = 60
RANDOM_SAMPLE_SIZE = 20
QUERY_BATCH_SIZE = 20

DEFAULT_RN_MINSIZE = 8000

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


def utcnow():
    return datetime.now(timezone.utc)


def get_base_dir():
    return os.path.dirname(os.path.abspath(__file__))


def get_state_dir():
    return os.path.join(get_base_dir(), STATE_DIR_NAME)


def get_history_path():
    return os.getenv('HISTORY_FILE') or os.path.join(get_state_dir(), HISTORY_FILENAME)


def get_env_int(name, default, min_value=None, max_value=None):
    value = os.getenv(name)
    if value is None or str(value).strip() == '':
        return default
    try:
        parsed = int(str(value).strip())
    except ValueError:
        logger.warning(f"Invalid {name} value '{value}', using {default}")
        return default

    if min_value is not None and parsed < min_value:
        return min_value
    if max_value is not None and parsed > max_value:
        return max_value
    return parsed


def get_env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return str(value).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def title_key(title):
    return ''.join(char for char in (title or '').casefold() if char.isalnum())


TEXT_STOPWORDS = {
    've', 'ile', 'da', 'de', 'bir', 'bu', 'şu', 'için', 'olan', 'olarak', 'üzerine',
    'daha', 'en', 'gibi', 'ancak', 'buna', 'bunun', 'içinde', 'arasında', 'sırasında',
    'tarafından', 'olarak', 'göre', 'sonra', 'önce', 'kadar', 'çok', 'az',
    'the', 'and', 'of', 'in', 'on', 'to', 'a', 'an'
}


def text_tokens(text):
    raw = re.split(r"\W+", (text or '').casefold())
    tokens = set()
    for token in raw:
        token = token.strip('_')
        if not token or len(token) < 3:
            continue
        if any(char.isdigit() for char in token):
            continue
        if token in TEXT_STOPWORDS:
            continue
        tokens.add(token)
    return tokens


def topic_tokens_for_text(text, limit=TOPIC_TOKEN_LIMIT):
    tokens = list(text_tokens(text))
    tokens.sort(key=lambda token: (-len(token), token))
    return tokens[:max(1, limit)]


def is_unwanted_title(title):
    key = title_key(title)
    return key in {'anasayfa'}


def parse_history_timestamp(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def load_history(path):
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
        if isinstance(data, list):
            return data
        logger.warning("History file has unexpected format; ignoring.")
        return []
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to read history file: {e}")
        return []


def save_history(path, entries):
    state_dir = os.path.dirname(path)
    if state_dir:
        os.makedirs(state_dir, exist_ok=True)

    tmp_path = path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as handle:
        json.dump(entries, handle, ensure_ascii=False)
    os.replace(tmp_path, path)


def prune_history(entries, history_days):
    cutoff = utcnow() - timedelta(days=history_days)
    kept = []

    for entry in entries:
        timestamp = parse_history_timestamp(entry.get('timestamp'))
        if timestamp is None:
            continue
        if timestamp >= cutoff:
            kept.append(entry)

    return kept


def build_history_indexes(entries, topic_days):
    recent_title_keys = set()
    recent_pageids = set()
    recent_tokens = set()

    topic_cutoff = utcnow() - timedelta(days=topic_days)

    for entry in entries:
        recent_title_keys.add(entry.get('title_key') or title_key(entry.get('title')))
        pageid = entry.get('pageid')
        if pageid is not None:
            recent_pageids.add(pageid)

        timestamp = parse_history_timestamp(entry.get('timestamp'))
        if timestamp is None or timestamp < topic_cutoff:
            continue
        for token in entry.get('topic_tokens') or []:
            recent_tokens.add(token)

    return recent_title_keys, recent_pageids, recent_tokens


def make_history_entry(article):
    title = article.get('title', '')
    extract = article.get('extract') or ''
    return {
        'title': title,
        'title_key': title_key(title),
        'pageid': article.get('pageid'),
        'url': article.get('url'),
        'timestamp': utcnow().isoformat(),
        'topic_tokens': topic_tokens_for_text(f"{title} {extract}")
    }


def is_article_eligible(article, recent_title_keys, recent_pageids):
    title = article.get('title', '')
    if not title or is_unwanted_title(title) or ':' in title:
        return False
    if title_key(title) in recent_title_keys:
        return False
    pageid = article.get('pageid')
    if pageid is not None and pageid in recent_pageids:
        return False
    if article.get('pageprops', {}).get('disambiguation') is not None:
        return False
    if not article.get('url'):
        return False
    if not article.get('thumbnail_url'):
        return False

    extract = (article.get('extract') or '').strip()
    if len(extract) < MIN_EXTRACT_LEN:
        return False

    length = article.get('length') or 0
    if length < MIN_PAGE_LEN:
        return False

    return True


def pick_from_scored(articles, recent_tokens, top_k=10):
    if not articles:
        return None

    no_overlap = []
    with_overlap = []
    for article in articles:
        candidate_tokens = set(topic_tokens_for_text(
            f"{article.get('title', '')} {article.get('extract', '')}"
        ))
        overlap = bool(candidate_tokens & recent_tokens)
        (with_overlap if overlap else no_overlap).append(article)

    candidates = no_overlap or with_overlap
    if not candidates:
        return None

    scored = [(score_article(article), article) for article in candidates]
    scored.sort(key=lambda item: item[0], reverse=True)
    top = scored[:max(1, top_k)]
    _, chosen = random.choice(top)
    return chosen


def chunked(items, size):
    for index in range(0, len(items), size):
        yield items[index:index + size]


def load_config(require_twitter_credentials=True):
    """Load configuration from environment variables."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dotenv_path = os.path.join(base_dir, '.env')
    load_dotenv(dotenv_path=dotenv_path)

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

    if require_twitter_credentials:
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
        response = requests.get(WIKIPEDIA_RANDOM_API, timeout=10, headers=WIKIMEDIA_HEADERS)
        response.raise_for_status()
        data = response.json()

        article = {
            'pageid': data.get('pageid'),
            'title': data.get('title', 'Unknown Title'),
            'url': data.get('content_urls', {}).get('desktop', {}).get('page', ''),
            'extract': data.get('extract', ''),
            'thumbnail_url': data.get('thumbnail', {}).get('source'),
            'length': None,
            'pageprops': {},
            'views': 0
        }

        logger.info(f"Fetched random article: {article['title']}")
        return article

    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching Wikipedia article: {e}")
        return None


def get_trending_page_titles(pool_size=TREND_POOL_SIZE, days_back=1):
    """Fetch top-viewed Turkish Wikipedia titles for a given day (UTC)."""
    date = (utcnow() - timedelta(days=days_back)).strftime("%Y/%m/%d")
    url = PAGEVIEWS_TOP_API.format(date=date)

    try:
        response = requests.get(url, timeout=10, headers=WIKIMEDIA_HEADERS)
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
        if ':' in title:
            continue
        title_spaces = title.replace('_', ' ')
        if is_unwanted_title(title_spaces) or is_unwanted_title(title):
            continue

        candidates.append({
            'title': title_spaces,
            'views': views
        })

        if len(candidates) >= pool_size:
            break

    logger.info(f"Fetched {len(candidates)} trending candidates for {date}")
    return candidates


def get_page_details(candidates):
    """Fetch details for candidate titles from the Wikipedia query API."""
    if not candidates:
        return []

    title_to_views = {title_key(item.get('title')): item.get('views', 0) for item in candidates}
    titles = [item['title'] for item in candidates]

    results = []
    for batch in chunked(titles, QUERY_BATCH_SIZE):
        params = {
            'action': 'query',
            'format': 'json',
            'titles': '|'.join(batch),
            'prop': 'extracts|pageimages|info|pageprops',
            'exintro': 1,
            'explaintext': 1,
            'exsentences': 2,
            'exlimit': len(batch),
            'pithumbsize': 600,
            'pilimit': len(batch),
            'inprop': 'url',
            'redirects': 1
        }

        try:
            response = requests.get(
                WIKIPEDIA_QUERY_API,
                params=params,
                timeout=10,
                headers=WIKIMEDIA_HEADERS
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching page details: {e}")
            continue

        pages = data.get('query', {}).get('pages', {})
        for page in pages.values():
            if page.get('missing') is not None:
                continue

            title = page.get('title', '')
            if not title:
                continue

            results.append({
                'pageid': page.get('pageid'),
                'title': title,
                'url': page.get('fullurl', ''),
                'extract': page.get('extract', ''),
                'thumbnail_url': page.get('thumbnail', {}).get('source'),
                'length': page.get('length'),
                'pageprops': page.get('pageprops', {}),
                'views': title_to_views.get(title_key(title), 0)
            })

    return results


def get_page_details_by_pageids(pageids):
    """Fetch details for candidate pageids from the Wikipedia query API."""
    if not pageids:
        return []

    results = []
    for batch in chunked([pid for pid in pageids if pid is not None], QUERY_BATCH_SIZE):
        params = {
            'action': 'query',
            'format': 'json',
            'pageids': '|'.join(str(pid) for pid in batch),
            'prop': 'extracts|pageimages|info|pageprops',
            'exintro': 1,
            'explaintext': 1,
            'exsentences': 2,
            'exlimit': len(batch),
            'pithumbsize': 600,
            'pilimit': len(batch),
            'inprop': 'url',
            'redirects': 1
        }

        try:
            response = requests.get(
                WIKIPEDIA_QUERY_API,
                params=params,
                timeout=10,
                headers=WIKIMEDIA_HEADERS
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching page details: {e}")
            continue

        pages = data.get('query', {}).get('pages', {})
        for page in pages.values():
            if page.get('missing') is not None:
                continue

            title = page.get('title', '')
            if not title:
                continue

            results.append({
                'pageid': page.get('pageid'),
                'title': title,
                'url': page.get('fullurl', ''),
                'extract': page.get('extract', ''),
                'thumbnail_url': page.get('thumbnail', {}).get('source'),
                'length': page.get('length'),
                'pageprops': page.get('pageprops', {}),
                'views': 0
            })

    return results


def get_random_candidates(limit, rnminsize):
    """Fetch random Turkish Wikipedia pages (namespace 0, non-redirects)."""
    params = {
        'action': 'query',
        'format': 'json',
        'list': 'random',
        'rnnamespace': 0,
        'rnfilterredir': 'nonredirects',
        'rnlimit': limit,
        'rnminsize': rnminsize
    }

    try:
        response = requests.get(
            WIKIPEDIA_QUERY_API,
            params=params,
            timeout=10,
            headers=WIKIMEDIA_HEADERS
        )
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching random candidates: {e}")
        return []

    random_pages = data.get('query', {}).get('random', []) or []
    candidates = []
    for page in random_pages:
        title = page.get('title', '')
        pageid = page.get('id') or page.get('pageid')
        if not title or is_unwanted_title(title) or ':' in title:
            continue
        candidates.append({'title': title, 'pageid': pageid, 'views': 0})

    return candidates


def get_filtered_random_article(recent_title_keys, recent_pageids, recent_tokens):
    """Pick a random article that matches the quality filters."""
    rnminsize = get_env_int('RN_MINSIZE', DEFAULT_RN_MINSIZE, min_value=0, max_value=1000000)
    sample_size = get_env_int('RANDOM_SAMPLE_SIZE', RANDOM_SAMPLE_SIZE, min_value=5, max_value=50)
    top_k = get_env_int('RANDOM_PICK_TOP_K', 5, min_value=1, max_value=50)
    attempts = get_env_int('RANDOM_ATTEMPTS', 3, min_value=1, max_value=10)

    for _ in range(attempts):
        candidates = get_random_candidates(sample_size, rnminsize)
        pageids = [item.get('pageid') for item in candidates if item.get('pageid') is not None]
        details = get_page_details_by_pageids(pageids)
        eligible = [
            article
            for article in details
            if is_article_eligible(article, recent_title_keys, recent_pageids)
        ]
        chosen = pick_from_scored(eligible, recent_tokens, top_k=top_k)
        if chosen:
            logger.info(f"Selected random article: {chosen['title']}")
            return chosen

    return None


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
        score += min(3.0, math.log10(views + 1))

    return score


def get_trending_article(recent_title_keys, recent_pageids, recent_tokens):
    """Get a trending article with details, filtering, and scoring."""
    pool_size = get_env_int('TREND_POOL_SIZE', TREND_POOL_SIZE, min_value=50, max_value=5000)
    sample_size = get_env_int('TREND_SAMPLE_SIZE', TREND_SAMPLE_SIZE, min_value=10, max_value=200)
    top_k = get_env_int('TREND_PICK_TOP_K', 15, min_value=1, max_value=200)
    trend_days = get_env_int('TREND_DAYS', 3, min_value=1, max_value=30)

    days_back = random.randint(1, trend_days)
    candidates = get_trending_page_titles(pool_size=pool_size, days_back=days_back)
    if not candidates:
        return None

    sample = random.sample(candidates, k=min(sample_size, len(candidates)))
    details = get_page_details(sample)
    eligible = [
        article
        for article in details
        if is_article_eligible(article, recent_title_keys, recent_pageids)
    ]

    chosen = pick_from_scored(eligible, recent_tokens, top_k=top_k)
    if chosen:
        logger.info(f"Selected trending article: {chosen['title']}")
    return chosen


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
        response = requests.get(image_url, stream=True, timeout=10, headers=WIKIMEDIA_HEADERS)
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
        response = getattr(e, 'response', None)
        status_code = getattr(response, 'status_code', None)
        body = getattr(response, 'text', None)
        headers = getattr(response, 'headers', None) or {}
        request_id = headers.get('x-request-id')
        logger.error(
            "Error posting tweet: %s | status=%s request_id=%s body=%s",
            e,
            status_code,
            request_id,
            body
        )
        return False


def run_bot_once(client, api_v1, dry_run=False):
    """
    Run the bot once: fetch an article and post it.

    Args:
        client (tweepy.Client): Authenticated Twitter API client.
        api_v1 (tweepy.API): Authenticated Twitter API v1 client.

    Returns:
        bool: True if successful, False otherwise.
    """
    history_days = get_env_int('HISTORY_DAYS', DEFAULT_HISTORY_DAYS, min_value=1, max_value=3650)
    topic_days = get_env_int('TOPIC_DAYS', DEFAULT_TOPIC_DAYS, min_value=0, max_value=3650)
    history_path = get_history_path()

    history = prune_history(load_history(history_path), history_days)
    recent_title_keys, recent_pageids, recent_tokens = build_history_indexes(history, topic_days)

    article = get_trending_article(recent_title_keys, recent_pageids, recent_tokens)
    if not article:
        logger.warning("No suitable trending article found. Trying random.")
        article = get_filtered_random_article(recent_title_keys, recent_pageids, recent_tokens)

    if not article:
        logger.warning("Falling back to random summary endpoint.")
        fallback = get_random_turkish_wikipedia_article()
        if fallback:
            title = fallback.get('title', '')
            extract = (fallback.get('extract') or '').strip()
            if (
                fallback.get('url')
                and fallback.get('thumbnail_url')
                and len(extract) >= MIN_EXTRACT_LEN
                and not is_unwanted_title(title)
                and title_key(title) not in recent_title_keys
            ):
                article = fallback

    if not article or not article.get('url'):
        logger.error("Failed to find a suitable article to post.")
        return False

    tweet_text = format_tweet(article)

    if dry_run:
        logger.info("Dry-run enabled. Tweet not posted.")
        logger.info(f"Tweet preview:\n{tweet_text}")
        if article.get('thumbnail_url'):
            logger.info(f"Thumbnail: {article['thumbnail_url']}")

        if get_env_bool('DRY_RUN_SAVE_HISTORY', default=True):
            history.append(make_history_entry(article))
            history = prune_history(history, history_days)
            save_history(history_path, history)
            logger.info(f"Saved to history: {article.get('title')}")

        return True

    if client is None or api_v1 is None:
        logger.error("Twitter client is not configured.")
        return False

    media_id = None
    if article.get('thumbnail_url'):
        media_id = upload_media(api_v1, article['thumbnail_url'])

    success = post_tweet(client, tweet_text, media_id)
    if success:
        history.append(make_history_entry(article))
        history = prune_history(history, history_days)
        save_history(history_path, history)
    return success


def run_bot_loop(config, dry_run=False):
    """
    Run the bot in a continuous loop, posting at scheduled intervals.

    Args:
        config (dict): Configuration containing API credentials and settings.
    """
    client = None
    api_v1 = None
    if not dry_run:
        client, api_v1 = create_twitter_clients(config)

    logger.info(f"Bot started. Will post every {config['post_interval']} seconds.")
    logger.info("Press Ctrl+C to stop.")

    try:
        while True:
            success = run_bot_once(client, api_v1, dry_run=dry_run)

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

    dry_run = '--dry-run' in sys.argv
    once = '--once' in sys.argv

    config = load_config(require_twitter_credentials=not dry_run)

    if once:
        client = None
        api_v1 = None
        if not dry_run:
            client, api_v1 = create_twitter_clients(config)
        success = run_bot_once(client, api_v1, dry_run=dry_run)
        sys.exit(0 if success else 1)
    else:
        run_bot_loop(config, dry_run=dry_run)


if __name__ == "__main__":
    main()
