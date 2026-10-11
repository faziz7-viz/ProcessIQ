# Milestone 6: Complete course demo

The original approved milestone is: README, setup instructions, reset behavior,
and a polished workflow; run the full suite and walk through both synthetic
examples, including a correction after analysis and a failed API request.
No exports, database, deployment, authentication, billing, or integrations.

## Finish-line changes

- Add qualitative suggested effort to the existing action templates/report, as
  required by the original action-plan design. No numerical effort/cost estimate.
- Clarify interview restart versus demo reset; add a way to return to the saved
  process without submitting an answer or discarding that process's pending edits.
- Add complete-path tests using the real OpenAI SDK over mocked HTTP: description,
  extraction, owner confirmation, analysis, plan, correction, recalculation,
  provider failure, and recovery. Ordinary tests spend no API usage.
- Verify both demo journeys, confirmed zero, reset, and absent/stale output.
- Write a short presentation walkthrough and architecture/module guide; rewrite
  README's introductory setup and outdated future-milestone text.

## Work sequence and verification

1. Write failing effort and interview navigation/restart tests. Implement minimal
   changes in recommendations.py, report.py, app.py; run the whole pytest suite.
2. Add end-to-end SDK/AppTest coverage. Complete demo expects $137.50/$2,750.00;
   corrected 30-minute estimate expects $126.25/$2,525.00. Incomplete demo retains
   unavailable totals with $5.00 known subtotal. HTTP failures preserve typed
   answers, saved facts, and existing valid plans. Follow-up reruns make no calls.
3. Validate locked setup, full pytest with warnings as errors, independent review,
   and browser walkthrough in a separate session to preserve the owner's session.
   Use isolated mocked HTTP for failure checks; do not change actual credentials.
4. Document actual evidence, a beginner-friendly demo script, and Week 1 limits.

## Review focus

Saved-process return must preserve pending edits. Restart must never restore a
synthetic demo in place of an active interview. Cached older plans must render
without a new-field crash. Demonstration instructions must match the current UI.

## Progress

Original scope recovered from the architecture proposal in this task's history.
The user has explicitly authorized this final milestone. Existing preview and
workspace retained. No new dependencies needed.

## Completion evidence

- Added qualitative effort and clear interview restart/return navigation.
- Four new finish-line UI tests; three complete course journeys with real SDK
  parsing and mocked HTTP. Pending inputs survive the hidden-review screen.
- Numeric support accepts sentence-ending punctuation, but validates complete
  tokens against the enclosing source message. Review found truncated decimal
  excerpts could pass; three regression cases reproduced and fixed that issue.
- Locked `uv sync --locked` succeeded. Full regular suite: 215 passed, 2 skipped.
- Browser: complete demo dashboard/plan, effort labels, 45→30-minute correction,
  $126.25/$2,525.00 corrected results, reset, incomplete demo unavailable totals
  and $5.00 known subtotal, and missing-fact plan verified.
- Separate local failure preview used mocked SDK HTTP 503 responses. Verified an
  existing plan/dashboard and typed interview answer survive failures. No real
  credentials read/changed or API requests made by that test harness. Temporary
  server/file/tab were removed. Main preview was left running.
- Independent review found no other material issues. No Milestone 7 exists in
  the approved plan; all six Week 1 milestones are implemented locally.

Final synthetic live checks: interviewer and improvement plan both passed
(2 passed in 11.51 seconds). Main preview health endpoint returned `ok`.
