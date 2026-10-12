# Current state

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
