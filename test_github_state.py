"""History transport regression checks; all network and filesystem calls are mocked."""
import base64
import os
import unittest
from unittest.mock import Mock, patch

import requests
from scripts import github_state


@patch.dict(os.environ, {'GH_TOKEN': 'test-token', 'GITHUB_REPOSITORY': 'example/wiki'})
class TestGithubState(unittest.TestCase):
    def setUp(self):
        self.session = Mock()
        self.path = Mock()
        for target, value in [('requests.Session', self.session), ('Path', self.path)]:
            patcher = patch('scripts.github_state.' + target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def response(self, metadata):
        response = Mock(status_code=200)
        response.json.return_value = metadata
        return response

    def test_inline_history_restore(self):
        self.session.get.return_value = self.response({
            'sha': 'file-sha', 'encoding': 'base64',
            'content': base64.b64encode(b'[{"title":"Example"}]').decode()})
        github_state.sync_history('restore')
        self.path.write_bytes.assert_called_once_with(b'[{"title":"Example"}]')
        self.session.get.assert_called_once()

    def test_large_history_uses_raw_content(self):
        raw = Mock(status_code=200, content=b'[{"title":"Example"}]')
        self.session.get.side_effect = [self.response({
            'sha': 'large-file-sha', 'size': 2_000_000, 'encoding': 'none', 'content': ''}), raw]
        github_state.sync_history('restore')
        self.path.write_bytes.assert_called_once_with(raw.content)
        self.assertEqual(self.session.get.call_args.kwargs['headers']['Accept'],
                         'application/vnd.github.raw+json')

    def test_unchanged_large_history_is_not_rewritten(self):
        raw = Mock(status_code=200, content=b'[{}]\n')
        self.session.get.side_effect = [self.response({
            'sha': 'large-file-sha', 'encoding': 'none', 'content': ''}), raw]
        self.path.read_bytes.return_value = raw.content
        github_state.sync_history('save')
        self.session.put.assert_not_called()

    def test_failed_raw_download_does_not_overwrite_history(self):
        raw = Mock(status_code=500)
        raw.raise_for_status.side_effect = requests.HTTPError()
        self.session.get.side_effect = [self.response({
            'sha': 'large-file-sha', 'encoding': 'none', 'content': ''}), raw]
        with self.assertRaises(requests.HTTPError):
            github_state.sync_history('restore')
        self.path.write_bytes.assert_not_called()
