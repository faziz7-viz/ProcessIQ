"""An evidence-led process explorer; chart floats are presentation values only."""

from collections.abc import Iterable, Mapping
from decimal import Decimal
from functools import partial
from html import escape
from typing import Literal

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from processiq.insights import blocker_labels, decimal_text, hero_insight, human_duration, ranking_insight
from processiq.models import AnalysisMetric, StepAnalysis, Workflow, WorkflowAnalysis

FOREST = "#315C49"
AMBER = "#B87928"


def _format(value: Decimal, money: bool = False) -> str:
    return f"${value:,.2f}" if money else decimal_text(value)


def format_metric(metric: AnalysisMetric) -> str:
    return "Unavailable" if metric.value is None else _format(metric.value, metric.unit.startswith("USD/"))


def step_table(analysis: WorkflowAnalysis) -> pd.DataFrame:
    return pd.DataFrame([
        {"Step": step.name, "Active (min)": format_metric(step.active_minutes),
         "Waiting (min)": format_metric(step.waiting_minutes),
         "Elapsed (min)": format_metric(step.elapsed_minutes),
         "Labor (person-min)": format_metric(step.labor_minutes),
         "Labor cost (USD)": format_metric(step.labor_cost)}
        for step in analysis.steps
    ])


def build_charts(
    analysis: WorkflowAnalysis, *, sort_by: Literal["process", "contribution"] = "process",
    time_mode: Literal["combined", "active", "waiting"] = "combined",
    step_ids: Iterable[str] | None = None, selected_step_id: str | None = None,
) -> dict[str, go.Figure]:
    """Build three compatible lenses, preserving unknowns and stable step IDs."""
    included = None if step_ids is None else set(step_ids)
    steps = [step for step in analysis.steps if included is None or step.step_id in included]
    positions = {step.step_id: number for number, step in enumerate(analysis.steps, 1)}
    traces = {
        "time": [("Active", "active_minutes", FOREST), ("Waiting", "waiting_minutes", AMBER)],
        "labor": [("Labor effort", "labor_minutes", FOREST)],
        "cost": [("Labor cost", "labor_cost", FOREST)],
    }
    if time_mode != "combined":
        traces["time"] = [trace for trace in traces["time"] if trace[1] == f"{time_mode}_minutes"]
    contribution_fields = {"time": "elapsed_minutes" if time_mode == "combined" else f"{time_mode}_minutes",
                           "labor": "labor_minutes", "cost": "labor_cost"}
    units = {"time": "Minutes per case", "labor": "Person-minutes per case", "cost": "USD per case"}
    charts = {}
    for key, series in traces.items():
        ordered = list(steps)
        if sort_by == "contribution":
            # Known zero still precedes unavailable. Stable sort preserves tied process order.
            ordered.sort(key=lambda step: (
                getattr(step, contribution_fields[key]).value is not None,
                getattr(step, contribution_fields[key]).value or Decimal(0),
            ), reverse=True)
        ids = [step.step_id for step in ordered]
        full_labels = [f"{positions[step.step_id]}. {step.name}" for step in ordered]
        tick_labels = [escape(label if len(label) <= 44 else label[:41] + "…") for label in full_labels]
        figure = go.Figure()
        for label, field, color in series:
            metrics = [getattr(step, field) for step in ordered]
            figure.add_trace(go.Bar(
                name=label, y=ids, text=[escape(label) for label in full_labels], textposition="none",
                x=[None if metric.value is None else float(metric.value) for metric in metrics],
                customdata=[[step.step_id, format_metric(metric)] for step, metric in zip(ordered, metrics, strict=True)],
                orientation="h", marker=dict(color=color, cornerradius=5),
                selectedpoints=[index for index, step in enumerate(ordered) if step.step_id == selected_step_id]
                if selected_step_id in ids else None,
                selected=dict(marker=dict(opacity=1)), unselected=dict(marker=dict(opacity=.58)),
                hovertemplate="%{text}<br>%{customdata[1]}<extra>%{fullData.name}</extra>",
            ))
        figure.update_layout(
            barmode="stack", bargap=.42, height=max(300, len(ordered) * 42 + 100),
            margin=dict(l=4, r=28, t=45, b=40), xaxis_title=units[key],
            xaxis=dict(gridcolor="#E1E6DF", zeroline=False, fixedrange=True, rangemode="tozero"),
            yaxis=dict(autorange="reversed", tickmode="array", tickvals=ids, ticktext=tick_labels,
                       automargin=True, fixedrange=True, showgrid=False),
            legend=dict(orientation="h", y=1.13, x=0, font=dict(size=12)),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(family="Geist, sans-serif", size=12, color="#202824"),
            hoverlabel=dict(bgcolor="white", font=dict(family="Geist, sans-serif", color="#202824")),
            clickmode="event+select", dragmode=False,
        )
        charts[key] = figure
    return charts


