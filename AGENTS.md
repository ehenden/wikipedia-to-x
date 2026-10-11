# Agent Instructions

## Scope

Keep this a small, configurable Wikipedia-to-X bot. Buffer is the only publishing
provider. Each invocation runs one cycle; GitHub Actions supplies the schedule.
Defaults are Turkish Wikipedia and popular selection with random fallback.
Category mode must stay within direct category members and fail without unrelated
fallback. Preserve quality filters, language-aware history, and source attribution.

## Implementation

- Keep selection and publishing in `bot.py`; hosted history in `scripts/github_state.py`.
- Use the existing helpers and verify provider API contracts before changing payloads.
- No database, local sleep loop, browser automation, or agent runtime dependency.
- Keep dependencies limited to `requests` and `python-dotenv` unless justified.
- Read configuration from environment or ignored `.env`; document it in README and `.env.example`.
- Never log or commit credentials. Only Buffer secrets are required.
- Dry runs must neither publish nor mutate history.
- Reserve uncertain submissions in history; never blindly retry publishing mutations.
- History without a language field belongs to the original Turkish edition.
- Restore history before publishing; fail closed if hosted state cannot be read.

## Validation

Run `python -m unittest -q` after code changes. Mock external calls in unit tests.
Use `--dry-run` for live selection checks; do not publish test posts without intent.
Keep README concise and factual. Use English for code, commits, and documentation.
