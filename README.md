# Wikipedia to X

[![Tests](https://github.com/ehenden/wikipedia-to-x/actions/workflows/tests.yml/badge.svg)](https://github.com/ehenden/wikipedia-to-x/actions/workflows/tests.yml)
[![Publish](https://github.com/ehenden/wikipedia-to-x/actions/workflows/post-once.yml/badge.svg)](https://github.com/ehenden/wikipedia-to-x/actions/workflows/post-once.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A small Python bot that selects a Wikipedia article and publishes its title,
short summary, source link, and image to X through Buffer.

**Live account:** [@RastgeleWiki](https://x.com/RastgeleWiki)

```text
GitHub Actions schedule → Wikipedia → Buffer → X
                         ↕
                 JSON history on bot-state
```

Each run processes at most one article and exits. GitHub Actions checks every five
minutes; publication history enforces at least 30 minutes between submissions.
The optional hosted continuation also dispatches the next cycle directly when due,
so regular operation does not depend only on cron. GitHub runner outages or delays
can still affect timing;
no personal computer, agent, web server, or database needs to stay running.

## Selection

- **popular** — samples recent Wikipedia pageview rankings, with random fallback.
- **random** — samples articles from the selected language edition.
- **category** — samples direct members of a chosen category, for a focused topic
  such as history. It does not traverse subcategories or fall back to unrelated topics.

Selection filters out repeated articles, disambiguation pages, and pages without
usable summaries or images. Topic overlap is a simple heuristic. History is kept
per language for 60 days; failed or uncertain Buffer submissions are also reserved
to reduce duplicate posting. Popularity reflects Wikipedia views, not live news
or X trends. By default, summaries come directly from Wikipedia. The optional
`AI_SUMMARY_RUNNER` Actions variable supplies a private summary entrypoint and uses
the `OPENROUTER_API_KEY` secret; forks do not need either.
If the private AI entrypoint cannot produce a valid summary, it uses the original
Wikipedia extract instead. AI quota or summary failures therefore do not stop publishing.

## Run your own

1. Fork this repository and enable GitHub Actions.
2. Connect your X account to Buffer and create a Buffer API key.
3. Add Actions secrets `BUFFER_API_KEY` and `BUFFER_CHANNEL_ID`.
4. Run **Publish Wikipedia** with `dry_run` checked to preview, then let the schedule run.

Configure these under **Settings → Secrets and variables → Actions → Variables**:

| Variable | Default | Purpose |
| --- | --- | --- |
| `WIKI_LANGUAGE` | `tr` | Wikipedia edition, e.g. `en`, `de`, `ja` |
| `ARTICLE_SOURCE` | `popular` | `popular`, `random`, or `category` |
| `WIKI_CATEGORY` | empty | Required in category mode; full title with `Category:` prefix |
| `HISTORY_DAYS` | `60` | Article repeat avoidance window |
| `TOPIC_DAYS` | `14` | Topic overlap window; `0` disables it |
| `RN_MINSIZE` | `8000` | Minimum size for random candidate queries |
| `POST_INTERVAL` | `1800` | Minimum seconds between Buffer submissions |
| `CONTINUOUS_PUBLISHING` | unset | Set to `true` to allow hosted continuation |

For English physics articles, set `WIKI_LANGUAGE=en`, `ARTICLE_SOURCE=category`,
and `WIKI_CATEGORY=Category:Physics`. Choose an existing category in your edition
for history or another topic. Change the cron in
[post-once.yml](.github/workflows/post-once.yml) to adjust frequency.

To start hosted continuation, set `CONTINUOUS_PUBLISHING=true` and run the workflow
with `keep_running=true`. Each cycle dispatches one successor; a separate job waits
until the interval is due. Disable the variable and cancel the waiting run to stop
continuation. Disable the workflow to pause both continuation and cron publishing.
This occupies one hosted runner while waiting; review Actions usage before enabling
it on a private repository. The live account's repository is public.

## Local development

Python 3.11 or newer; two dependencies: `requests` and `python-dotenv`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py --dry-run
python -m unittest -q
```

Dry runs need no Buffer credentials and do not change history. `python bot.py`
publishes one article using credentials from `.env` or the environment.

## Operations

Actions restores and saves `.bot_state/history.json` on the `bot-state` branch.
Before submitting to Buffer, it persists a pending reservation on that branch.
A failed reservation write blocks publishing; interrupted or uncertain provider
calls remain reserved across runners.
Actions reads the accepted post back from Buffer and records its delivery status,
publication time, and external link in history. Acceptance alone is not counted
as confirmed delivery; pending or failed delivery needs attention in Actions.
Publishing requests are not retried automatically after an uncertain response.

The hosted setup can run within free service allowances, subject to current
Buffer, X, and GitHub policies. Schedules may be delayed; inactive repositories
can have schedules disabled. Successful history commits keep the repository active,
but extended failures or exhausted content require attention in Actions.

Code: [MIT](LICENSE). Wikipedia text and media retain their source licenses;
follow the linked article and image pages for attribution and reuse terms.
