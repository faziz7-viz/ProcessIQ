# ProcessIQ

A Week 1 Mastering Agentic AI course project for small service businesses.

**Current scope: Complete Week 1 demo (Milestones 1–6).** ProcessIQ has validated data, synthetic fixtures,
a deterministic calculation engine, a Streamlit review/dashboard, and an OpenAI
interview/extraction integration, evidence-backed explanations, and prioritized
improvement plans. Live AI requires your own configured API key.

## Setup and tests

Python 3.11 or newer and uv are required. Open a terminal in this ProcessIQ folder, then:

```sh
uv sync --locked
uv run pytest -W error
uv run streamlit run app.py --server.address 127.0.0.1
```

The lockfile fixes the tested dependency versions. The project also uses Streamlit, pandas, and Plotly for the interface.
Open http://127.0.0.1:8501/. CSV uploads, synthetic demos, offline plans, and ordinary tests
do not require an API key. Live interviews and AI plans do.

For a short presentation walkthrough, sample interview description, expected
results, architecture, and failure-handling checks, see [the demo guide](docs/demo-guide.md).

## Get started with a CSV (no interview required)

The start screen defaults to **Upload a CSV**. **Use sample data** and
**AI interview (optional)** are alternative starting points. From an existing
assessment or the interview's Options menu, use **Choose data source** to return.

1. Download the CSV template from the start screen, or use
   [data/workflow_template.csv](data/workflow_template.csv). Its values are fictional;
   replace them with your own for an actual assessment.
2. Upload a UTF-8 CSV with one row per sequential step, then select **Review uploaded data**.
3. Correct any facts or scope labels, check **This matches the workflow I want to assess**,
   confirm the values you know, and select **Save reviewed facts**.
4. Select **Calculate dashboard**, then **Create offline plan** or **Generate AI plan**.
   Only the latter sends the saved assessment to OpenAI. Upload and review are local.

| Column | Meaning |
| --- | --- |
| `step_name` | Required; one nonblank name per step, in process order |
| `responsible_role` | Optional role responsible for that step |
| `active_minutes` | Active minutes per case |
| `waiting_minutes` | Elapsed waiting before that step, in minutes per case |
| `people` | Whole number of people actively working, at least 1 |
| `hourly_rate_usd` | Labor cost in USD per person per hour; number without `$` |
| `monthly_volume` | Whole number of cases for the entire workflow per month |
| `process_name`, `start_point`, `end_point`, `currency` | Optional workflow details; USD only |

Only `step_name` is required. Blank or omitted numeric fields remain unknown;
explicit zero remains zero (except people, which must be positive). Workflow details,
including monthly volume, can appear on the first row only or repeat consistently.
Different task frequencies, hours, or other currencies are not silently converted.
Familiar headers such as `Task`, `Team members`, `Hourly rate (USD)`, and
`Cases per month` are also accepted. Unknown and duplicate columns are rejected.
Files are limited to 2 MB and 200 steps; invalid cells identify their row and column.

`csv_import.py` converts the file into the same validated `Workflow` used by the
interview. Every imported number starts unconfirmed and retains row-level source
evidence. The filename and first/last steps supply editable scope labels when
metadata is absent. No numeric value is inferred, and no AI request occurs during
import. Partial uploads can produce partial results and a plan to collect missing facts.

After confirmation, the template calculates **$37.50 per case**, **$750.00 per month**,
and **105 elapsed minutes per case**. Changing Prepare quote from 30 to 20 active
minutes yields **$27.50 per case** and **$550.00 per month**.

CSV update verification (October 11, 2026): `uv run pytest -W error -q`
passed **280 tests**, with **3 opt-in live-provider tests skipped**. The browser
walkthrough used the real file picker to upload the template, confirm/save facts,
calculate $37.50/$750.00, generate an offline plan, and correct/recalculate to
$27.50/$550.00. No live AI request was needed for that path.

## The data contract in plain English

`Workflow` is the container for one sequential process. It records the process
name, its start and end points, owner source messages, monthly case volume, and
ordered steps. It supports USD for this initial demo. `data_kind` explicitly
marks synthetic data or owner-provided data.

