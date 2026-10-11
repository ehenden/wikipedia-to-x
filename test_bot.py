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
                self.assertFalse(bot.run_bot_once({}))
                entries = bot.load_history(path)
        self.assertEqual(entries[0]['buffer_submission'], 'failed_or_unknown')
        self.assertIsNone(entries[0]['buffer_post_id'])

    @patch('bot.load_dotenv')
    @patch.dict('os.environ', {
        'BUFFER_API_KEY': 'test-key',
        'BUFFER_CHANNEL_ID': 'channel-123',
    }, clear=True)
    def test_buffer_does_not_require_twitter_keys(self, _dotenv):
        self.assertEqual(bot.load_config()['buffer_channel_id'], 'channel-123')

    @patch('bot.load_dotenv')
    def test_selection_configuration_validation(self, _dotenv):
        with patch.dict('os.environ', {'WIKI_LANGUAGE': 'en', 'ARTICLE_SOURCE': 'category',
                                      'WIKI_CATEGORY': 'Category:Physics'}, clear=True):
            self.assertEqual(bot.load_config(False)['wiki_language'], 'en')
            self.assertEqual(bot.wikipedia_url('/w/api.php'), 'https://en.wikipedia.org/w/api.php')
        for values in [{'WIKI_LANGUAGE': 'en/invalid'}, {'ARTICLE_SOURCE': 'invalid'},
                       {'ARTICLE_SOURCE': 'category', 'WIKI_CATEGORY': ''}]:
            with patch.dict('os.environ', values, clear=True):
                with self.assertRaises(ValueError):
                    bot.load_config(False)

    def test_history_is_language_scoped_and_legacy_is_turkish(self):
        entries = [{'pageid': 1, 'title': 'Legacy'},
                   {'pageid': 2, 'title': 'English', 'wiki_language': 'en'}]
        with patch.dict('os.environ', {'WIKI_LANGUAGE': 'en'}):
            self.assertEqual(bot.build_history_indexes(entries, 14)[1], {2})
        with patch.dict('os.environ', {'WIKI_LANGUAGE': 'tr'}):
            self.assertEqual(bot.build_history_indexes(entries, 14)[1], {1})

    @patch('bot.get_page_details_by_pageids', return_value=[])
    @patch('bot.requests.get')
    def test_category_pagination_stays_bounded(self, get, details):
        get.return_value.json.return_value = {
            'query': {'categorymembers': [{'pageid': 5, 'title': 'Example'}]},
            'continue': {'cmcontinue': 'next', 'continue': '-||'},
        }
        self.assertIsNone(bot.get_category_article('Category:Physics', set(), set(), set()))
        self.assertEqual(get.call_count, 3)
        self.assertEqual(get.call_args.kwargs['params']['cmnamespace'], 0)
        self.assertEqual(get.call_args.kwargs['params']['cmcontinue'], 'next')
        details.assert_called_once()

    @patch('bot.get_random_article')
    @patch('bot.get_filtered_random_article')
    @patch('bot.get_category_article', return_value=None)
    def test_empty_category_does_not_publish_unrelated_content(self, category, random, summary):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict('os.environ', {'HISTORY_FILE': directory + '/history.json'}):
                self.assertFalse(bot.run_bot_once({'article_source': 'category',
                                                  'wiki_category': 'Category:Physics'}, True))
        random.assert_not_called()
        summary.assert_not_called()

    @patch('bot.save_history')
    @patch('bot.post_to_buffer')
    @patch('bot.get_trending_article', return_value={
        'title': 'Preview', 'url': 'https://en.wikipedia.org/wiki/Preview', 'extract': 'Example'})
    def test_dry_run_does_not_publish_or_write_history(self, fetch, publish, save):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict('os.environ', {'HISTORY_FILE': directory + '/history.json'}):
                self.assertTrue(bot.run_bot_once({}, True))
        publish.assert_not_called()
        save.assert_not_called()

    @patch('bot.get_trending_article')
    @patch('bot.get_filtered_random_article', return_value={
        'title': 'Random', 'url': 'https://en.wikipedia.org/wiki/Random'})
    def test_random_mode_skips_pageview_query(self, random, popular):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict('os.environ', {'HISTORY_FILE': directory + '/history.json'}):
                self.assertTrue(bot.run_bot_once({'article_source': 'random'}, True))
        popular.assert_not_called()

    def test_cjk_post_preserves_long_source_and_stays_within_weight_limit(self):
        url = 'https://ja.wikipedia.org/wiki/' + '%E6%AD%B4' * 100
        post = bot.format_post({'title': '歴史' * 200, 'extract': '世界' * 300, 'url': url})
        body, source = post.rsplit('\n\n', 1)
        self.assertEqual(source, url)
        # Independent conservative count; CJK characters weigh two on X.
        self.assertLessEqual(sum(1 if ord(c) < 128 else 2 for c in body) + 2 + 23, 280)

    def test_format_post_normal(self):
        """Test tweet formatting with normal length article."""
        article = {
            'title': 'Test Article',
            'url': 'https://tr.wikipedia.org/wiki/Test',
            'extract': 'Some description'
        }
        tweet = bot.format_post(article)

        self.assertIn('Test Article', tweet)
        self.assertIn('Some description', tweet)
        self.assertIn('https://tr.wikipedia.org/wiki/Test', tweet)
        self.assertLessEqual(len(tweet.rsplit('\n\n', 1)[0]) + 2 + 23, 280)

    def test_format_post_long_extract(self):
        """Test tweet formatting with very long extract."""
        article = {
            'title': 'Test Article',
            'url': 'https://tr.wikipedia.org/wiki/Test',
            'extract': 'A' * 600
        }
        tweet = bot.format_post(article)

        self.assertIn('https://tr.wikipedia.org/wiki/Test', tweet)
        self.assertLessEqual(len(tweet.rsplit('\n\n', 1)[0]) + 2 + 23, 280)
        self.assertIn('...', tweet)

    def test_format_post_contains_url(self):
        """Test that formatted tweet contains the URL."""
        article = {
            'title': 'Short Title',
            'url': 'https://tr.wikipedia.org/wiki/Page',
            'extract': 'Description'
        }
        tweet = bot.format_post(article)

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

        article = bot.get_random_article()

        self.assertIsNotNone(article)
        self.assertEqual(article['title'], 'Turkiye')
        self.assertIn('wikipedia.org', article['url'])

    @patch('bot.requests.get')
    def test_get_random_article_failure(self, mock_get):
        """Test article fetch failure handling."""
        mock_get.side_effect = requests.exceptions.RequestException("Network error")

        article = bot.get_random_article()

        self.assertIsNone(article)


    @patch.dict('os.environ', {}, clear=True)
    @patch('bot.load_dotenv')
    def test_load_config_missing_credentials(self, _mock_load_dotenv):
        """Test configuration loading with missing credentials."""
        with self.assertRaises(SystemExit):
            bot.load_config()

if __name__ == '__main__':
    # Run tests
    unittest.main(verbosity=2)
