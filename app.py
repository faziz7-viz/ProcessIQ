"""ProcessIQ: AI interview, owner fact review, and deterministic dashboard."""

from pathlib import Path
import time

from pydantic import ValidationError
import streamlit as st

from processiq.analysis import analyze_workflow
from processiq.assessment import FACT_FIELDS, apply_review, review_confirmations, review_values
from processiq.dashboard import render_dashboard
from processiq.csv_import import CsvImportError, parse_workflow_csv
from processiq.models import Workflow
from processiq.interview import InterviewSession, MAX_TURNS, MAX_MESSAGE_CHARS, FIRST_QUESTION, advance_interview, rewind_interview
from processiq.recommendations import generate_plan, workflow_fingerprint
from processiq.report import render_plan
from processiq.llm import InterviewError, OpenAIInterviewer, OpenAIPlanner

from processiq.presentation import interview_css, question_html, answer_hints, enhance_hints
from processiq.speech import transcribe_recording

DATA = Path(__file__).resolve().parent / "data"
DEMOS = {
    "Complete contractor demo": "contractor_estimate.json",
    "Incomplete contractor demo": "contractor_estimate_incomplete.json",
}
LABELS = {
    "active_time": "Active minutes / case",
    "waiting_time": "Waiting minutes / case",
    "people": "People working",
    "hourly_labor_cost": "Labor cost / person / hour (USD)",
}


def load_demo(name: str) -> None:
    st.session_state.workflow = Workflow.model_validate_json((DATA / DEMOS[name]).read_text())
    st.session_state.loaded_demo = name
    st.session_state.analysis = None
    st.session_state.analysis_snapshot = None
    st.session_state.plan = None
    st.session_state.dirty = False
    st.session_state.notice = ""
    st.session_state.interviewing = False
    st.session_state.show_start = False
    st.session_state.source_picker_return = False
    st.session_state.transcription_notice = ""
    st.session_state.interview_session = InterviewSession()
    st.session_state.review_backup = {}
    st.session_state.workflow_confirmed = True
    st.session_state.epoch = st.session_state.get("epoch", -1) + 1


