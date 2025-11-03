#!/usr/bin/env python3
"""
Simple tests for the bot functionality.
Tests that don't require API access.
"""

import sys
import unittest
from unittest.mock import Mock, patch
import bot


class TestBotFunctions(unittest.TestCase):
    """Test bot functions without external API calls."""

    def test_format_tweet_normal(self):
        """Test tweet formatting with normal length article."""
        article = {
            'title': 'Test Article',
            'url': 'https://tr.wikipedia.org/wiki/Test',
            'extract': 'Some description'
        }
        tweet = bot.format_tweet(article)
        
        self.assertIn('Test Article', tweet)
        self.assertIn('https://tr.wikipedia.org/wiki/Test', tweet)
        self.assertLessEqual(len(tweet), 280)

    def test_format_tweet_long_title(self):
        """Test tweet formatting with very long title."""
        article = {
            'title': 'A' * 300,  # Very long title
            'url': 'https://tr.wikipedia.org/wiki/Test',
            'extract': 'Some description'
        }
        tweet = bot.format_tweet(article)
        
        self.assertIn('https://tr.wikipedia.org/wiki/Test', tweet)
        self.assertLessEqual(len(tweet), 280)
        self.assertIn('...', tweet)  # Should be truncated

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
            'title': 'Türkiye',
            'content_urls': {
                'desktop': {
                    'page': 'https://tr.wikipedia.org/wiki/T%C3%BCrkiye'
                }
            },
            'extract': 'Türkiye description'
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        article = bot.get_random_turkish_wikipedia_article()
        
        self.assertIsNotNone(article)
        self.assertEqual(article['title'], 'Türkiye')
        self.assertIn('wikipedia.org', article['url'])

    @patch('bot.requests.get')
    def test_get_random_article_failure(self, mock_get):
        """Test article fetch failure handling."""
        mock_get.side_effect = Exception("Network error")
        
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
    def test_load_config_missing_credentials(self):
        """Test configuration loading with missing credentials."""
        with self.assertRaises(SystemExit):
            bot.load_config()


if __name__ == '__main__':
    # Run tests
    unittest.main(verbosity=2)
