#!/usr/bin/env python3
"""
Simple tests for the bot functionality.
Tests that don't require API access.
"""

import unittest
import tempfile
from datetime import timedelta
from unittest.mock import Mock, patch
import requests
import bot


class TestBotFunctions(unittest.TestCase):
    """Test bot functions without external API calls."""

    def test_next_cycle_accounts_for_recent_submission_and_bounded_failure_delay(self):
        now = bot.utcnow()
        with patch('bot.utcnow', return_value=now):
            for minutes, expected in [(0, 1800), (10, 1200), (29.5, 60), (31, 1800)]:
                with self.subTest(minutes=minutes):
                    entry = {'timestamp': (now - timedelta(minutes=minutes)).isoformat(),
                             'buffer_submission': 'accepted'}
                    self.assertEqual(bot.next_cycle_delay([entry]), expected)
            self.assertEqual(bot.next_cycle_delay([]), 1800)
            self.assertEqual(bot.next_cycle_delay([{'timestamp': 'invalid', 'buffer_submission': 'pending'}]), 1800)

    @patch('scripts.github_state.sync_history')
    @patch('bot.post_to_buffer')
    @patch('bot.get_filtered_random_article', return_value={
        'title': 'Reserved', 'url': 'https://tr.wikipedia.org/wiki/Reserved', 'extract': 'Source'})
    def test_hosted_reservation_precedes_mutation_and_failure_blocks_publishing(self, select, publish, sync):
        with tempfile.TemporaryDirectory() as directory:
            path = directory + '/history.json'
            with patch.dict('os.environ', {'HISTORY_FILE': path, 'SYNC_HOSTED_RESERVATION': 'true'}):
                sync.side_effect = requests.Timeout()
                with self.assertRaises(requests.Timeout):
                    bot.run_bot_once({'article_source': 'random'})
                self.assertEqual(bot.load_history(path)[-1]['buffer_submission'], 'pending')
        sync.assert_called_once_with('save')
        publish.assert_not_called()

    @patch('scripts.github_state.sync_history')
    @patch('bot.post_to_buffer')
    @patch('bot.get_filtered_random_article', return_value={
        'title': 'Reserved', 'url': 'https://tr.wikipedia.org/wiki/Reserved', 'extract': 'Source'})
    def test_hosted_mutation_only_runs_after_reservation_succeeds(self, select, publish, sync):
        with tempfile.TemporaryDirectory() as directory:
            path = directory + '/history.json'
            def publish_after_sync(*args):
                sync.assert_called_once_with('save')
                self.assertEqual(bot.load_history(path)[-1]['buffer_submission'], 'pending')
                return 'reserved-post'
            publish.side_effect = publish_after_sync
            with patch.dict('os.environ', {'HISTORY_FILE': path, 'SYNC_HOSTED_RESERVATION': 'true'}):
                self.assertTrue(bot.run_bot_once({'article_source': 'random'}))
        publish.assert_called_once()

    @patch('bot.post_to_buffer')
    @patch('bot.get_filtered_random_article')
    def test_recent_submission_skips_selection_and_publishing(self, select, publish):
        with tempfile.TemporaryDirectory() as directory:
            path = directory + '/history.json'
            for status in ('accepted', 'pending', 'failed_or_unknown'):
                entry = {'timestamp': (bot.utcnow() - timedelta(minutes=29)).isoformat(),
                         'buffer_submission': status, 'wiki_language': 'tr'}
                bot.save_history(path, [entry])
                with patch.dict('os.environ', {'HISTORY_FILE': path, 'POST_INTERVAL': '1800'}):
                    self.assertTrue(bot.run_bot_once({'article_source': 'random'}))
                    self.assertEqual(bot.load_history(path), [entry])
        select.assert_not_called()
        publish.assert_not_called()

    @patch('bot.post_to_buffer', return_value='new-post')
    @patch('bot.get_filtered_random_article', return_value={
        'title': 'New', 'url': 'https://tr.wikipedia.org/wiki/New', 'extract': 'Source facts'})
    def test_elapsed_interval_publishes_once_and_reserves_before_mutation(self, select, publish):
        with tempfile.TemporaryDirectory() as directory:
            path = directory + '/history.json'
            bot.save_history(path, [{'timestamp': (bot.utcnow() - timedelta(minutes=31)).isoformat(),
                                     'buffer_submission': 'accepted'}])
            def check_reservation(*args):
                self.assertEqual(bot.load_history(path)[-1]['buffer_submission'], 'pending')
                return 'new-post'
            publish.side_effect = check_reservation
            with patch.dict('os.environ', {'HISTORY_FILE': path, 'POST_INTERVAL': '1800'}):
                self.assertTrue(bot.run_bot_once({'article_source': 'random'}))
            self.assertEqual(bot.load_history(path)[-1]['buffer_submission'], 'accepted')
        publish.assert_called_once()

    @patch('bot.post_to_buffer')
    def test_corrupt_history_blocks_publication(self, publish):
        with tempfile.TemporaryDirectory() as directory:
            path = directory + '/history.json'
            with open(path, 'w') as handle:
                handle.write('{broken')
            with patch.dict('os.environ', {'HISTORY_FILE': path}):
                with self.assertRaises(ValueError):
                    bot.run_bot_once({})
        publish.assert_not_called()

    @patch('bot.requests.post')
    def test_delivery_readback_records_sent_url(self, request):
        expected = {'id': 'post-123', 'status': 'sent', 'sentAt': '2026-10-12T19:00:00Z',
                    'externalLink': 'https://x.com/RastgeleWiki/status/123', 'error': None}
        request.return_value.json.return_value = {'data': {'post': expected}}
        self.assertEqual(bot.verify_buffer_post({'buffer_api_key': 'test-key'}, 'post-123'), expected)
        request.assert_called_once()
        self.assertNotIn('mutation', request.call_args.kwargs['json']['query'])

    @patch('bot.requests.post')
    def test_delivery_failure_never_resubmits(self, request):
        request.return_value.json.return_value = {'data': {'post': {
            'id': 'post-123', 'status': 'error', 'error': {'message': 'Disconnected'}}}}
        self.assertEqual(bot.verify_buffer_post({'buffer_api_key': 'test-key'}, 'post-123')['status'], 'error')
        request.assert_called_once()

    @patch('time.sleep')
    @patch('bot.requests.post')
    def test_pending_delivery_readback_is_bounded(self, request, sleep):
        request.return_value.json.return_value = {'data': {'post': {'status': 'sending'}}}
        self.assertEqual(bot.verify_buffer_post({'buffer_api_key': 'test-key'}, 'post-123')['status'], 'sending')
        self.assertEqual(request.call_count, 4)
        self.assertEqual(sleep.call_count, 3)

    def test_turkish_summary_uses_single_weight_characters(self):
        summary = ('Rahibe Teresa Anıt Evi, Üsküp’te bulunan bir müzedir. '
                   'Rahibe Teresa’nın yaşamını anlatan fotoğraf ve kişisel eşyalar sergilenir.')
        self.assertEqual(bot.text_weight(summary), len(summary))
        self.assertEqual(bot.truncate_text(summary, len(summary)), summary)

    def test_text_weight_unicode_ranges_and_normalization(self):
        cases = {'çğıöşüİé': 8, 'e\u0301': 1, '世界': 4, '😀': 2,
                 '\u10ff': 1, '\u1100': 2, '\u2000': 1, '\u200d': 1,
                 '\u200e': 2, '\u2010': 1, '\u201f': 1, '\u2020': 2,
                 '\u2032': 1, '\u2037': 1, '\u2038': 2}
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(bot.text_weight(text), expected)
        # Multi-codepoint emoji stay above X's actual weight, never below it.
        self.assertGreaterEqual(bot.text_weight('👨‍👩‍👧‍👦'), 2)
        self.assertEqual(bot.truncate_text('e\u0301' * 10, 6), 'ééé...')

    def test_turkish_post_preserves_summary_that_fits_x_budget(self):
        title = 'İklim değişkenliği ve değişiklikleri'
        summary = 'çğıöşü' * 35 + '.'
        url = 'https://tr.wikipedia.org/wiki/İklim_değişkenliği_ve_değişiklikleri'
        post = bot.format_post({'title': title, 'extract': summary, 'url': url})
        self.assertEqual(post, f'{title}\n\n{summary}\n\n{url}')
        self.assertLessEqual(len(title) + len(summary) + 4 + 23, 280)


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
