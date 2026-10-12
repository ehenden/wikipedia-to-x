# Current state

Verified on 2026-10-12 against GitHub main `309c46b` and Actions run `38231869184`.

- Repository: `ehenden/wikipedia-to-x` (renamed from `X-Random-Wikipedia-Bot`).
- One publication cycle per invocation, through Buffer; Actions runs every 30 minutes.
- Hosted selection uses Turkish Wikipedia, random mode, `RN_MINSIZE=5000`,
  `HISTORY_DAYS=60`, and `TOPIC_DAYS=60`.
- Article history is restored and saved on the `bot-state` branch.
- The account uses an optional private `AI_SUMMARY_RUNNER` Actions variable;
  AI calls are free-model-only and quota-aware, with at most two attempts per cycle.
- The latest failed run stopped before Buffer submission: summary weights 283 and
  271 exceeded the 140–210 budget. The Unicode counter overcounted Turkish letters,
  and the private prompt used that incorrect counting rule.
- Fix: follow twitter-text v3 single-weight Unicode ranges, preserve conservative
  counting for emoji sequences, and align the private prompt with the summary budget.
- Provider acceptance is separate from confirmed delivery on X. Dry-run validation
  must neither submit to Buffer nor change publication history.
