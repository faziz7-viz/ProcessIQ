# ProcessIQ: Week 1 demonstration guide

## Start the application

Open a terminal in the ProcessIQ folder, then run:

```sh
uv sync --locked
uv run streamlit run app.py --server.address 127.0.0.1
```

Open http://127.0.0.1:8501/. Start with **Upload a CSV**, **Use sample data**, or
**AI interview (optional)**. CSV uploads, the complete and incomplete synthetic demos,
and rule-based plans work without an API key or API usage. For live interviews/plans,
configure this project's `.env` as described in README. Use fictional data during
presentation. Keep your API key off screen.

## CSV walkthrough (no questions required)

1. Leave **Upload a CSV** selected and download the template. Explain that its
   painting-quote workflow is fictional, with one row per sequential step.
2. Upload the template and choose **Review uploaded data**. Show its three steps
   and CSV row evidence. No interview has been started and no API call is needed.
3. Check the workflow and numeric values, select **This matches the workflow I want
   to assess** and **Confirm all provided values on save**, then **Save reviewed facts**.
4. **Calculate dashboard** shows $37.50 per case, $750.00 per month for 20 cases,
   and 105 elapsed minutes. **Create offline plan** produces evidence-linked actions.
5. Change Prepare quote from 30 to 20 active minutes, confirm/save, and recalculate:
   $27.50 per case and $550.00 per month. Values left blank stay unknown, not zero.
6. Use **Choose data source** to explore the sample workflows or optional interview.

The CSV format and supported columns are documented in README. Only step_name is
required. Per-task weekly frequencies are not converted into monthly case volume.

## Short presentation walkthrough

1. Say: “ProcessIQ helps a small service-business owner understand one sequential
   process. The owner confirms facts, Python calculates, and AI prioritizes actions.”
2. Choose **Use sample data**, then load **Complete contractor demo**. Explain the estimate process and show a
   reviewed source quote. Waiting occurs before each step within the boundaries.
3. Click **Calculate dashboard**. Point out $137.50 labor cost per case and
   $2,750.00 projected monthly labor cost for 20 cases. Explain that waiting is
   not charged as labor. Follow-up has 2,880 waiting minutes; the site visit has
   120 person-minutes. These are contributions, not proven causes or capacity limits.
4. Click **Create offline plan**, or **Generate AI plan** if live AI is configured.
   Show supporting evidence and actions with suggested owner, qualitative effort,
   and a measurement to track. Explain that this does not promise savings.
5. Expand **4. Prepare estimate**, change active minutes from 45 to 30, and show
   that the dashboard and plan disappear. Confirm the changed value, save, and
   recalculate. The new cost is $126.25 per case and $2,525.00 per month. Create a
   new plan. The original sources remain and the correction has a new source.
6. Click **Reset current demo**. The original 45-minute value returns; old results
   clear. Reset never edits the fixture files.
7. Load **Incomplete contractor demo** and calculate. Full cost is **Unavailable**,
   with a **$5.00 known subtotal**. Missing and unconfirmed values are not zero.
   Create an offline plan; its first action collects and confirms missing facts.
8. Optionally show the live interview using the single-step synthetic description
   below. All extracted numbers start unconfirmed. Review them before calculation.
   **Restart AI interview** clears that conversation. **Return to saved process**
   returns to the prior saved process and preserves pending review edits.

## Synthetic description for the live interview

This is synthetic course data for a contractor. Our process is Receive an inquiry.
It starts when a customer inquiry arrives and ends when its details are recorded.
There is one sequential step: Receive inquiry, handled by the office administrator.
Receiving takes 10 active minutes per case. Waiting before this step is 0 minutes.
There is 1 person working. Labor cost is USD 30 per person per hour. We handle
20 cases per month.

After confirming and saving, this example should calculate $5.00 per case and
$100.00 per month. The model may ask a clarification before you review it.

## Show failure handling reliably

Provider failures are nondeterministic, so ordinary course tests use the actual
SDK with an isolated mocked HTTP response. Run:

```sh
uv run pytest tests/test_course_journey.py -v
```

These scenarios verify description → extraction → review → calculation → plan,
correction/recalculation, a failed follow-up preserving the typed answer and draft,
and a failed plan request preserving the existing plan and dashboard. They make
no real provider calls and do not alter `.env`. Do not break your configured key
or depend on a provider outage to demonstrate graceful failure.

## How the architecture works

```text
CSV upload -> CSV validation --------+
                                    |
Sample fixture ---------------------+--> Validated workflow
                                    |            |
Optional interview -> OpenAI -------+            v
                              Owner review and confirmation
                                                 |
                                                 v
                              Python Decimal calculations
                                                 |
                                                 v
                              Tables and Plotly dashboard
                                                 |
                                                 v
                              Verified finding/action catalog
                                                 |
                                                 v
                              AI selection OR offline rules
                                                 |
                                                 v
                              Evidence-linked improvement plan
```

`app.py` handles screens and temporary session state. `csv_import.py` validates CSV
cells and records their row evidence without AI. `models.py` defines validated
facts and evidence. `interview.py` controls the question loop and validates draft
extractions. `llm.py` handles the provider, strict response formats, and safe errors;
`prompts.py` contains its instructions. `assessment.py` validates owner edits and
records corrections. `analysis.py` performs all arithmetic. `dashboard.py` presents
tables/charts. `recommendations.py` builds the verified catalog and checks selected
actions. `report.py` displays explanations and the action plan.

The agentic loop is bounded: the AI identifies a useful question, the owner answers,
Python validates the updated draft, and the cycle repeats for up to 30 answers.
The AI never confirms facts. Its plan response contains only finding IDs and action
codes; Python supplies all displayed numbers, quotes, and explanation wording.

## Week 1 limits and later work

One sequential process, USD, explicit minute/hour units, temporary in-browser
session data, owner estimates, and a small action-template catalog. Refreshes and
server restarts can lose the session. Qualitative effort is a suggestion to review,
not a measured estimate. Evidence proves traceability, not the truth of a claim.
Costs exclude materials/overhead; monthly cost is projected, not observed spend.

Postpone saved history/database, team access, authentication/billing, business
integrations, branching/parallel workflows, capacity modeling, document uploads,
automatic implementation, benchmarks/ROI projections, advanced exports, and
production deployment. The course demo is complete locally, not production-ready.
