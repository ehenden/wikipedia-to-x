"""Persist actual article history on a separate branch between Actions runs."""
import base64
import json
import os
from pathlib import Path
import sys

import requests


def sync_history(mode):
    path = Path('.bot_state/history.json')
    session = requests.Session()
    session.headers.update({
        'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    })
    root = 'https://api.github.com/repos/' + os.environ['GITHUB_REPOSITORY']
    url = root + '/contents/.bot_state/history.json'
    response = session.get(url, params={'ref': 'bot-state'}, timeout=30)
    if response.status_code == 404:
        remote = None
    else:
        response.raise_for_status()
        remote = response.json()
    if mode == 'restore':
        content = base64.b64decode(remote['content']) if remote else b'[]\n'
        if not isinstance(json.loads(content), list):
            raise ValueError('History must be a list')
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(content)
        return
    if not path.exists():
        return
    content = path.read_bytes()
    if not isinstance(json.loads(content), list):
        raise ValueError('History must be a list')
    if remote and base64.b64decode(remote['content']) == content:
        return
    if not remote:
        branch = session.get(root + '/git/ref/heads/bot-state', timeout=30)
        if branch.status_code == 404:
            created = session.post(root + '/git/refs', json={
                'ref': 'refs/heads/bot-state', 'sha': os.environ['GITHUB_SHA'],
            }, timeout=30)
            created.raise_for_status()
        else:
            branch.raise_for_status()
    payload = {
        'message': 'Record Wikipedia publication history',
        'content': base64.b64encode(content).decode(),
        'branch': 'bot-state',
    }
    if remote:
        payload['sha'] = remote['sha']
    saved = session.put(url, json=payload, timeout=30)
    saved.raise_for_status()
    print('Article history persisted on bot-state branch')


if __name__ == '__main__':
    if len(sys.argv) != 2 or sys.argv[1] not in {'restore', 'save'}:
        sys.exit('Usage: github_state.py restore|save')
    try:
        sync_history(sys.argv[1])
    except (requests.RequestException, ValueError, KeyError):
        sys.exit('History synchronization failed; inspect Actions and bot-state')