def selected_step_from_event(event: Mapping, analysis: WorkflowAnalysis) -> str | None:
    """Validate IDs returned by a chart; labels and indexes never identify steps."""
    points = event.get("selection", {}).get("points", [])
    known_ids = {step.step_id for step in analysis.steps}
    for point in reversed(points):
        custom = point.get("customdata", [])
        if isinstance(custom, (list, tuple)) and custom and custom[0] in known_ids:
            return custom[0]
        if point.get("y") in known_ids:
            return point["y"]
    return None


def _select_chart_step(chart_key: str, analysis: WorkflowAnalysis) -> None:
    selected = selected_step_from_event(st.session_state.get(chart_key, {}), analysis)
    if selected is not None:
        st.session_state["pi-selected-step"] = selected


def _select_picker_step() -> None:
    st.session_state["pi-selected-step"] = st.session_state["pi-step-picker"]


def hero_html(analysis: WorkflowAnalysis) -> str:
    finding = hero_insight(analysis)
    kind = "Synthetic example" if analysis.data_kind == "synthetic" else "Owner-provided facts"
    return (
        '<section class="pi-hero" aria-label="Process insight">'
        f'<p class="pi-eyebrow">THE BIG PICTURE · {escape(analysis.workflow_name)}</p>'
        f'<h2 class="pi-hero-title">{escape(finding.title)}</h2>'
        f'<p class="pi-hero-copy">{escape(finding.description)}</p>'
        f'<span class="pi-chip">{escape(kind)}</span> '
        '<span class="pi-chip">One representative case</span>'
        '</section>'
    )


def _subtotal(metric: AnalysisMetric) -> None:
    if metric.known_subtotal is not None:
        subtotal = _format(metric.known_subtotal, metric.unit.startswith("USD/"))
        st.caption(f"Known subtotal only: {subtotal} {metric.unit}")


def _render_metrics(analysis: WorkflowAnalysis, workflow: Workflow | None) -> list[tuple[str, AnalysisMetric]]:
    primary = [
        ("Elapsed minutes / case", analysis.total_elapsed_minutes),
        ("Labor cost / case", analysis.labor_cost_per_case),
        ("Projected labor cost / month", analysis.monthly_labor_cost),
    ]
    captions = ["From process start to finish", "Active work × people × hourly rate", "At the recorded monthly volume"]
    if workflow is not None and workflow.monthly_volume.confirmed:
        captions[2] = f"At {workflow.monthly_volume.value:,} cases per month"
    for index, (column, (label, metric)) in enumerate(zip(st.columns(3), primary, strict=True)):
        with column, st.container(border=True, key=f"pi-primary-{index}"):
            value = human_duration(metric.value) if index == 0 else format_metric(metric)
            st.metric(label, value)
            st.caption(f"{format_metric(metric)} minutes · 24-hour days" if index == 0 and metric.value is not None else captions[index])
            _subtotal(metric)
    secondary = [
        ("Active minutes / case", analysis.total_active_minutes),
        ("Waiting minutes / case", analysis.total_waiting_minutes),
        ("Labor person-min / case", analysis.total_labor_minutes),
    ]
    for index, (column, (label, metric)) in enumerate(zip(st.columns(3), secondary, strict=True)):
        with column, st.container(key=f"pi-secondary-{index}"):
            st.metric(label, format_metric(metric))
            _subtotal(metric)
    st.caption("Calculated from saved, confirmed facts. Waiting adds elapsed time, not labor expense. "
               "Monthly cost is a projection; costs exclude materials and overhead.")
    return primary + secondary