`WorkflowStep` records a stable ID, position, name, responsible role, and four
numeric facts: active time, waiting time, people working, and hourly labor cost.
All numeric facts are optional, so a partial interview can become a valid draft.
A process still requires a name, boundaries, at least one owner message, and one
step. The AI interviewer collects those starting details from the owner description.

Each fact has:

- `value`: a known quantity, or `null` in JSON (`None` in Python) when unknown.
- `unit`: minutes, people, cases/month, or currency/hour, depending on the field.
- `evidence`: a source message ID and a verbatim quote from that message.
- `confirmed`: whether the owner has reviewed this particular value.

For example, the complete demo's first step records 10 active minutes, zero
waiting minutes, one person, and USD 30.00 hourly labor cost per person. Its
numeric inputs have evidence and simulated owner confirmation.

### Validation rules

1. Unknown is never replaced with zero. Explicit zero duration, cost, or monthly
   volume is allowed and requires evidence. A known worker count must be at least
   one; zero workers is rejected.
2. Negative, infinite, and NaN quantities are rejected. Counts must be actual
   integers; strings, fractions, and booleans are not accepted as counts.
3. Durations and money become Python `Decimal` values. JSON inputs should use
   decimal strings such as `"30.00"` or integers. Binary floats are rejected to
   preserve exact input values. Input validation does not round money; analysis applies the rounding policy below.
4. Units must match the field. Hours cannot silently enter a minutes field. A
   future interviewer must resolve units before submitting a draft.
5. Every known numeric value must include evidence. Each quote must occur exactly
   in an existing owner source message. Blank quotes and missing source IDs fail
   validation. Unknown values may cite an owner saying they do not know.
6. Unknown values cannot be marked confirmed. Known values may remain unconfirmed
   during extraction. Confirmation must be a real boolean.
7. Unexpected fields, blank labels, duplicate source/step IDs, and invalid step
   sequences are rejected. Steps must appear as 1, 2, 3, and so on.

**Evidence checks traceability, not truth.** Validation cannot prove the quote
supports the extracted number semantically, or that the owner's estimate is
accurate. Source messages must come from the owner's actual input, not text an
LLM is allowed to invent. The application collects those messages itself, shows extracted facts for review,
and manages confirmation outside the LLM.

### Correcting facts safely

Models and their nested collections are immutable. Export a draft using
`workflow.model_dump(mode="json")`, update the exported data, add the owner's
correction as a source message, replace the changed fact's evidence, and call
`Workflow.model_validate(updated_data)` to validate it again. Set the changed
fact's confirmation to false until the owner reviews it.

Do not use `model_copy(update=...)` for user edits: Pydantic does not validate
those updates. The tests demonstrate a valid correction and rejection of a
negative corrected value. Edits invalidate old analysis and recommendations.

## Synthetic examples

Both examples describe a fictional contractor's inquiry-to-estimate follow-up
process with six steps. Waiting time means elapsed time before work on the current step,
inside the process boundaries, including nights and weekends. Active time is elapsed time while the listed
people work; the calculation engine will multiply by people to obtain labor time.
Hourly rates represent per-person labor cost, not customer billing rates.

- `data/contractor_estimate.json`: complete data; all numeric facts are present
  and marked confirmed to simulate an owner-reviewed assessment. It includes
  zero waiting time and a two-person site visit.
- `data/contractor_estimate_incomplete.json`: the same representative process
  with unknown monthly volume, site-visit waiting time, estimate preparation
  time/rate, and follow-up staffing/rate/role. Only receive-inquiry facts have
  simulated confirmation; other known values remain drafts.

Demo confirmation is fictional review, not an assertion about a real business.

Load either example with the same production validator:

```python
from pathlib import Path
from processiq.models import Workflow

workflow = Workflow.model_validate_json(
    Path("data/contractor_estimate.json").read_text()
)
```

## How the application uses this contract

The Python calculation engine receives validated, owner-confirmed facts.
Separate active/waiting durations prevent waiting from automatically being charged
as labor. People and per-person rates support labor-time/cost calculations.
Unknown values let the engine mark unsupported totals unavailable rather than
fabricating numbers. Validation alone does not authorize calculation: the engine
must check the confirmation and availability of every input it uses.

