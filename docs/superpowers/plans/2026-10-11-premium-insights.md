# Premium Insights Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for coordinated implementation. Steps use checkbox syntax for tracking.

**Goal:** Deliver the approved interactive ProcessIQ dashboard and durable Git checkpoints.

**Architecture:** Keep the validated Python calculation and provider boundaries intact. Add presentation helpers and a scoped design system; use separate Streamlit workspaces with explicit navigation and preserved review state. Scenario arithmetic is independent of confirmed Workflow objects.

**Tech Stack:** Existing Python, Streamlit 1.65+, Plotly, pandas, Pydantic, Decimal; no additional product dependencies.

**Spec:** docs/superpowers/specs/2026-10-11-premium-insights-design.md

## Global Constraints
- Preserve the working CSV, sample, interview, review, analysis, and plan journeys.
- Unknown is distinct from zero, missing from unconfirmed.
- Live provider calls remain explicit; no credentials committed.
- Respect reduced motion and keyboard navigation.
- No historical trends or claimed realized savings.

## Review Focus
- Navigating away and back must preserve unsaved fact values and their confirmations.
- Duplicate step labels use stable IDs for selection, evidence and charts.
- Partial/zero totals never produce misleading percentages or hypothetical totals.
- User labels and source quotes must be escaped in custom HTML.
- Long names and 200-step workflows must remain usable; scenario reset must respect changed assessment.

## Task 1: Version control and baseline
- [x] Inspect repository and permissions; create dedicated private repository because parent is read-only and ProcessIQ untracked.
- [x] Verify baseline with `.venv/bin/python -m pytest -W error -q`: 280 passed, 3 skipped.
- [x] Ignore environment, local cache and scratch artifacts; inspect staged files for credentials.
- [ ] Push baseline/tag, create feature branch, commit this design/plan.

## Task 2: Insight explorer
Files: processiq/dashboard.py, processiq/insights.py, tests/test_dashboard.py, tests/test_insights.py.
Interface: retain format_metric(metric), step_table(analysis), build_charts(analysis); render_dashboard(analysis, workflow=None) may return selected step ID. No imports from recommendations to avoid existing circular dependency.
- [ ] Add/run failing behavior tests for safe percentages, human time, missing values, stable selection and descending charts.
- [ ] Implement evidence-derived hero, primary metrics, selectable chart lenses, selected step details and exact tables.
- [ ] Verify focused tests. Root integrates global CSS and workspace navigation.

## Task 3: App shell and presentation
Files: app.py, processiq/presentation.py, processiq/ui/app.css, processiq/ui/start.css, .streamlit/config.toml, tests/test_workspace.py; existing journey tests updated only for intentional navigation changes.
Interface: presentation.app_css() returns local-font CSS; workspace view persisted as a session value; existing edit/invalidation/provider callbacks remain authoritative.
- [ ] Add/run failing navigation and draft-preservation tests.
- [ ] Implement refined source screen, compact sidebar, process header, workspaces, save/calculate routing and contextual controls.
- [ ] Style dashboard and plan consistently; preserve interview presentation.
- [ ] Verify app/CSV/interview/plan tests, commit and push tested milestone.

## Task 4: Hypothetical scenarios and action cards
Files: processiq/scenarios.py, processiq/scenario_ui.py, processiq/report.py, tests/test_scenarios.py.
Interface: render_scenarios(workflow, analysis) displays an isolated comparison. Pure scenario helper accepts workflow + stable step ID + active/wait reduction percentages; returns baseline/hypothetical calculated metrics without mutating Workflow.
- [ ] Add/run failing tests for unchanged baseline, 0 and 100 percent reduction, missing inputs and Decimal rounding.
- [ ] Implement hypothetical comparisons and clear labels; no provider calls or saved confirmations.
- [ ] Refine plan into cards with effort, owner, expandable measurement and linked evidence.
- [ ] Verify focused tests; root integrates workspace and CSS.

## Task 5: Verification and delivery
- [ ] Run full offline suite with warnings as errors; fix regressions with focused tests.
- [ ] Independent code review of validity, navigation, missing facts, safe markup and scenarios.
- [ ] Browser verification of overview, chart selection, review correction, incomplete data, offline plan, scenario and narrow screen.
- [ ] Add GitHub Actions offline checks and update README with usage and checkpoint workflow.
- [ ] Commit/push final tested build, retain baseline tag, open local app preview and report URL/repository.

## Execution ledger
- Ruling: user requested autonomous implementation; written-spec and plan approval pauses are waived by that explicit request.
- Ruling: use a dedicated repository and feature branch in the current project directory, isolating it from the unrelated parent course repository without relocating the running app.
- Ruling: delegate independent dashboard and scenario/report files; root owns navigation, global design system, integration, Git and verification.