def initialize_session() -> None:
    """Backfill state after code reloads without replacing the owner's work."""
    if "workflow" not in st.session_state:
        load_demo("Complete contractor demo")
        st.session_state.show_start = True
    defaults = {
        "loaded_demo": "Owner-described process" if st.session_state.workflow.data_kind == "owner_provided" else "Complete contractor demo",
        "analysis": None,
        "analysis_snapshot": None,
        "plan": None,
        "dirty": False,
        "notice": "",
        "epoch": 0,
        "interviewing": False,
        "show_start": False,
        "source_picker_return": False,
        "interview_answer_backup": {},
        "interview_session": InterviewSession(),
        "interview_epoch": 0,
        "review_backup": {},
        "workflow_confirmed": st.session_state.workflow.data_kind == "synthetic",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def choose_data_source() -> None:
    if not st.session_state.interviewing:
        backup_review()
    else:
        st.session_state.interview_answer_backup = {
            key: value for key, value in st.session_state.items() if key.startswith("interview-answer-")
        }
    st.session_state.show_start = True
    st.session_state.source_picker_return = True


def backup_review() -> None:
    prefix = f"editor-{st.session_state.epoch}."
    values = {key: value for key, value in st.session_state.items() if key.startswith(prefix)}
    if values:
        st.session_state.review_backup = values


def render_start() -> None:
    st.html(f"<style>{(DATA.parent / 'processiq/ui/start.css').read_text()}</style>")
    with st.sidebar:
        st.title("ProcessIQ")
        st.caption("WORKFLOW INTELLIGENCE")
        st.divider()
        st.write("**1 · Add your workflow**")
        st.caption("2 · Review your facts")
        st.caption("3 · Explore your dashboard")
        st.caption("4 · Choose your next improvement")
    with st.container(key="start-screen"):
        st.caption("A CLEARER VIEW OF YOUR BUSINESS")
        st.title("Choose how to get started")
        st.write("Upload your workflow, explore a sample, or talk it through.")
        choice = st.radio(
            "Choose a data source", ["Upload a CSV", "Use sample data", "AI interview (optional)"],
            captions=[
                "Bring your own steps, timing, and costs. Go straight to review.",
                "Explore a ready-made contractor workflow with synthetic data.",
                "Describe your work and let AI help you build a workflow.",
            ], label_visibility="collapsed", key="start-source", width="stretch",
        )
        if choice == "Upload a CSV":
            uploaded = st.file_uploader("Your workflow CSV", type=["csv"], max_upload_size=2)
            st.caption("One row per step, in order. Unknown values can stay blank. No interview required.")
            st.download_button("Download CSV template", data=(DATA / "workflow_template.csv").read_bytes(),
                               file_name="processiq_workflow_template.csv", mime="text/csv")
            with st.expander("What should my CSV include?"):
                st.write("Only **step_name** is required. Add **active_minutes**, **waiting_minutes**, **people**, **hourly_rate_usd**, **monthly_volume**, and **responsible_role** where known.")
                st.write("Time is per case, in minutes. Waiting is before that step. People work on that step; the rate is USD per person per hour. Monthly volume is cases for the whole workflow, not a separate frequency for each task.")
                st.caption("Optional: process_name, start_point, end_point, currency (USD). Repeat workflow details consistently or fill them on the first row only. The template contains fictional example values—replace them with your own. Maximum 200 steps, 2 MB; save as CSV UTF-8.")
            if st.button("Review uploaded data", type="primary", width="stretch", disabled=uploaded is None):
                try:
                    workflow = parse_workflow_csv(uploaded.getvalue(), filename=uploaded.name)
                except CsvImportError as exc:
                    st.error(str(exc))
                else:
                    st.session_state.update(
                        workflow=workflow, loaded_demo=f"CSV upload · {uploaded.name}",
                        workflow_confirmed=False, analysis=None, analysis_snapshot=None,
                        plan=None, dirty=False, interviewing=False, show_start=False,
                        source_picker_return=False, interview_session=InterviewSession(),
                        review_backup={}, notice="CSV loaded. Review and confirm your facts, then calculate your dashboard.",
                    )
                    st.session_state.epoch += 1
                    st.rerun()
        elif choice == "Use sample data":
            selected = st.selectbox("Sample workflow", list(DEMOS))
            st.caption("Synthetic examples work without an API key. Try the incomplete sample to see how unknowns are handled.")
            if st.button("Load selected demo", type="primary", width="stretch"):
                load_demo(selected)
                st.rerun()
        else:
            st.caption("Prefer a conversation? Answer at your own pace and review the extracted facts. This option uses your configured OpenAI API key.")
            if st.button("Start AI interview", type="primary", width="stretch"):
                start_interview()
                st.rerun()
        if st.session_state.source_picker_return and st.button("Return to saved process"):
            for key, value in st.session_state.review_backup.items():
                st.session_state[key] = value
            for key, value in st.session_state.interview_answer_backup.items():
                st.session_state[key] = value
            st.session_state.interview_answer_backup = {}
            st.session_state.show_start = False
            st.session_state.source_picker_return = False
            st.rerun()


def guard_saved_results() -> None:
    """Keep legacy sessions and results tied to the exact current workflow."""
    if st.session_state.analysis is None:
        st.session_state.plan = None
        return
    snapshot = workflow_fingerprint(st.session_state.workflow)
    if st.session_state.analysis_snapshot is None:
        # Older sessions have no fingerprint. Verify their analysis before reuse.
        if st.session_state.analysis == analyze_workflow(st.session_state.workflow):
            st.session_state.analysis_snapshot = snapshot
            return
    elif st.session_state.analysis_snapshot == snapshot:
        return
    st.session_state.analysis = None
    st.session_state.analysis_snapshot = None
    st.session_state.plan = None


def invalidate() -> None:
    st.session_state.dirty = True
    st.session_state.analysis = None
    st.session_state.plan = None
    st.session_state.notice = ""


def fact_changed(confirmation_key: str) -> None:
    st.session_state[confirmation_key] = False
    invalidate()


def numeric_input(path: str, label: str, prefix: str) -> None:
    key = prefix + path
    confirmation = prefix + "confirmed." + path
    st.text_input(label, key=key, on_change=fact_changed, args=(confirmation,))
    st.checkbox(
        "Confirmed", key=confirmation, disabled=not st.session_state[key].strip(),
        on_change=invalidate,
    )


def render_review(workflow: Workflow) -> None:
    prefix = f"editor-{st.session_state.epoch}."
    values = review_values(workflow)
    confirmations = review_confirmations(workflow)
    # Initialize only new epochs; ordinary reruns preserve the owner's pending edits.
    for path, value in values.items():
        st.session_state.setdefault(prefix + path, value)
    for path, value in confirmations.items():
        st.session_state.setdefault(prefix + "confirmed." + path, value)
    st.session_state.setdefault(prefix + "confirm_all", False)

    st.subheader("Review your process")
    st.caption("Blank means unknown. Time is in minutes. Costs are per person in USD. Editing a number clears its confirmation.")
    with st.expander("Process details", expanded=False):
        for path, label in (("name", "Process name"), ("start_point", "Process starts when"), ("end_point", "Process ends when")):
            st.text_input(label, key=prefix + path, on_change=invalidate)
    st.checkbox("This matches the workflow I want to assess", key="workflow_confirmed", on_change=invalidate)
    numeric_input("monthly_volume", "Cases per month", prefix)
    for step in workflow.steps:
        with st.expander(f"{step.order}. {step.name}", expanded=step.order == 1):
            left, right = st.columns(2)
            with left:
                st.text_input("Step name", key=prefix + f"steps.{step.id}.name", on_change=invalidate)
            with right:
                st.text_input("Responsible role", key=prefix + f"steps.{step.id}.responsible_role", on_change=invalidate)
            for column, field in zip(st.columns(4), FACT_FIELDS, strict=True):
                with column:
                    numeric_input(f"steps.{step.id}.{field}", LABELS[field], prefix)
    st.checkbox(
        "Confirm all provided values on save", key=prefix + "confirm_all", on_change=invalidate,
        help="Use after reviewing the provided values. Missing values remain unknown and unconfirmed.",
    )
    if st.button("Save reviewed facts", type="primary", width="stretch"):
        edited = {path: st.session_state[prefix + path] for path in values}
        reviewed = {path: st.session_state[prefix + "confirmed." + path] for path in confirmations}
        try:
            updated = apply_review(workflow, edited, reviewed, confirm_all=st.session_state[prefix + "confirm_all"])
        except ValidationError as exc:
            for error in exc.errors(include_url=False):
                location = ".".join(str(part) for part in error["loc"]) or "Review"
                st.error(f"{location}: {error['msg']}")
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.session_state.workflow = updated
            st.session_state.analysis = None
            st.session_state.plan = None
            st.session_state.dirty = False
            st.session_state.notice = "Facts saved. Calculate the dashboard to see the updated assessment."
            st.session_state.epoch += 1
            st.rerun()
    if st.session_state.dirty:
        st.warning("You have unsaved edits. Save reviewed facts before calculating. Previous results have been cleared.")
    if st.session_state.notice:
        st.success(st.session_state.notice)
    with st.expander("Source evidence (messages and CSV rows)"):
        for message in workflow.source_messages:
            st.text(f"{message.id}\n{message.text}")


def start_interview() -> None:
    if not st.session_state.interviewing:
        # Streamlit removes widget state when its screen is hidden. Keep pending
        # review values in ordinary session state until the owner returns.
        backup_review()
    st.session_state.interviewing = True
    st.session_state.show_start = False
    st.session_state.source_picker_return = False
    st.session_state.transcription_notice = ""
    st.session_state.interview_session = InterviewSession()
    st.session_state.interview_epoch = st.session_state.get("interview_epoch", 0) + 1
    st.session_state.analysis = None
    st.session_state.plan = None
    st.session_state.notice = ""


def interview_options() -> None:
    with st.container(key="interview-options"):
        with st.popover("Options", help="Privacy, examples, and interview controls"):
            st.button("Choose data source", on_click=choose_data_source, width="stretch")
            st.caption("Continue sends only your submitted answers to OpenAI. Examples in the empty field are hints, never your answers. Session data is temporary and may clear on refresh.")
            selected = st.radio("Synthetic examples", list(DEMOS))
            if st.button("Load selected demo", width="stretch"):
                load_demo(selected)
                st.rerun()
            if st.button("Restart AI interview", width="stretch"):
                start_interview()
                st.rerun()
            if st.button("Return to saved process", width="stretch"):
                for key, value in st.session_state.review_backup.items():
                    st.session_state[key] = value
                st.session_state.review_backup = {}
                st.session_state.interviewing = False
                st.rerun()


def leave_question() -> None:
    # The old prompt fades out, is removed by the rerun, then the next fades in.
    # Reduced-motion users see a direct replacement without animation.
    st.html("<style>.pi-question {animation:pi-leave 170ms forwards !important;} @media(prefers-reduced-motion:reduce){.pi-question{animation:none !important;}}</style>")
    time.sleep(0.18)


def render_interview() -> None:
    state = st.session_state.interview_session
    question = FIRST_QUESTION if not state.sources else state.question
    answer_key = f"interview-answer-{st.session_state.interview_epoch}-{len(state.sources)}"
    if answer_key not in st.session_state:
        st.session_state[answer_key] = st.session_state.pop("revised_answer", "")
    st.html(f"<style>{interview_css()}</style>")
    with st.container(key="interview-screen"):
        interview_options()
        with st.container(key="interview-stage"):
            st.html(question_html(question or ("Your draft is ready to review." if state.workflow else "Let's pause here.")))
            answer = ""
            if question:
                with st.container(key="interview-answer"):
                    field, voice = st.columns([1, .1], gap="small", vertical_alignment="center")
                    # Run the recorder before the text widget so transcription can
                    # populate that widget before it is instantiated on this rerun.
                    with voice, st.container(key="interview-voice"):
                        with st.popover("Record an answer", icon=":material/mic:", help="Speak, then review your words", width="stretch"):
                            st.write("Speak your answer")
                            st.caption("Tap the microphone below to record. Stop when finished. Transcribe sends this recording to OpenAI for speech-to-text using your configured account. Review and edit the words before choosing Continue. Nothing is submitted as an answer automatically.")
                            recording = st.audio_input("Record up to two minutes", key=f"audio-{answer_key}", sample_rate=16000)
                            st.caption("If permission is denied, keep typing or enable microphone access for this local site in your browser.")
                            if recording is not None and st.button("Transcribe recording", key=f"transcribe-{answer_key}"):
                                try:
                                    with st.spinner("Transcribing your recording…"):
                                        transcript = transcribe_recording(recording.getvalue())
                                except InterviewError as exc:
                                    st.error(str(exc))
                                else:
                                    st.session_state[answer_key] = transcript
                                    st.session_state.transcription_notice = "Your words are ready. Edit them, then choose Continue."
                                    st.rerun()
                    with field:
                        answer = st.text_input("Your answer", key=answer_key, max_chars=MAX_MESSAGE_CHARS,
                                               placeholder=answer_hints(state)[0], label_visibility="collapsed")
                enhance_hints(state)
                if st.session_state.get("transcription_notice"):
                    st.caption(st.session_state.transcription_notice)
            else:
                st.write("You can complete unknown details in review, or go back to revise an answer." if state.workflow else "We haven't identified a clear workflow yet. Go back or restart from Options with one concrete activity from your day.")
            with st.container(horizontal=True, horizontal_alignment="center", key="interview-actions"):
                if state.sources and st.button("Back"):
                    st.session_state.revised_answer = state.sources[-1].text
                    st.session_state.interview_session = rewind_interview(state)
                    st.session_state.interview_epoch += 1
                    st.session_state.transcription_notice = ""
                    st.session_state.analysis = None
                    st.session_state.plan = None
                    leave_question()
                    st.rerun()
                unsure = st.button("Not sure") if question else False
                continuing = st.button("Continue", type="primary", icon=":material/arrow_forward:") if question else False
            if continuing or unsure:
                if continuing and not answer.strip():
                    st.info("Add a detail, or choose Not sure.")
                else:
                    try:
                        with st.spinner("Choosing your next question…"):
                            updated = advance_interview(state, "Not sure" if unsure else answer, OpenAIInterviewer())
                    except InterviewError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state.interview_session = updated
                        st.session_state.transcription_notice = ""
                        st.session_state.analysis = None
                        st.session_state.plan = None
                        leave_question()
                        st.rerun()
            if state.workflow:
                with st.container(key="interview-finish", horizontal=True, horizontal_alignment="center"):
                    finish = st.button("Finish & review", help="Check your workflow and confirm its facts before calculating.")
                if finish:
                    st.session_state.workflow = state.workflow
                    st.session_state.review_backup = {}
                    st.session_state.loaded_demo = "Owner-described process"
                    st.session_state.interviewing = False
                    st.session_state.workflow_confirmed = False
                    st.session_state.dirty = False
                    st.session_state.analysis = None
                    st.session_state.plan = None
                    st.session_state.notice = "Check the discovered workflow, then confirm only the facts you know."
                    st.session_state.epoch += 1
                    st.rerun()


def render_plan_controls() -> None:
    if st.session_state.plan is not None and st.session_state.plan.snapshot != workflow_fingerprint(st.session_state.workflow):
        st.session_state.plan = None
    st.divider()
    st.subheader("Turn findings into actions")
    st.caption("Generate AI plan sends the saved assessment and its evidence to OpenAI. The offline option works without an API key. Every displayed number stays calculated by Python.")
    offline, live = st.columns(2)
    create_offline = offline.button("Create offline plan", width="stretch", disabled=st.session_state.dirty)
    create_live = live.button("Generate AI plan", type="primary", width="stretch", disabled=st.session_state.dirty)
    if create_offline or create_live:
        try:
            with st.spinner("Preparing your improvement plan..."):
                plan = generate_plan(st.session_state.workflow, OpenAIPlanner() if create_live else None)
        except InterviewError as exc:
            st.error(str(exc))
        except (ValidationError, ValueError, TypeError):
            st.error("The AI plan did not pass evidence checks. Your saved facts and any existing plan were preserved. Try again or create an offline plan.")
        else:
            st.session_state.plan = plan
    if st.session_state.plan is not None:
        render_plan(st.session_state.plan)


def main() -> None:
    st.set_page_config(page_title="ProcessIQ | Process assessment", page_icon="🔎", layout="wide")
    initialize_session()
    guard_saved_results()
    if st.session_state.show_start:
        render_start()
        return
    if st.session_state.interviewing:
        render_interview()
        return
    st.html("""<style>
    .stMainBlockContainer {max-width: 1180px; padding-top: 3rem; padding-bottom: 3rem;}
    h1 {letter-spacing: -.035em;} h3 {letter-spacing: -.015em;}
    [data-testid="stVerticalBlockBorderWrapper"] {background: white; border-radius: 16px;}
    [data-testid="stMetric"] {background: white; border: 1px solid #E0E9E5; padding: 18px; border-radius: 14px;}
    [data-testid="stMetricValue"] {font-size: clamp(1.4rem, 2.6vw, 2rem);}
    .stButton button {border-radius: 10px; min-height: 44px;}
    [data-testid="stExpander"] {background: white; border-radius: 12px;}
    [data-testid="stCaptionContainer"] {color: #516967;}
    @media (max-width: 700px) {
      .stMainBlockContainer {padding: 1.4rem 1rem;}
      [data-testid="stHorizontalBlock"] {flex-wrap: wrap; gap: .7rem;}
      [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {min-width: min(100%, 240px); flex: 1 1 240px;}
      [data-testid="stMetricValue"] {font-size: 1.8rem;}
      h1 {font-size: 2rem;} h3 {font-size: 1.25rem;}
    }
    </style>""")
    with st.sidebar:
        st.title("ProcessIQ")
        st.caption("Understand your process. Find your next improvement.")
        st.button("Choose data source", on_click=choose_data_source, width="stretch")
        if st.button("Start AI interview", type="primary", width="stretch"):
            start_interview()
            st.rerun()
        selected = st.radio("Synthetic examples", list(DEMOS))
        if st.button("Load selected demo", width="stretch"):
            load_demo(selected)
            st.rerun()
        if st.session_state.loaded_demo in DEMOS:
            if st.button("Reset current demo", width="stretch"):
                load_demo(st.session_state.loaded_demo)
                st.rerun()
        st.divider()
        st.caption("Week 1 course demo · Interview, assessment & improvement plan")
        st.caption("One sequential workflow. Session data is temporary; a refresh may clear edits.")
    st.title("Your workflow, made clear")
    st.caption("Review → Dashboard → Action plan")
    kind = "Synthetic course demo" if st.session_state.workflow.data_kind == "synthetic" else "Owner-provided draft"
    st.info(f"{kind} · {st.session_state.loaded_demo}")
    render_review(st.session_state.workflow)
    st.divider()
    if st.button("Calculate dashboard", disabled=st.session_state.dirty or not st.session_state.workflow_confirmed, type="primary", width="stretch"):
        st.session_state.plan = None
        st.session_state.analysis = analyze_workflow(st.session_state.workflow)
        st.session_state.analysis_snapshot = workflow_fingerprint(st.session_state.workflow)
    if st.session_state.analysis is not None:
        render_dashboard(st.session_state.analysis)
        render_plan_controls()
    else:
        st.caption("Your dashboard will appear here after you calculate the saved facts. Incomplete inputs are supported.")


if __name__ == "__main__":
    main()