The AI interviewer uses these fields as its checklist, asks about missing or
ambiguous facts, and return drafts in this format. Stable step/message IDs let
answers and corrections target the right place. The schema and JSON round trips
support structured exchange; decimal values serialize as strings. The LLM must
not decide confirmation or replace the application's recorded owner messages.

## Deterministic analysis (Milestone 2)

Call the pure Python entry point with a validated workflow:

```python
from processiq.analysis import analyze_workflow

result = analyze_workflow(workflow)
print(result.labor_cost_per_case.value)       # Decimal('137.50') for complete demo
print(result.monthly_labor_cost.value)        # Decimal('2750.00') for complete demo
print(result.waiting_ranking.entries[0].step_id)  # 'follow-up'
```

There are no AI calls and no filesystem reads inside the engine. Every call
recalculates from its input; it does not cache or mutate the original workflow.
Input exports are revalidated to catch invalid edits that bypassed Pydantic.

### Formulas and units

- Step elapsed minutes = active minutes + waiting minutes.
- Step labor effort = active minutes * people, measured in person-minutes.
- Step labor cost = active minutes * people * hourly labor cost / 60.
- Process totals = sum of the relevant step metrics.
- Monthly labor cost = per-case labor cost * confirmed monthly case volume.

Waiting increases elapsed time, not labor cost. Divide person-minutes by 60 to
interpret effort in person-hours. For example, a two-person 60-minute site visit
uses 120 person-minutes (2 person-hours), while its active elapsed time is 60 minutes.

All arithmetic uses Decimal with a private context and sufficient precision for
the supplied inputs. Money uses **ROUND_HALF_UP** to two decimal places per step.
Per-case cost sums those rounded line items; monthly cost multiplies the rounded
per-case total by the integer volume. This makes displayed step costs add up to
the displayed process total. Monthly cost is a projection under this per-case
rounding policy, not observed accounting expenditure.

### Complete synthetic demo results

| Metric | Result |
| --- | ---: |
| Active time per case | 145 minutes |
| Waiting time per case | 4,680 minutes |
| Sequential elapsed time per case | 4,825 minutes |
| Labor effort per case | 205 person-minutes |
| Labor cost per case | USD 137.50 |
| Labor cost for 20 cases/month | USD 2,750.00 |

The largest waiting contributor is follow-up (2,880 minutes); the largest labor
contributor is the two-person site visit (120 person-minutes). These are potential
bottleneck indicators, not proof of a capacity constraint or its cause. Sequential
elapsed time includes nights/weekends and is not a count of working minutes.

### Missing facts and partial results

Each `AnalysisMetric` has a `value`, `unit`, `formula`, `input_paths`, `evidence`,
and `blocked_by`. If any required input is missing or unconfirmed, `value` is
`None` and `blocked_by` tells you which facts need attention. Missing inputs and
unconfirmed inputs have different reason labels.

Incomplete aggregate metrics also have `known_subtotal`, covering only fully
calculable steps. It is not a total estimate. If no step is calculable, the
subtotal is `None`; a confirmed zero contribution remains a real zero.
An elapsed-time subtotal includes only steps with both durations confirmed.

In the incomplete demo, only receive-inquiry facts are reviewed. Its known
labor-cost subtotal is USD 5.00, and its known waiting subtotal is zero. Full
process costs and times remain unavailable. No partial monthly cost is projected.
Monthly cost requires both complete per-case cost and confirmed volume, even if
volume is zero. Similarly, zero active time does not bypass missing rate/staff
requirements. This conservative policy keeps every formula's inputs explicit.

### Rankings and ties

`waiting_ranking` compares confirmed waiting minutes; `labor_ranking` compares
confirmed person-minutes. Positive contributions sort largest first. Equal values
share a dense rank (1, 1, 2), preserving process order within the tie. Zero values
are omitted because they are not bottleneck contributors.

Each ranking has `complete` and `blocked_by`; incomplete data produces a partial
comparison of calculable steps rather than a claim about the entire process.
Ranked entries retain source evidence and input paths for later dashboards and
AI explanations. No causes, recommendations, or savings are generated here.

## Run the local application (Milestone 3)

From the ProcessIQ folder:

```sh
uv sync --locked
uv run streamlit run app.py --server.address 127.0.0.1
```

