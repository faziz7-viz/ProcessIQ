# Milestone 3: Fact Review and Dashboard

Approved scope: local Streamlit UI over the existing demo/model/analysis pipeline.
No AI, authentication, integrations, or improvement recommendations.

## Flow and responsibilities
- `app.py`: load/reset either demo, own session state, render review inputs,
  save validated edits, explicitly run analysis, and invalidate results on edits.
- `processiq/assessment.py`: apply reviewed edits to a workflow; append genuine
  owner correction messages and replace changed numeric evidence; preserve unchanged
  evidence; unknown stays None; confirmation is explicit, never inferred.
- `processiq/dashboard.py`: exact-value tables and metric formatting plus Plotly
  charts. Floats are for rendering only; all calculations remain in analysis.py.
- Each numeric field accepts exact decimal text or integer counts. Blank means
  unknown. Editing a value clears its confirmation and any old analysis.
- Owners may confirm individual facts or explicitly confirm all provided values
  when saving. Unknown facts cannot be confirmed, even by bulk confirmation.
- Workflow name/boundaries, per-step names/roles, monthly volume, and numeric facts
  are reviewable. Sequential topology/step insertion is deferred.
- Save errors display friendly field-level messages without replacing the stored
  valid workflow. Pending edits hide old results; analysis requires a saved draft.
- Dashboard displays supported totals, clearly labeled subtotals, gaps, partial
  rankings, source evidence, and three charts with unavailable values left blank.
- Session state is temporary; reset reloads the selected fixture, clears analysis,
  and discards editor widget state.

## Verification
1. Write failing review tests for corrections/evidence, null/zero, invalid text,
   integer counts, confirmations, and unchanged source preservation.
2. Write dashboard tests for chart values and unavailable vs zero; implement helpers.
3. Use Streamlit AppTest for initial load, complete and incomplete assessments,
   edited input invalidation/reconfirmation/recalculation, invalid save, and reset.
4. Run all pytest tests with warnings as errors. Start the local server and inspect
   the live interface in a browser, including charts and saved corrections.

## Completion evidence
- Implemented review/draft handling, confirmation/evidence, charts, tables, metrics,
  incomplete results, and reset flow. No Milestone 4 work was started.
- Independent review found duplicate editable names could combine Plotly bars.
  A regression test reproduced the failure; stable step-ID categories and numbered
  labels fixed it. No other findings were reported.
- The full suite passes 116 cases with warnings treated as errors, including seven
  automated Streamlit interaction scenarios and a same-rerun edit/calculation check.
- Local server starts at http://127.0.0.1:8501 and returns `ok` on its health endpoint.
- Visual browser walkthrough remains unverified: the Mac was locked, the in-app
  browser could not attach, and Chrome was unavailable. Preview was queued in Codex.
