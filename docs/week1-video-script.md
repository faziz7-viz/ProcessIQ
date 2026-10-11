# ProcessIQ Week 1 video walkthrough

Target length: **4 minutes 30 seconds**, leaving 30 seconds below the handout's
five-minute limit. Record your screen and your own explanation. This file is a
script, not a completed recording. Use the fictional examples throughout.

## Before recording

Run `uv run streamlit run app.py --server.address 127.0.0.1` and open
`http://127.0.0.1:8501/?demo=complete` in a fresh session. The existing review
preview uses port **8502**. Direct demo links initialize fresh sessions only.
Close developer tools. Rehearse the navigation once, then reset the demo.
Have the GitHub repository and Week 1 report available in separate tabs.
Use the offline plan to keep the recording independent of network/API latency.

## 0:00 to 0:35 — Problem and audience

Show the Overview headline and three main metrics.

“This is ProcessIQ, my Week 1 project under Path C. It helps small service-business
owners understand where time and labor go in a repeatable process. I built it with
AI coding assistance. This contractor example is synthetic, so these figures are
a demonstration rather than a customer result.”

## 0:35 to 1:15 — Data and review

Open **Workflow** and expand one step to show its inputs and source evidence.
Do not edit values during this short recording.

“Owners can upload a CSV, use a sample, or choose an optional AI interview. Each
step has active time, waiting time, staffing, and an hourly rate. Numbers retain
their source and must be reviewed. Missing values stay unknown. Python calculates
the money; AI does not invent financial results.”

## 1:15 to 2:00 — Interactive insights

Return to **Overview**. Scroll to the chart, select follow-up, and show its evidence.
Switch between the time and labor views if time permits.

“This workflow takes 4,825 elapsed minutes per case, and 4,680 of those minutes are
waiting. Labor cost is $137.50 per case, projected to $2,750 at 20 cases a month.
Waiting adds elapsed time, but is not charged as labor. Selecting a step exposes
its inputs and quoted evidence. These figures identify where to investigate;
they do not prove why a delay exists.”

## 2:00 to 2:35 — Practical next actions

Open **Improvements**, choose **Create offline plan**, and expand one action.

“The plan proposes small experiments linked to the findings. Each has a suggested
owner, effort level, and a measurement to track. The offline version works without
an API key. Optional AI can prioritize validated actions, while Python keeps the
displayed numbers and sources consistent.”

## 2:35 to 3:15 — A hypothetical change

Open **What if**. Select **04 · Prepare estimate**, set active time reduction to
**30%**, and keep waiting reduction at zero. Show the cards, then return to Overview.

“If preparing the estimate took 30% less active time, the model gives $127.38 per
case and $2,547.60 per month. The $202.40 difference is hypothetical, not a promise
of savings. My reviewed baseline remains unchanged. Actual corrections happen in
Workflow and require saving and recalculating.”

## 3:15 to 4:00 — How AI coding helped

Show the report's prompt and iteration section, then the GitHub commit history.

“I used Codex to plan and implement the app in stages: validated data, calculations,
review, an optional interview, and evidence-linked plans. I then asked for a premium
dashboard aimed at small-business owners. The written design came before the UI
changes. Tests and browser checks drove revisions, including percentage rounding,
chart clicks, and reopening the sidebar on small screens. Git preserves the original
working app and the tested redesign.”

## 4:00 to 4:30 — Verification and learning

Return to the app overview. End the recording before five minutes.

“The final offline suite passes 345 tests; three live-provider tests are opt-in and
skipped. My main lesson was to make inputs and calculations trustworthy before
polishing the interface, then test real interactions as well as code. This version
supports one sequential workflow in USD and temporary session data. Saved history
and production deployment are future work.”

## After recording

Play the recording back, check audio and duration, and obtain a reviewer-accessible
link. The handout requires the Google Doc, video, and GitHub code link in the course
form: https://forms.gle/VpQz7ZnsgL1bYRqv6. The handout states a deadline of
Sunday, October 11, 2026 at 11:59 PM Pacific Time and accepts late submissions through
the same form without Builder of the Week eligibility. Review access for both the
private repository and document before submitting. A localhost URL is not a public
deployment URL and is not a substitute for the video.
