# Milestone 5: Evidence-based explanations and improvement plan

Authorized by the request to proceed to the next milestone after Milestone 4.
Implement in the existing ProcessIQ workspace so the configured local preview
and owner setup continue to work. Milestone 6 remains out of scope.

## Design

Python builds a catalog of findings from a fresh deterministic analysis of the
saved workflow. Every numeric explanation includes the engine's exact value,
unit, formula, input paths, and actual source evidence. Partial rankings stay
partial; unknown totals stay unavailable. Indicators do not establish causes.

The AI selects and orders catalog findings and applicable action templates via
structured output. It cannot supply numbers, quotes, financial claims, causes,
or arbitrary narrative. Python renders plain-English explanations and practical
experiments from those selections. This deliberately constrained Week 1 design
prioritizes financial integrity over unrestricted AI prose. Actions state what
to try and how to measure it, with no projected savings or promised outcome.

An explicitly labeled rule-based plan works without a key. The live AI option
uses the current project configuration and only runs on an explicit button.
Failure preserves an existing valid plan. Any fact edit, save, reset, demo load,
new interview, or recalculation clears the plan. A workflow fingerprint also
guards against showing a stale report after session/code changes.

## Files and interfaces

- Create `processiq/recommendations.py`: immutable finding/action/report models,
  `build_catalog(workflow)`, `generate_plan(workflow, planner=None)`, snapshot
  fingerprint, validation of references/applicability and offline selection.
- Modify `processiq/llm.py`: `PlanOutput`, `ActionSelection`, and
  `OpenAIPlanner.select(catalog=...)` with existing credentials/error boundaries.
- Modify `processiq/prompts.py`: constrained selection instructions.
- Create `processiq/report.py`: plain-language report rendering and source details.
- Modify `app.py`: explicit offline/live buttons and report state/invalidation.
- Create tests for catalog, transport, report, Streamlit interactions, and an
  opt-in synthetic live plan test. Update README with the completed scope.

## Implementation tasks

1. Write failing catalog/plan tests, implement the pure selection and report
   contract, and run the entire suite. Pin complete demo costs $137.50/$2,750.00,
   follow-up waiting 2,880 minutes, site-visit effort 120 person-minutes, exact
   sources, partial comparisons, ties, confirmed zeros, unknowns, and corrections.
   Reject unknown IDs, incompatible actions, duplicates, missing gap disclosure,
   fabricated fields/quotes/savings, and revalidated bypassed model updates.
2. Write failing mocked real-SDK tests and implement the live structured selector.
   Check strict schema, payload without credentials, invalid output, refusal,
   timeout, provider/configuration failures, bounded retries, and safe errors.
3. Write failing AppTest scenarios and add report UI. Verify explicit-only calls,
   offline use, incomplete assessments, preserved report on failure, legacy-state
   migration, all result invalidation paths, same-rerun edits and generation,
   and stale fingerprint handling. Run all tests with warnings treated as errors.
4. Run one real API smoke test with only synthetic data using the already
   configured key; review the feature independently, fix material issues with
   regression tests, verify server health, and document actual test evidence.

## Review focus

- A report must not mix new workflow facts with an older dashboard.
- Ties and partial comparisons must not claim a unique overall bottleneck.
- An action's eligibility must depend on its cited finding, including gaps.
- Unavailable/zero values and empty rankings must remain distinct.
- Hostile owner text or model output must not insert invented financial claims.

## Progress

Plan/design preflight: selection references, report rendering, and session
invalidation share the catalog contract; no conflicting interfaces found.
Implementation and test evidence will be recorded below.

Task 1 complete: catalog and selection tests written before implementation;
19 cases pass, including collisions and bypassed model-update validation.
Task 2 complete: 12 mocked real-SDK tests pass; shared transport preserves the
existing interview behavior. No dependencies or key configuration changed.
Task 3 complete: 17 AppTest cases pass, including same-rerun edits, legacy state,
all invalidation paths, and stale analysis/report protection.
Task 4 verification: live synthetic plan test passed (1 test, 4.77 seconds).
Independent review found a stale dashboard/new report mixture after a valid
session workflow replacement. Regression tests reproduced it; analysis
fingerprints plus verified legacy migration fixed it. The whole regular suite
passes: 203 passed, 2 opt-in live tests skipped. No other material findings.

Preview verification: reran the existing in-app browser session and inspected
the rendered improvement plan/actions. Captured a screenshot of the action list.
