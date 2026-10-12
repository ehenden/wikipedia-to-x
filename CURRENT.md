# Current state

## Publication recovery, 2026-10-12

- Audit: scheduled run `38297022301` failed before Buffer because AI summaries
  weighed 259 and 225 against the 210 maximum. Last accepted post was at
  2026-10-11 22:44 UTC; only two scheduled runs occurred during the following day.
- The workflow was active and Actions enabled. The previous cron configuration
  did not prove actual half-hourly execution; the trigger gap remains provider-side.
- Scheduler: check every five minutes, with `POST_INTERVAL=1800` enforced from
  restored history before any selection or AI request. Missed runs do not create
  catch-up bursts. GitHub schedules remain best-effort, not an exact-time guarantee.
- Private AI overlay: preserve the free model and bounded attempts, but fall back
  to the original Wikipedia extract on invalid output, quota exhaustion or errors.
- Write a pending history reservation before the publishing mutation. Accepted,
  pending and uncertain submissions all enforce the interval; no blind resubmission.
- Actions enables read-only Buffer delivery checks. History records sent status,
  timestamp and destination URL; delivery failures are not silently treated as success.
- Local validation: 34 mocked tests passed, including seven private-overlay checks.
- Deployed code: `7e81c8a`; private summary overlay updated and read back.
- Hosted Tests run `38298160738`: 27 repository tests passed.
- Real publication run `38298296057`: succeeded. Buffer post
  `6acd35c6ebe016d7f5fd1f8c` was read back as `sent` at 2026-10-12 19:32:23 UTC.
  Destination: https://twitter.com/RastgeleWiki/status/2109728907960230266
- Scheduler deployment: workflow commit `6036a7c` was saved through the signed-in
  GitHub browser because CLI OAuth lacks `workflow` scope. The hosted file was
  read back and matched the prepared workflow; the local checkout was fast-forwarded.
- The workflow was explicitly enabled via API. Hosted cron is now `2/5 * * * *`;
  `POST_INTERVAL=1800` and `VERIFY_DELIVERY=true` are passed to the bot.
- Duplicate-prevention run `38298411768` succeeded: it skipped before selection,
  AI or Buffer calls, and hosted history SHA stayed
  `a502fc679f6a9c8047319332dc46ccf0c76d249b`.
- Hosted continuation: `26aaf98` adds an opt-in `next_cycle` job. The publication
  job emits a delay computed from actual history; the waiting job dispatches one
  successor with the repository's ephemeral `GITHUB_TOKEN` (`actions: write`).
  A separate concurrency group bounds waiting jobs. Cron remains a backup.
- `CONTINUOUS_PUBLISHING=true` is enabled. Root run `38300070763` was dispatched
  with `keep_running=true`; its publication job passed and its next-cycle timer started.
- Final local tests: 41 passed (34 repository, seven private-overlay). Automatic
  successor publication is confirmed below. Hosted Tests run `38300824442`: 34 passed.
- Reservation hardening: `8d6e797` plus workflow `91f3d56` persist pending state
  to GitHub before Buffer submission. History failures block the mutation.
- Large history support: `b882e26` uses GitHub's object/raw media types so the
  60-day history can grow past the 1 MB inline-content limit at this publication rate.
- To stop continuation, set `CONTINUOUS_PUBLISHING=false` and cancel the waiting
  run. Disable the workflow to pause both cron and continuation. Waiting uses one
  standard GitHub-hosted Ubuntu runner; this repository is public.
- Automatic continuation proof: root `38300070763` completed successfully and
  dispatched `38301617977` at 2026-10-12 20:02:31 UTC. The successor's actor and
  triggering actor are both `github-actions[bot]`, and its publication job passed.
- The successor published "Radin Inten II Uluslararası Havalimanı" at 20:02:49 UTC;
  Buffer post `6acd3ce8f5c35b68cbfc9900` was read back as `sent`.
  Destination: https://twitter.com/RastgeleWiki/status/2109736566323093876
- Real publications were 30 minutes 26 seconds apart. The successor's waiting job
  started with a 1794-second delay; the next target is around 20:32 UTC (23:32 Istanbul).
  This is confirmed continuation behavior, not a guarantee against GitHub/Buffer/X outages.

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
