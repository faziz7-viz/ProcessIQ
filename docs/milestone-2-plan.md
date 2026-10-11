# Milestone 2: Deterministic Calculation Engine

Approved scope: Python time/cost calculations, potential bottleneck rankings,
pytest verification, and documentation. No UI, AI calls, or recommendations.

## Interfaces
`analyze_workflow(workflow: Workflow) -> WorkflowAnalysis` in `processiq/analysis.py`.
Validated immutable result models live in `processiq/models.py`.

## Rules
- Use only confirmed facts. Missing and unconfirmed inputs produce gaps with
  stable paths and reasons; never convert either into zero.
- Per-step active/waiting durations retain minutes. Elapsed = active + waiting;
  labor effort = active minutes * people, in person-minutes. Waiting is elapsed
  time before work on the current step, inside the process boundaries.
- Labor cost = active minutes * people * hourly labor cost / 60. Waiting has no
  labor charge. Work with Decimal in a private context so caller precision,
  rounding, and traps cannot change results.
- Round each step's labor cost to cents with ROUND_HALF_UP, sum rounded step costs
  for per-case cost, then multiply per-case cost by integer monthly volume.
- Every metric lists its formula, input paths, source evidence, and blocked facts.
  Totals are unavailable if any contributing step is unavailable. An incomplete
  total may have a known subtotal from fully calculable steps; no contributors
  means no subtotal, rather than an invented zero.
- Monthly cost requires complete per-case cost and confirmed monthly volume,
  including when volume is zero. Do not present a partial monthly projection.
- Rank positive waiting durations and labor effort descending, preserving process
  order in ties and using dense ranks. Keep every tied candidate. Mark incomplete
  rankings partial, list gaps, and do not claim a capacity constraint or cause.
- Revalidate input exports at the analysis boundary to catch invalid edits made
  through Pydantic model_copy. Never mutate the supplied workflow.

## Tasks
1. Write hand-checked complete/incomplete fixture assertions and edge-case tests.
2. Run tests before implementing; confirm missing-engine failures.
3. Add result models and minimal pure Python engine; run the full suite.
4. Check rounding, ties, zero, confirmation, context isolation, serialization,
   correction/recalculation, and unchanged input. Update README and run pytest
   with warnings treated as errors.

## Review focus
Unknown vs zero; confirmation on every dependency; repeating division and penny
rounding; positive-only tie rankings; stale or bypassed validated input; subtotals
that could otherwise look like complete totals. Tests pin these behaviors.

## Completion

The engine, result models, and documentation are implemented. A focused independent
review found no implementation issues. Final verification: 89 pytest cases pass
with warnings treated as errors; both demo files were analyzed directly. Synthetic
waiting labels were clarified to place waiting before work on the current step,
inside process boundaries, without changing any numeric inputs. Milestone 3 has
not started.