def _render_step_detail(step: StepAnalysis, analysis: WorkflowAnalysis, workflow: Workflow | None) -> None:
    number = next(index for index, item in enumerate(analysis.steps, 1) if item.step_id == step.step_id)
    original = next((item for item in workflow.steps if item.id == step.step_id), None) if workflow else None
    with st.container(border=True, key="pi-step-detail"):
        st.markdown('<p class="pi-eyebrow">STEP DETAIL</p>', unsafe_allow_html=True)
        st.markdown(f'<h3>{number}. {escape(step.name)}</h3>', unsafe_allow_html=True)
        role = original.responsible_role if original and original.responsible_role else "Role not recorded"
        st.markdown(f'<p class="pi-note">{escape(role)}</p>', unsafe_allow_html=True)
        values = [("Active time", step.active_minutes), ("Waiting before this step", step.waiting_minutes),
                  ("Labor cost", step.labor_cost)]
        for column, (label, metric) in zip(st.columns(3), values, strict=True):
            with column:
                st.metric(label, format_metric(metric) + (" min" if metric.value is not None and metric.unit == "minutes" else ""))
        st.caption(f"Elapsed: {format_metric(step.elapsed_minutes)} min · "
                   f"Labor effort: {format_metric(step.labor_minutes)} person-minutes")
        blockers = tuple(dict.fromkeys(gap for _, metric in values for gap in metric.blocked_by))
        if blockers:
            st.info("Complete or confirm these facts to calculate this step.")
            for label in blocker_labels(blockers, analysis):
                st.text(label)
        evidence = tuple(dict.fromkeys(item for _, metric in values for item in metric.evidence))
        st.markdown('<p class="pi-stat-label">Quoted source</p>', unsafe_allow_html=True)
        if evidence:
            for item in evidence:
                st.markdown(f'<blockquote class="pi-note">“{escape(item.quote)}”</blockquote>', unsafe_allow_html=True)
        else:
            st.caption("No confirmed numeric source is available for this step yet.")
        with st.expander("How this step is calculated"):
            st.write("Elapsed time = active time + waiting before this step. Labor effort = active minutes × people working. "
                     "Labor cost = active minutes × people × hourly labor cost ÷ 60, rounded half up to cents.")
            if original:
                people = str(original.people.value) if original.people.confirmed else "Unavailable"
                rate = f"${original.hourly_labor_cost.value:,.2f}" if original.hourly_labor_cost.confirmed else "Unavailable"
                st.caption(f"People working: {people} · Hourly labor cost per person: {rate}")
            for label, metric in values:
                st.caption(label)
                st.code(metric.formula, language=None)


