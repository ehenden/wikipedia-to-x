#!/usr/bin/env python3
"""
Simple tests for the bot functionality.
Tests that don't require API access.
"""

import unittest
import tempfile
from unittest.mock import Mock, patch
import requests
import bot


class TestBotFunctions(unittest.TestCase):
    """Test bot functions without external API calls."""

    def make_twitter_exception(self, message, status_code=None, headers=None, body=None):
        exc = bot.tweepy.TweepyException(message)
        if status_code is not None:
            response = Mock()
            response.status_code = status_code
            response.text = body or message
            response.headers = headers or {}
            exc.response = response
        exc.api_errors = []
        exc.errors = None
        return exc

    @patch('bot.requests.post')
    def test_buffer_acceptance_with_image_and_url(self, post):
        post.return_value.json.return_value = {'data': {'createPost': {
            '__typename': 'PostActionSuccess', 'post': {'id': 'post-123'},
        }}}
        config = {'buffer_api_key': 'test-key', 'buffer_channel_id': 'channel-123'}
        result = bot.post_to_buffer(config, 'Wiki https://tr.wikipedia.org/wiki/Test',
                                    'https://example.org/image.jpg')
        self.assertEqual(result, 'post-123')
        payload = post.call_args.kwargs['json']['variables']['input']
        self.assertEqual(payload['channelId'], 'channel-123')
        self.assertEqual(payload['mode'], 'shareNow')
        self.assertIn('https://tr.wikipedia.org', payload['text'])
        self.assertEqual(payload['assets'][0]['image']['url'], 'https://example.org/image.jpg')

    @patch('bot.requests.post')
    def test_buffer_rejection_is_not_success(self, post):
        config = {'buffer_api_key': 'test-key', 'buffer_channel_id': 'channel-123'}
        for data in [
            {'errors': [{'message': 'error'}]},
            {'data': {'createPost': {'__typename': 'PostLimitReachedError'}}},
            {'data': {'createPost': {'__typename': 'PostActionSuccess', 'post': {}}}},
        ]:
            post.return_value.json.return_value = data
            self.assertFalse(bot.post_to_buffer(config, 'Hello'))

    @patch('bot.requests.post')
    def test_buffer_timeout_is_not_retried(self, post):
        post.side_effect = requests.exceptions.Timeout()
        self.assertFalse(bot.post_to_buffer(
            {'buffer_api_key': 'test-key', 'buffer_channel_id': 'channel-123'}, 'Hello'))
        self.assertEqual(post.call_count, 1)

    @patch('bot.post_to_buffer', return_value=False)
    @patch('bot.get_trending_article')
    def test_uncertain_buffer_submission_is_reserved_in_history(self, fetch, publish):
        fetch.return_value = {
            'title': 'Test', 'url': 'https://tr.wikipedia.org/wiki/Test',
            'extract': 'Example', 'pageid': 1,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = directory + '/history.json'
            with patch.dict('os.environ', {'HISTORY_FILE': path}):
                self.assertFalse(bot.run_bot_once(None, None, config={'publish_provider': 'buffer'}))
                entries = bot.load_history(path)
        self.assertEqual(entries[0]['buffer_submission'], 'failed_or_unknown')
        self.assertIsNone(entries[0]['buffer_post_id'])

    @patch('bot.load_dotenv')
    @patch.dict('os.environ', {
        'PUBLISH_PROVIDER': 'buffer', 'BUFFER_API_KEY': 'test-key',
        'BUFFER_CHANNEL_ID': 'channel-123',
    }, clear=True)
    def test_buffer_does_not_require_twitter_keys(self, _dotenv):
        self.assertEqual(bot.load_config()['publish_provider'], 'buffer')

    def test_format_tweet_normal(self):
        """Test tweet formatting with normal length article."""
        article = {
            'title': 'Test Article',
            'url': 'https://tr.wikipedia.org/wiki/Test',
            'extract': 'Some description'
        }
        tweet = bot.format_tweet(article)

        self.assertIn('Test Article', tweet)
        self.assertIn('Some description', tweet)
        self.assertIn('https://tr.wikipedia.org/wiki/Test', tweet)
        self.assertLessEqual(len(tweet), 280)

    def test_format_tweet_long_extract(self):
        """Test tweet formatting with very long extract."""
        article = {
            'title': 'Test Article',
            'url': 'https://tr.wikipedia.org/wiki/Test',
            'extract': 'A' * 600
        }
        tweet = bot.format_tweet(article)

        self.assertIn('https://tr.wikipedia.org/wiki/Test', tweet)
        self.assertLessEqual(len(tweet), 280)
        self.assertIn('...', tweet)

    def test_format_tweet_contains_url(self):
        """Test that formatted tweet contains the URL."""
        article = {
            'title': 'Short Title',
            'url': 'https://tr.wikipedia.org/wiki/Page',
            'extract': 'Description'
        }
        tweet = bot.format_tweet(article)

        self.assertIn('https://tr.wikipedia.org/wiki/Page', tweet)

    @patch('bot.requests.get')
    def test_get_random_article_success(self, mock_get):
        """Test successful article fetch."""
        mock_response = Mock()
        mock_response.json.return_value = {
            'title': 'Turkiye',
            'content_urls': {
                'desktop': {
                    'page': 'https://tr.wikipedia.org/wiki/T%C3%BCrkiye'
                }
            },
            'extract': 'Turkiye description'
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        article = bot.get_random_turkish_wikipedia_article()

        self.assertIsNotNone(article)
        self.assertEqual(article['title'], 'Turkiye')
        self.assertIn('wikipedia.org', article['url'])

    @patch('bot.requests.get')
    def test_get_random_article_failure(self, mock_get):
        """Test article fetch failure handling."""
        mock_get.side_effect = requests.exceptions.RequestException("Network error")

        article = bot.get_random_turkish_wikipedia_article()

        self.assertIsNone(article)

    @patch.dict('os.environ', {
        'TWITTER_API_KEY': 'test_key',
        'TWITTER_API_SECRET': 'test_secret',
        'TWITTER_ACCESS_TOKEN': 'test_token',
        'TWITTER_ACCESS_TOKEN_SECRET': 'test_token_secret',
        'POST_INTERVAL': '3600'
    })
    def test_load_config_success(self):
        """Test successful configuration loading."""
        config = bot.load_config()

        self.assertEqual(config['api_key'], 'test_key')
        self.assertEqual(config['api_secret'], 'test_secret')
        self.assertEqual(config['access_token'], 'test_token')
        self.assertEqual(config['access_token_secret'], 'test_token_secret')
        self.assertEqual(config['post_interval'], 3600)

    @patch.dict('os.environ', {}, clear=True)
    @patch('bot.load_dotenv')
    def test_load_config_missing_credentials(self, _mock_load_dotenv):
        """Test configuration loading with missing credentials."""
        with self.assertRaises(SystemExit):
            bot.load_config()

    @patch('bot.time.sleep')
    @patch.dict('os.environ', {'X_POST_MAX_ATTEMPTS': '3'}, clear=False)
    def test_post_tweet_retries_transient_503_then_succeeds(self, mock_sleep):
        """Test transient 503 errors are retried before succeeding."""
        client = Mock()
        client.create_tweet.side_effect = [
            self.make_twitter_exception('Service Unavailable', status_code=503),
            Mock(),
        ]

        result = bot.post_tweet(client, 'Hello world')

        self.assertTrue(result)
        self.assertEqual(client.create_tweet.call_count, 2)
        mock_sleep.assert_called_once_with(5)

    @patch('bot.time.sleep')
    @patch.dict('os.environ', {'X_POST_MAX_ATTEMPTS': '3'}, clear=False)
    def test_post_tweet_does_not_retry_non_retryable_error(self, mock_sleep):
        """Test non-retryable errors fail immediately."""
        client = Mock()
        client.create_tweet.side_effect = self.make_twitter_exception(
            'Forbidden',
            status_code=403,
        )

        result = bot.post_tweet(client, 'Hello world')

        self.assertFalse(result)
        self.assertEqual(client.create_tweet.call_count, 1)
        mock_sleep.assert_not_called()

    @patch('bot.time.sleep')
    @patch.dict('os.environ', {'X_POST_MAX_ATTEMPTS': '3'}, clear=False)
    def test_post_tweet_uses_retry_after_header(self, mock_sleep):
        """Test Retry-After header overrides exponential backoff."""
        client = Mock()
        client.create_tweet.side_effect = [
            self.make_twitter_exception(
                'Too Many Requests',
                status_code=429,
                headers={'retry-after': '12'},
            ),
            Mock(),
        ]

        result = bot.post_tweet(client, 'Hello world')

        self.assertTrue(result)
        self.assertEqual(client.create_tweet.call_count, 2)
        mock_sleep.assert_called_once_with(12.0)


if __name__ == '__main__':
    # Run tests
    unittest.main(verbosity=2)
