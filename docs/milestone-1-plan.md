# Milestone 1: Data Contract and Demo Fixtures

Approved scope: validated input models, complete/incomplete synthetic workflows,
and pytest verification only. No analysis engine, UI, or LLM integration.

## Contract
- Workflow stores a sequential representative path, monthly volume, USD currency,
  source owner messages, and ordered steps with stable IDs.
- Each numeric fact stores its value, explicit unit, evidence references, and
  owner confirmation. Unknown means null, never zero. All numeric fields permit
  unknowns; worker count is a positive integer when known.
- Money and durations use nonnegative finite Decimal values, parsed from decimal
  strings or integers, never binary floats or booleans. Counts are strict integers.
- Evidence must quote an existing owner message verbatim. A known numeric value
  needs evidence; confirmation is a separate review state, not proof of truth.
- Unknown values cannot be confirmed. Unknown facts may cite an owner saying they
  do not know. Incomplete facts remain valid drafts.
- Reject unknown fields, empty labels, duplicate IDs, invalid units, and unordered
  or noncontiguous steps. Models are immutable to discourage unvalidated edits;
  changes should be made to exported data and revalidated with model_validate.
- JSON preserves decimal strings and nulls for future AI and UI exchange.

## Work sequence
1. Write model behavior tests; run them before implementation to observe failures.
2. Implement only the input contract; rerun those tests.
3. Write fixture behavior tests; observe failures before creating fixtures.
4. Create complete and incomplete synthetic fixtures with source-backed values.
5. Document the contract, run the entire suite, and review the finished files.

## Review focus
Tests cover unsupported source quotes and references; booleans/floats and
nonfinite numbers; zero vs unknown; incomplete/contradictory confirmation;
sequence and ID integrity; validated corrections and JSON round trips.

## Completion evidence
Recorded in the README and reported in chat after the final pytest run.