def render_dashboard(analysis: WorkflowAnalysis, workflow: Workflow | None = None) -> str | None:
    st.markdown(hero_html(analysis), unsafe_allow_html=True)
    metrics = _render_metrics(analysis, workflow)
    gaps = tuple(dict.fromkeys(gap for _, metric in metrics for gap in metric.blocked_by))
    if gaps:
        st.warning("Some totals are unavailable. Missing or unconfirmed inputs are not treated as zero.")
        with st.expander(f"Facts to complete or confirm ({len(gaps)})"):
            for label in blocker_labels(gaps, analysis):
                st.text(label)

    st.markdown('<div class="pi-section-intro"><p class="pi-eyebrow">FOLLOW THE WORK</p>'
                '<h2>Where each step adds up</h2>'
                '<p class="pi-note">Compare time, effort, and cost. Select a bar or choose a step to see the facts behind it.</p></div>',
                unsafe_allow_html=True)
    for column, lens, label in zip(st.columns(2), ("waiting", "labor"), ("Largest wait", "Largest labor demand"), strict=True):
        with column, st.container(border=True, key=f"pi-ranking-{lens}"):
            st.markdown(f'<p class="pi-stat-label">{label}</p><p class="pi-note">{escape(ranking_insight(analysis, lens))}</p>',
                        unsafe_allow_html=True)
    st.caption("These are contribution comparisons, not proof of a capacity limit or its cause.")

    ids = [step.step_id for step in analysis.steps]
    names = {step.step_id: f"{number}. {step.name}" for number, step in enumerate(analysis.steps, 1)}
    if st.session_state.get("pi-selected-step") not in ids:
        st.session_state["pi-selected-step"] = analysis.waiting_ranking.entries[0].step_id if analysis.waiting_ranking.entries else ids[0]
    st.session_state["pi-step-picker"] = st.session_state["pi-selected-step"]
    sort_column, step_column = st.columns([1, 2])
    with sort_column:
        sort = st.selectbox("Order steps", ["Process order", "Largest contribution"], key="pi-chart-sort")
    with step_column:
        st.selectbox("Inspect a step", ids, format_func=names.get, key="pi-step-picker", on_change=_select_picker_step)
    selected = st.session_state["pi-selected-step"]
    filtered = ids
    if len(ids) > 12:
        query = st.text_input("Find steps in the charts", placeholder="Search by step name or number", key="pi-chart-search")
        filtered = [step_id for step_id in ids if query.casefold() in names[step_id].casefold()]
        st.caption(f"Showing {len(filtered)} of {len(ids)} steps. Scroll within the chart to explore.")
    time_tab, labor_tab, cost_tab = st.tabs(["Time", "Labor effort", "Labor cost"])
    with time_tab:
        mode = st.radio("Time shown", ["Active + waiting", "Active only", "Waiting only"], horizontal=True, key="pi-time-mode")
    charts = build_charts(analysis, sort_by="contribution" if sort == "Largest contribution" else "process",
                          time_mode={"Active + waiting": "combined", "Active only": "active", "Waiting only": "waiting"}[mode],
                          step_ids=filtered, selected_step_id=selected)
    for tab, key in ((time_tab, "time"), (labor_tab, "labor"), (cost_tab, "cost")):
        with tab:
            if not filtered:
                st.info("No steps match that search. Clear it to see the process again.")
            with st.container(height=520 if len(filtered) > 10 else "content", border=False):
                st.plotly_chart(charts[key], width="stretch", theme=None, key=f"chart-{key}",
                                on_select=partial(_select_chart_step, f"chart-{key}", analysis), selection_mode="points",
                                config={"displayModeBar": False, "scrollZoom": False, "responsive": True},
                                alt=f"{key.title()} contribution by process step. Use Inspect a step for exact values and source evidence.")
            st.caption("Blank bars mean unavailable inputs. A recorded zero is still zero. Hover for exact values.")
    _render_step_detail(next(step for step in analysis.steps if step.step_id == selected), analysis, workflow)
    with st.expander("All steps · exact values"):
        st.dataframe(step_table(analysis), hide_index=True, width="stretch")
    with st.expander("Whole-process formulas and evidence"):
        st.caption("Step labor costs are rounded half up to cents, then summed and multiplied by confirmed monthly case volume.")
        for label, metric in metrics:
            st.write(f"{label}: {format_metric(metric)}")
            st.code(metric.formula, language=None)
            for item in metric.evidence:
                st.text(f"{item.message_id}: {item.quote}")
    st.markdown('<div class="pi-section-intro"><p class="pi-eyebrow">YOUR NEXT MOVE</p>'
                '<h3>Turn the findings into a small experiment.</h3>'
                '<p class="pi-note">Open Improvements for an evidence-linked action plan, '
                'or What if to explore a change before trying it.</p></div>', unsafe_allow_html=True)
    return selected
