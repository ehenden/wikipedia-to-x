# Current state

## Publication recovery, 2026-10-12

- Audit: scheduled run `38297022301` failed before Buffer because AI summaries
  weighed 259 and 225 against the 210 maximum. Last accepted post was at
  2026-10-11 22:44 UTC; only two scheduled runs occurred during the following day.
- The workflow was active and Actions enabled. The previous cron configuration
  did not prove actual half-hourly execution; the trigger gap remains provider-side.
- Recovery: check every five minutes, with `POST_INTERVAL=1800` enforced from
  restored history before any selection or AI request. Missed runs do not create
  catch-up bursts. GitHub schedules remain best-effort, not an exact-time guarantee.
- Private AI overlay: preserve the free model and bounded attempts, but fall back
  to the original Wikipedia extract on invalid output, quota exhaustion or errors.
- Write a pending history reservation before the publishing mutation. Accepted,
  pending and uncertain submissions all enforce the interval; no blind resubmission.
- Actions enables read-only Buffer delivery checks. History records sent status,
  timestamp and destination URL; delivery failures are not silently treated as success.
- Local validation: 34 mocked tests passed, including seven private-overlay checks.

## Previous audit

Audited on 2026-10-12 against GitHub main `309c46b` and Actions run `38231869184`.
The code fix is committed in `e819c3b`; the private summary variable was updated
and its content read back to confirm the update.

- Repository: `ehenden/wikipedia-to-x` (renamed from `X-Random-Wikipedia-Bot`).
- One publication cycle per invocation, through Buffer; Actions runs every 30 minutes.
- Hosted selection uses Turkish Wikipedia, random mode, `RN_MINSIZE=5000`,
  `HISTORY_DAYS=60`, and `TOPIC_DAYS=60`.
- Article history is restored and saved on the `bot-state` branch.
- The account uses an optional private `AI_SUMMARY_RUNNER` Actions variable;
  AI calls are free-model-only and quota-aware, with at most two attempts per cycle.
- The reported failed run stopped before Buffer submission: summary weights 283 and
  271 exceeded the 140–210 budget. The Unicode counter overcounted Turkish letters,
  and the private prompt used that incorrect counting rule.
- Fix: follow twitter-text v3 single-weight Unicode ranges, preserve conservative
  counting for emoji sequences, and align the private prompt with the summary budget.
- Provider acceptance is separate from confirmed delivery on X. Dry-run validation
  must neither submit to Buffer nor change publication history.

## Validation

- Local: 26 mocked unit tests passed, including five private-overlay regression checks.
- GitHub Tests run `38232647976`: all 21 repository tests passed.
- Publish Wikipedia dry-run `38232670278`: successful on the first AI attempt;
  summary weight 162 within 140–210, complete post weight 199/280.
- Hosted history SHA stayed `12c861d3f7c8e1e170957c4a9d23072c8c55599e` across the
  dry-run. No Buffer submission or X delivery was tested by this validation.
