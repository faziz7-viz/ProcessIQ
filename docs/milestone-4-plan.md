# Milestone 4: AI Interview and Structured Extraction

Approved scope: live OpenAI interview, validated extraction, and handoff to existing
review/calculation screens. No generated findings/recommendations or Milestone 5.

- `prompts.py`: scoped interview/extraction instructions, no financial calculations.
- `llm.py`: simple all-required transport models and OpenAI Responses structured
  output adapter. Default gpt-5-mini, environment override, 30-second timeout,
  one retry for transient API errors, no provider exception details shown to owner.
- `interview.py`: immutable conversation state, application-owned source messages,
  validation of quotes and explicit numeric support, forced unconfirmed drafts,
  missing-field follow-up selection, unknown/skip handling, six-turn limit, and
  atomic failure handling. Model cannot submit source messages or confirmation.
- `app.py`: choose live AI or existing synthetic examples, explicit submit-only API
  calls, recorded conversation, graceful config/error messages, early review handoff.
- Natural language can yield workflow=null while boundaries/steps are unclear;
  follow-up asks for process details. Missing numeric information stays None.
- Sources and numbers require validation; numeric literals must appear in source
  quotes. No inferred labor rates, default staffing, financial guesses, unit
  conversion, or fabricated source text. Semantic accuracy still needs owner review.
- API key read only from environment or ProcessIQ/.env, never displayed, logged,
  or copied from unrelated projects. Add .env.example with placeholders.
- Mock HTTP at the provider boundary; test actual OpenAI SDK request serialization,
  error/redaction/refusal handling, malformed response, unsupported numbers/units,
  source grounding, count/decimal safety, caps, skip, correction, and UI handoff.
- Live synthetic smoke test only if a ProcessIQ API key is available; otherwise
  document it as unverified and provide an opt-in command for later verification.

## Verification and review
- Offline suite: 152 passing cases; one opt-in real API test is skipped by default.
- Focused review identified clarification questions being discarded for filled
  fields and source hours being accepted as minutes. Regression tests reproduced
  both; the controller now permits valid scope/known-field clarifications and
  requires explicit supporting units in source quotes.
- Additional tests verify full-schema SDK parsing, latest corrections, populated
  draft preservation, and one-retry/two-attempt behavior through real SDK HTTP.
- Project configuration was prepared in ignored .env without overwriting existing
  contents. The owner configured a project API key and authorized live verification.
  The opt-in synthetic test passed against the real API on October 8, 2026
  (1 passed in 13.80 seconds). Regular suite rerun: 152 passed, 1 opt-in skipped.
- No Milestone 5 work has started.

- Configuration is reread per submission without caching a blank key in the
  process environment; configuring the project .env does not require a restart.

## Status

Milestone 4 implementation and live synthetic smoke verification are complete.
The live test validates one explicit synthetic workflow, not all possible owner
descriptions. Milestone 5 remains awaiting owner approval.
