#!/usr/bin/env python3
"""
X Random Wikipedia Bot
A bot that posts random Turkish Wikipedia article links to X (Twitter).
"""

import os
import sys
import time
import logging
import requests
import tweepy
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_config():
    """Load configuration from environment variables."""
    load_dotenv()
    
    config = {
        'api_key': os.getenv('TWITTER_API_KEY'),
        'api_secret': os.getenv('TWITTER_API_SECRET'),
        'access_token': os.getenv('TWITTER_ACCESS_TOKEN'),
        'access_token_secret': os.getenv('TWITTER_ACCESS_TOKEN_SECRET'),
        'post_interval': int(os.getenv('POST_INTERVAL', 3600))
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
    Fetch a random Turkish Wikipedia article using the Wikipedia API.
    
    Returns:
        dict: Article information containing title and URL, or None if error occurs.
    """
    api_url = "https://tr.wikipedia.org/api/rest_v1/page/random/summary"
    
    try:
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        article = {
            'title': data.get('title', 'Unknown Title'),
            'url': data.get('content_urls', {}).get('desktop', {}).get('page', ''),
            'extract': data.get('extract', '')
        }
        
        logger.info(f"Fetched article: {article['title']}")
        return article
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching Wikipedia article: {e}")
        return None


def format_tweet(article):
    """
    Format a tweet with the article information.
    
    Args:
        article (dict): Article information containing title and URL.
    
    Returns:
        str: Formatted tweet text.
    """
    # Simple format: title and URL
    # Twitter will automatically create a preview card for the URL
    tweet = f"{article['title']}\n\n{article['url']}"
    
    # Ensure tweet doesn't exceed Twitter's character limit (280)
    if len(tweet) > 280:
        # Truncate title to fit
        max_title_length = 280 - len(article['url']) - 5  # 5 for newlines and ellipsis
        truncated_title = article['title'][:max_title_length] + "..."
        tweet = f"{truncated_title}\n\n{article['url']}"
    
    return tweet


def create_twitter_client(config):
    """
    Create and authenticate Twitter API client.
    
    Args:
        config (dict): Configuration containing API credentials.
    
    Returns:
        tweepy.Client: Authenticated Twitter API client.
    """
    try:
        client = tweepy.Client(
            consumer_key=config['api_key'],
            consumer_secret=config['api_secret'],
            access_token=config['access_token'],
            access_token_secret=config['access_token_secret']
        )
        logger.info("Successfully authenticated with X API")
        return client
    except Exception as e:
        logger.error(f"Error creating Twitter client: {e}")
        sys.exit(1)


def post_tweet(client, tweet_text):
    """
    Post a tweet to X (Twitter).
    
    Args:
        client (tweepy.Client): Authenticated Twitter API client.
        tweet_text (str): The text to tweet.
    
    Returns:
        bool: True if successful, False otherwise.
    """
    try:
        response = client.create_tweet(text=tweet_text)
        logger.info(f"Successfully posted tweet: {tweet_text[:50]}...")
        return True
    except tweepy.TweepyException as e:
        logger.error(f"Error posting tweet: {e}")
        return False


def run_bot_once(client):
    """
    Run the bot once: fetch an article and post it.
    
    Args:
        client (tweepy.Client): Authenticated Twitter API client.
    
    Returns:
        bool: True if successful, False otherwise.
    """
    # Fetch random article
    article = get_random_turkish_wikipedia_article()
    if not article or not article['url']:
        logger.error("Failed to fetch article or article has no URL")
        return False
    
    # Format tweet
    tweet_text = format_tweet(article)
    
    # Post tweet
    return post_tweet(client, tweet_text)


def run_bot_loop(config):
    """
    Run the bot in a continuous loop, posting at scheduled intervals.
    
    Args:
        config (dict): Configuration containing API credentials and settings.
    """
    client = create_twitter_client(config)
    
    logger.info(f"Bot started. Will post every {config['post_interval']} seconds.")
    logger.info("Press Ctrl+C to stop.")
    
    try:
        while True:
            success = run_bot_once(client)
            
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
        client = create_twitter_client(config)
        success = run_bot_once(client)
        sys.exit(0 if success else 1)
    else:
        # Run in continuous loop
        run_bot_loop(config)


if __name__ == "__main__":
    main()