Open the local URL printed by Streamlit, normally `http://127.0.0.1:8501`.

1. Choose **Use sample data**, select the complete or incomplete synthetic example,
   and click **Load selected demo**.
2. Expand the steps to review their names, roles, numeric facts, and confirmation.
3. Change any incorrect values. Leave unknowns blank; counts must be whole numbers.
   Editing a numeric value clears its confirmation and removes the old dashboard.
4. Confirm individual facts, or select **Confirm all provided values on save** after
   reviewing them. Missing values remain unknown and unconfirmed.
5. Click **Save reviewed facts**. Invalid values display errors and do not replace
   the last valid saved workflow. Unsaved edits keep calculation disabled.
6. Click **Calculate dashboard** to see saved/confirmed metrics, charts, rankings,
   and evidence. The incomplete example works without filling its gaps.
7. **Reset current demo** discards the session's edits and results and restores the
   currently loaded fixture. Choosing another radio option does not replace the
   loaded assessment until **Load selected demo** is clicked.

New numeric corrections are recorded as owner-review statements with unique source
IDs and exact quotes. Unchanged facts retain their original sources. These statements
record values supplied through the review inputs; they are not AI-generated facts.
Individual confirmations are preserved only for unchanged values or explicit review.

`app.py` manages temporary session state; `assessment.py` applies validated edits;
`dashboard.py` builds the exact-value tables and Plotly charts. Chart floats are
for visual presentation only; money calculation continues to use Decimal. Steps
and step order are fixed in this milestone; editing their labels/roles is supported.

**Start AI interview** starts a new conversation from review; **Restart AI interview**
is available in the interview's Options menu. **Return to saved process** exits the interview without
submitting and restores pending review inputs for the previously saved process.

Refreshes or server restarts can lose edits. No edits are written back to the demo
files. No authentication or external business integrations are included.
AI calls happen only when an interview answer is explicitly submitted.

## AI interview and extraction (Milestone 4)

### Configure live AI

Copy `.env.example` to `.env` **inside ProcessIQ**, then fill in:

```text
OPENAI_API_KEY=your-own-key
OPENAI_MODEL=gpt-5-mini
```

Do not commit `.env`, paste keys in chat, or place them in source code. The app
loads only ProcessIQ/.env and environment variables; it does not search neighboring
projects for credentials. An existing environment variable takes precedence.
The key is never shown in the app. API requests go to the official OpenAI endpoint.

