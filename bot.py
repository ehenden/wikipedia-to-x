#!/usr/bin/env python3
"""
Publish Wikipedia articles to X through Buffer.
"""

import os
import sys
import argparse
import logging
import random
import json
import re
import math
import unicodedata
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

# Constants
POST_CHAR_LIMIT = 280
SOURCE_URL_WEIGHT = 23  # X wraps source links with t.co

PAGEVIEWS_TOP_API = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/{language}.wikipedia"
    "/all-access/{date}"
)
WIKIMEDIA_HEADERS = {
    "User-Agent": "wikipedia-to-x/1.0 (https://github.com/ehenden/wikipedia-to-x)"
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
        raise ValueError('Publication history must be a list; refusing to publish')
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError('Cannot read publication history; refusing to publish') from e


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
        if entry.get('wiki_language', 'tr') != get_wiki_language():
            continue
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
        'wiki_language': get_wiki_language(),
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


def get_wiki_language():
    language = os.getenv('WIKI_LANGUAGE', 'tr').strip().lower()
    if not re.fullmatch(r'[a-z]{2,12}(?:-[a-z0-9]{1,12})*', language):
        raise ValueError('WIKI_LANGUAGE must be a Wikipedia language code, such as tr or en')
    return language


def wikipedia_url(path):
    return f'https://{get_wiki_language()}.wikipedia.org{path}'


def load_config(require_credentials=True):
    """Read Buffer credentials from the environment or an ignored .env file."""
    load_dotenv(dotenv_path=os.path.join(get_base_dir(), '.env'))
    config = {
        'buffer_api_key': os.getenv('BUFFER_API_KEY'),
        'buffer_channel_id': os.getenv('BUFFER_CHANNEL_ID'),
    }
    config['wiki_language'] = get_wiki_language()
    config['article_source'] = os.getenv('ARTICLE_SOURCE', 'popular').strip().lower()
    config['wiki_category'] = os.getenv('WIKI_CATEGORY', '').strip()
    if config['article_source'] not in {'popular', 'random', 'category'}:
        raise ValueError('ARTICLE_SOURCE must be popular, random, or category')
    if config['article_source'] == 'category' and not config['wiki_category'].startswith('Category:'):
        raise ValueError('Category mode requires WIKI_CATEGORY with a Category: prefix')
    if require_credentials and not (config['buffer_api_key'] and config['buffer_channel_id']):
        sys.exit('BUFFER_API_KEY and BUFFER_CHANNEL_ID are required')
    return config


def get_random_article():
    """
    Fetch a random Wikipedia article using the Wikipedia REST API.

    Returns:
        dict: Article information containing title and URL, or None if error occurs.
    """
    try:
        response = requests.get(wikipedia_url('/api/rest_v1/page/random/summary'), timeout=10, headers=WIKIMEDIA_HEADERS)
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
    """Fetch top-viewed Wikipedia titles for a given day (UTC)."""
    date = (utcnow() - timedelta(days=days_back)).strftime("%Y/%m/%d")
    url = PAGEVIEWS_TOP_API.format(language=get_wiki_language(), date=date)

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
                wikipedia_url('/w/api.php'),
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
                wikipedia_url('/w/api.php'),
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
    """Fetch random Wikipedia pages (namespace 0, non-redirects)."""
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
            wikipedia_url('/w/api.php'),
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


def get_category_article(category, recent_title_keys, recent_pageids, recent_tokens):
    """Sample direct category members; bound requests and never leave the category."""
    params = {
        'action': 'query', 'format': 'json', 'list': 'categorymembers',
        'cmtitle': category, 'cmnamespace': 0, 'cmtype': 'page',
        'cmprop': 'ids|title', 'cmlimit': 500,
    }
    members = []
    try:
        for _ in range(3):
            response = requests.get(wikipedia_url('/w/api.php'), params=dict(params),
                                    timeout=10, headers=WIKIMEDIA_HEADERS)
            response.raise_for_status()
            data = response.json()
            if data.get('error'):
                logger.error('Wikipedia rejected the category query')
                return None
            members.extend(data.get('query', {}).get('categorymembers', []))
            continuation = data.get('continue', {})
            if len(members) >= 500 or not continuation.get('cmcontinue'):
                break
            params.update(continuation)
    except (requests.exceptions.RequestException, ValueError):
        logger.error('Category query failed')
        return None
    members = members[:500]
    sample = random.sample(members, k=min(60, len(members)))
    details = get_page_details_by_pageids([member['pageid'] for member in sample])
    eligible = [article for article in details
                if is_article_eligible(article, recent_title_keys, recent_pageids)]
    return pick_from_scored(eligible, recent_tokens)


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


def text_weight(text):
    # twitter-text v3 single-weight ranges, including Turkish/Latin characters.
    # Emoji sequences remain conservatively overcounted without another dependency.
    # https://github.com/twitter/twitter-text/blob/master/config/v3.json
    text = unicodedata.normalize('NFC', text)
    return sum(1 if (ord(char) <= 0x10FF or 0x2000 <= ord(char) <= 0x200D
                     or 0x2010 <= ord(char) <= 0x201F
                     or 0x2032 <= ord(char) <= 0x2037) else 2 for char in text)


def truncate_text(text, max_weight):
    text = unicodedata.normalize('NFC', text)
    if max_weight <= 0:
        return ''
    if text_weight(text) <= max_weight:
        return text
    suffix = '...' if max_weight >= 3 else ''
    budget = max_weight - len(suffix)
    result = []
    for char in text:
        weight = text_weight(char)
        if weight > budget:
            break
        result.append(char)
        budget -= weight
    return ''.join(result) + suffix


def format_post(article):
    """Preserve the source URL and fit a conservative X Unicode character budget."""
    title = unicodedata.normalize('NFC', article.get('title', '').strip())
    url = article.get('url', '').strip()
    extract = unicodedata.normalize('NFC', (article.get('extract') or '').strip())
    title = truncate_text(title, POST_CHAR_LIMIT - SOURCE_URL_WEIGHT - 2)
    available = POST_CHAR_LIMIT - text_weight(title) - SOURCE_URL_WEIGHT - 4
    extract = truncate_text(extract, available)
    body = f'{title}\n\n{extract}' if extract else title
    return f'{body}\n\n{url}'


def post_to_buffer(config, post_text, image_url=None):
    """Submit once to Buffer; acceptance is not proof of X publication."""
    query = '''mutation Publish($input: CreatePostInput!) {
      createPost(input: $input) {
        __typename
        ... on PostActionSuccess { post { id } }
        ... on MutationError { message }
      }
    }'''
    post_input = {
        'channelId': config['buffer_channel_id'],
        'text': post_text,
        'schedulingType': 'automatic',
        'mode': 'shareNow',
        'assets': [{'image': {'url': image_url}}] if image_url else [],
        'needsApproval': False,
    }
    try:
        response = requests.post(
            'https://api.buffer.com',
            headers={'Authorization': 'Bearer ' + config['buffer_api_key']},
            json={'query': query, 'variables': {'input': post_input}},
            timeout=45,
        )
        response.raise_for_status()
        data = response.json()
        if data.get('errors'):
            logger.error('Buffer GraphQL request failed; no automatic resubmission')
            return False
        result = (data.get('data') or {}).get('createPost') or {}
        post_id = (result.get('post') or {}).get('id')
        if result.get('__typename') != 'PostActionSuccess' or not post_id:
            logger.error('Buffer rejected the post (type=%s)', result.get('__typename'))
            return False
        logger.info('Buffer accepted post id=%s; verify publication in X', post_id)
        return post_id
    except (requests.exceptions.RequestException, ValueError):
        # A timed-out mutation may have succeeded. Never retry it blindly.
        logger.error('Buffer request failed or outcome is unknown; check Buffer before retrying')
        return False


def verify_buffer_post(config, post_id):
    """Read delivery state without ever resubmitting an accepted mutation."""
    query = '''query VerifyPost($input: PostInput!) {
      post(input: $input) { id status sentAt externalLink error { message } }
    }'''
    last = {}
    for attempt in range(4):
        if attempt:
            import time
            time.sleep(5)
        try:
            response = requests.post('https://api.buffer.com',
                headers={'Authorization': 'Bearer ' + config['buffer_api_key']},
                json={'query': query, 'variables': {'input': {'id': post_id}}}, timeout=15)
            response.raise_for_status()
            data = response.json()
            if data.get('errors'):
                logger.error('Buffer delivery query failed; accepted post will not be resubmitted')
                return {'status': 'unknown'}
            last = (data.get('data') or {}).get('post') or {}
            logger.info('Buffer delivery id=%s status=%s sentAt=%s externalLink=%s',
                        post_id, last.get('status'), last.get('sentAt'), last.get('externalLink'))
            if last.get('status') in {'sent', 'error'} or last.get('error'):
                return last
        except (requests.RequestException, ValueError):
            logger.error('Cannot verify Buffer delivery; accepted post will not be resubmitted')
            return {'status': 'unknown'}
    return last or {'status': 'unknown'}


def run_bot_once(config, dry_run=False):
    """Select one article, submit it to Buffer, and record the outcome."""
    history_days = get_env_int('HISTORY_DAYS', DEFAULT_HISTORY_DAYS, min_value=1, max_value=3650)
    topic_days = get_env_int('TOPIC_DAYS', DEFAULT_TOPIC_DAYS, min_value=0, max_value=3650)
    history_path = get_history_path()

    history = prune_history(load_history(history_path), history_days)
    interval = get_env_int('POST_INTERVAL', 1800, min_value=60, max_value=86400)
    if not dry_run:
        reserved = [parse_history_timestamp(entry.get('timestamp')) for entry in history
                    if entry.get('buffer_submission') in
                    {'accepted', 'failed_or_unknown', 'pending'}]
        latest = max((stamp for stamp in reserved if stamp is not None), default=None)
        if latest and (utcnow() - latest).total_seconds() < interval:
            logger.info('Publication interval has not elapsed; skipping without AI or Buffer calls')
            return True
    recent_title_keys, recent_pageids, recent_tokens = build_history_indexes(history, topic_days)

    source = config.get('article_source', 'popular')
    article = None
    if source == 'category':
        article = get_category_article(config['wiki_category'], recent_title_keys,
                                       recent_pageids, recent_tokens)
    else:
        if source == 'popular':
            article = get_trending_article(recent_title_keys, recent_pageids, recent_tokens)
        if not article:
            article = get_filtered_random_article(recent_title_keys, recent_pageids, recent_tokens)
        if not article:
            fallback = get_random_article()
            if fallback:
                title = fallback.get('title', '')
                extract = (fallback.get('extract') or '').strip()
                if (fallback.get('url') and fallback.get('thumbnail_url')
                        and len(extract) >= MIN_EXTRACT_LEN
                        and not is_unwanted_title(title) and ':' not in title
                        and title_key(title) not in recent_title_keys
                        and fallback.get('pageid') not in recent_pageids):
                    article = fallback

    if not article or not article.get('url'):
        logger.error("Failed to find a suitable article to post.")
        return False

    post_text = format_post(article)

    if dry_run:
        logger.info("Dry-run enabled. Post not submitted.")
        logger.info(f"Post preview:\n{post_text}")
        if article.get('thumbnail_url'):
            logger.info(f"Thumbnail: {article['thumbnail_url']}")

        return True

    entry = make_history_entry(article)
    entry['buffer_submission'] = 'pending'
    entry['buffer_post_id'] = None
    history.append(entry)
    save_history(history_path, history)
    post_id = post_to_buffer(config, post_text, article.get('thumbnail_url'))
    entry['buffer_post_id'] = post_id or None
    entry['buffer_submission'] = 'accepted' if post_id else 'failed_or_unknown'
    save_history(history_path, prune_history(history, history_days))
    if post_id and os.getenv('VERIFY_DELIVERY', '').lower() == 'true':
        delivery = verify_buffer_post(config, post_id)
        entry['buffer_delivery_status'] = delivery.get('status', 'unknown')
        entry['published_url'] = delivery.get('externalLink')
        entry['published_at'] = delivery.get('sentAt')
        save_history(history_path, prune_history(history, history_days))
        if delivery.get('status') != 'sent' or delivery.get('error'):
            logger.error('Buffer accepted the post but delivery is not confirmed; do not resubmit')
            return False
    return bool(post_id)


def main():
    """Run one cycle; the hosted scheduler supplies the recurring loop."""
    parser = argparse.ArgumentParser(description='Publish a Wikipedia article through Buffer.')
    parser.add_argument('--dry-run', action='store_true', help='Preview without publishing or changing history')
    args = parser.parse_args()
    config = load_config(require_credentials=not args.dry_run)
    sys.exit(0 if run_bot_once(config, dry_run=args.dry_run) else 1)


if __name__ == '__main__':
    main()