The integration uses the Responses API with strict structured output, following
[official OpenAI documentation](https://developers.openai.com/api/docs/guides/structured-outputs).
The default model is configurable. Alternate models must support Responses
structured outputs; GPT-5 model IDs also receive low reasoning effort.
Each request has a 30-second timeout and at most one SDK retry for transient
failures. Output is capped at 6,000 tokens. Retries can increase wait time/usage.

### Use the interview

1. Click **Start AI interview**.
2. Describe one process, its start/end, and its ordered steps. This first version
   supports sequential workflows and USD. Include only information you know.
3. Click **Continue**. Only this action calls the provider. The app sends
   your recorded owner messages and current draft to OpenAI; ordinary UI reruns
   do not make requests. Responses are requested with `store=False`.
4. Answer one follow-up at a time, or say **I don't know**, **unknown**, **skip**,
   or **not sure**. The previous missing field is skipped rather than invented.
5. Click **Review extracted facts** whenever a valid draft exists. Every extracted
   numeric fact starts unconfirmed. Review/correct it, confirm provided values,
   save, and calculate using the existing Python engine.

An interview stops after six successful turns or when no unskipped numeric gap
remains. A vague description can produce a process-details question without
fabricating workflow steps. If no valid workflow exists at the turn limit, start
again with clearer boundaries/steps or use a synthetic example.
API failures, refusals, incomplete output, and invalid extraction preserve the
previous draft and typed answer so you can retry or review available facts.

### How the Python and AI responsibilities stay separate

- `prompts.py` instructs the model to interview and extract, never calculate.
- `llm.py` defines an all-required structured response and handles the provider.
  The model's output has no confirmation flags or owner-message collection.
- `interview.py` owns conversation state and creates actual owner message IDs.
  It validates all evidence against those messages, forces confirmation to false,
  and passes the resulting workflow through the established Pydantic contract.
- Numeric literals and the required units must appear in supporting quotes. No default labor rate,
  staffing, time, or volume is added. Decimal values stay exact strings.
- This conservative first version asks for explicit numeric values in required
  units instead of automatically interpreting word-only numbers or converting
  hours into minutes. Counts must be integers; blank/unknown stays `None`.
- Lexical evidence checks cannot prove that a number means the correct business
  fact. Contradictions, ambiguities, and semantic mistakes still require owner
  review. The UI shows the original sources and allows corrections.

The AI chooses one missing-field or clarification target. Python checks that it
is a valid process/field target and has not been skipped. Scope and known-fact
clarifications are allowed even when all numbers are filled. Invalid selections
fall back to a targeted missing-field question. Model output never controls whether calculations are authorized.

### Live synthetic smoke test

Ordinary tests never consume API usage. After configuring your key, explicitly run:

```sh
PROCESSIQ_LIVE_TEST=1 uv run pytest tests/test_live_interview.py -v
```

This sends one synthetic contractor description to the real API and verifies the
extracted volume, active/waiting time, staffing, labor rate, and unconfirmed state.
Live verification succeeded on October 8, 2026 using the configured project key:
`PROCESSIQ_LIVE_TEST=1 uv run pytest tests/test_live_interview.py -v` passed
its one synthetic extraction test in 13.80 seconds. This confirms this example
works with the actual API; other descriptions still require owner review.

## Explanations and improvement plans (Milestone 5)

After saving/confirming facts and calculating the dashboard, choose:

- **Create offline plan**: a clearly labeled rule-based plan, without an API call.
- **Generate AI plan**: the AI selects and prioritizes relevant findings and
  applicable actions from an evidence-backed catalog. This sends the saved
  assessment, source quotes, and available action templates to OpenAI.

The report explains every dashboard total in plain English, then highlights
selected findings and an ordered action plan. Actions include a suggested owner,
qualitative effort, what to try, and how to measure the result. Effort labels are
suggestions to review with your team; no hours or implementation cost is estimated. Expand each finding's evidence to see
its actual source quotes, inputs, and formula. Missing facts are the first action
for an incomplete assessment; partial rankings never imply an overall winner.
Zero remains a known value, while unavailable totals remain unavailable.

Python rebuilds the catalog from the current validated workflow and supplies all
numbers and evidence. The LLM returns only finding IDs and action codes in a
strict structured response. It cannot supply arbitrary explanations, causes,
financial values, quotes, percentages, or savings. Python writes the displayed
explanations and experiment instructions using the verified findings and small
predefined action templates. This Week 1 restriction keeps financial information
reliable, at the cost of less flexible AI prose and a limited action vocabulary.
It does not prove that an owner's estimate is true or that a suggested trial will
help. Required quality and safety checks should be preserved during trials.

`recommendations.py` owns the catalog, eligibility checks, and immutable report.
`report.py` presents it. `llm.py` shares the existing OpenAI request/error handling
for the interviewer and plan selector; there are no new dependencies.

Editing, saving, resetting, loading a demo, starting an interview, or recalculating
clears old plans. Fingerprints tie both dashboard and report to the current
workflow; older sessions are checked before reuse. Failed generation preserves
saved facts and an existing valid plan. Ordinary reruns never call the API.

An opt-in synthetic live plan check is available:

```sh
PROCESSIQ_LIVE_PLAN_TEST=1 uv run pytest tests/test_live_plan.py -v
```

It passed on October 8, 2026: **1 passed in 4.77 seconds** using the configured
project key. Regular tests mock external requests and never consume API usage.

## Verification

Run `uv run pytest -W error`. Regular suite: **239 passed, 3 skipped**. The skipped
cases are opt-in to avoid API usage during normal tests. The live interview and
live improvement-plan tests were each run separately and passed (**1 passed** each).

The 36 Milestone 4 offline cases cover structured parsing through the actual
OpenAI SDK with mocked HTTP, safe error messages, network timeout, refusal,
incomplete/malformed output, source quotes, unsupported numbers/units, forced
confirmation, skipped questions, scope/known-field clarifications, source-unit mismatch, limits,
latest corrections, populated-draft preservation, bounded retries, and
Streamlit interview-to-review handoff. All 116 prior tests continue to pass.

A local Streamlit server was started successfully during Milestone 3. Visual
browser verification was then blocked by the locked Mac/browser attachment.
AppTest interaction tests exercise the running script without a browser. During
Milestone 5 the in-app browser was accessible: the updated app, populated
improvement plan, action instructions, and measurement guidance were inspected
and a screenshot of the rendered actions was captured.

Implementation scope: `docs/milestone-1-plan.md` through
`docs/milestone-6-plan.md`. All six approved milestones are implemented.

Milestone 6 adds end-to-end course journeys over real SDK parsing with mocked
HTTP, clearer interview navigation/restart, preserved pending edits across
screens, qualitative action effort, sentence-ending numeric evidence handling,
and the presentation guide. Locked setup and the full test suite were verified.
The optional live checks remain explicit to avoid usage during normal tests.

Final browser walkthrough verified both synthetic examples, correction from
45 to 30 minutes with $126.25/$2,525.00 results, demo reset, and qualitative
action effort. An isolated local test preview over mocked SDK HTTP verified
503 failures preserve typed answers and an existing offline plan/dashboard.
It made no real requests or credential changes and was removed after testing.

Final Milestone 6 live verification: the synthetic interview and plan tests
were run together on October 8, 2026; **2 passed in 11.51 seconds**. The normal
suite remains **230 passed, 3 skipped**. Local preview health returned `ok`.


## Adaptive workday interview

A new session opens with the data-source choices above. The optional AI interview
opens with one question: “Walk me through your typical workday.” Each next
question is selected by the existing OpenAI integration using the latest answer,
all previous question/answer pairs, and the current draft. There is no scripted
fallback questionnaire and no growing transcript. **Back** restores the earlier
answer and removes dependent sources/extraction; continuing rebuilds from that
point. **Not sure** preserves unknowns. A partial discovered workflow can be
reviewed immediately with **Finish & review**; confirm its scope and save the reviewed facts before
calculating. The safety limit is 30 answers, with Back/restart recovery if no
valid workflow has emerged. API errors preserve the current answer and draft.

Ordinary tests use the real SDK with mocked HTTP, never a live provider. For a
minimal real-model check with two synthetic workday paths and an unknown answer:

```sh
PROCESSIQ_LIVE_ADAPTIVE_TEST=1 uv run pytest tests/test_live_adaptive.py -v -s
```

This opt-in uses the existing project provider configuration; it makes three
synthetic interview requests and does not configure new access.


## Immersive interview and optional voice input

The interview opens with **Walk me through your typical workday.** One prompt
and a single-line answer field fill the screen. Empty-field examples rotate
quietly; they are placeholders only and never enter the submitted answer or
extracted evidence. Typing or transcribing stops them. Reduced-motion settings
keep the hints and watercolor background static. Fonts are bundled locally:
Geist and Instrument Serif Italic, with their SIL Open Font Licenses in
`processiq/ui/fonts`. No third-party font requests occur in the browser.

Use **Options** for privacy information, synthetic demos, restart, and return to
the saved process. **Back** appears after an answer. **Finish & review** appears
only when a valid workflow exists; the existing owner confirmation and fact
review are still required before calculations.

The microphone beside the field opens the native Streamlit recorder. Nothing
records on page load or on opening the popover. Read the disclosure, tap Record,
and tap Stop when finished. **Transcribe recording** explicitly sends the WAV to
OpenAI `gpt-4o-mini-transcribe` through the project's existing configured account;
normal API charges may apply. It replaces the editable answer field, never
automatically submits it. The user must choose **Continue**. Recordings are
session-only, limited to two minutes, and are not written to app files. A
transcription failure preserves the existing answer. Typing remains available
when microphone permission is denied or unavailable. Localhost is a supported
secure context; remotely hosted recording would require HTTPS.

This presentation uses the Streamlit 1.65 component API already in the lockfile.
Run the normal regression suite with `uv run pytest -W error`. Voice tests use
synthetic WAVs and mocked provider replies; real microphone capture and live
transcription are deliberately excluded from automated checks.
