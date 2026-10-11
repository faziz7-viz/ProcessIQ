"""Dashboard rendering; chart floats are presentation values, never financial inputs."""

from decimal import Decimal

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from processiq.models import AnalysisMetric, WorkflowAnalysis


def _format(value: Decimal, money: bool = False) -> str:
    if money:
        return f"${value:,.2f}"
    return format(value, ",f").rstrip("0").rstrip(".") if value.as_tuple().exponent < 0 else f"{value:,}"


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


def build_charts(analysis: WorkflowAnalysis) -> dict[str, go.Figure]:
    step_ids = [step.step_id for step in analysis.steps]
    labels = [f"{index}. {step.name}" for index, step in enumerate(analysis.steps, start=1)]
    charts = {}
    series = {
        "time": [("Active", "active_minutes", "#087F8C"), ("Waiting", "waiting_minutes", "#C58332")],
        "labor": [("Labor effort", "labor_minutes", "#087F8C")],
        "cost": [("Labor cost", "labor_cost", "#087F8C")],
    }
    units = {"time": "Minutes per case", "labor": "Person-minutes per case", "cost": "USD per case"}
    for key, traces in series.items():
        figure = go.Figure()
        for label, field, color in traces:
            metrics = [getattr(step, field) for step in analysis.steps]
            figure.add_trace(go.Bar(
                name=label, y=step_ids, text=labels, textposition="none",
                x=[None if metric.value is None else float(metric.value) for metric in metrics],
                customdata=[format_metric(metric) for metric in metrics], orientation="h",
                marker_color=color, hovertemplate="%{text}<br>%{customdata}<extra>%{fullData.name}</extra>",
            ))
        figure.update_layout(
            barmode="stack", height=340, margin=dict(l=10, r=20, t=20, b=30),
            xaxis_title=units[key],
            yaxis=dict(autorange="reversed", tickmode="array", tickvals=step_ids, ticktext=labels),
            legend=dict(orientation="h", y=1.12), paper_bgcolor="rgba(0,0,0,0)",
        )
        charts[key] = figure
    return charts


def render_dashboard(analysis: WorkflowAnalysis) -> None:
    st.subheader("Your process at a glance")
    kind = "Synthetic demo data" if analysis.data_kind == "synthetic" else "Owner-provided data"
    st.caption(f"Calculated from saved, confirmed facts. {kind} · USD · One sequential process")
    metrics = [
        ("Active minutes / case", analysis.total_active_minutes),
        ("Waiting minutes / case", analysis.total_waiting_minutes),
        ("Elapsed minutes / case", analysis.total_elapsed_minutes),
        ("Labor person-min / case", analysis.total_labor_minutes),
        ("Labor cost / case", analysis.labor_cost_per_case),
        ("Projected labor cost / month", analysis.monthly_labor_cost),
    ]
    for offset in (0, 3):
        for column, (label, metric) in zip(st.columns(3), metrics[offset:offset + 3], strict=True):
            with column:
                st.metric(label, format_metric(metric))
                if metric.known_subtotal is not None:
                    subtotal = _format(metric.known_subtotal, metric.unit.startswith("USD/"))
                    st.caption(f"Known subtotal only: {subtotal} {metric.unit}")
    gaps = {gap.path: gap.reason for _, metric in metrics for gap in metric.blocked_by}
    if gaps:
        st.warning("Some totals are unavailable. Missing or unconfirmed inputs are not treated as zero.")
        with st.expander(f"Facts to complete or confirm ({len(gaps)})", expanded=True):
            st.dataframe(pd.DataFrame([{"Fact": path, "Status": reason} for path, reason in gaps.items()]), hide_index=True, width="stretch")
    st.caption("Elapsed time includes waits, nights, and weekends. Waiting does not add labor expense. Costs exclude materials and overhead.")
    time_tab, labor_tab, cost_tab = st.tabs(["Elapsed time", "Labor effort", "Labor cost"])
    charts = build_charts(analysis)
    for tab, key in ((time_tab, "time"), (labor_tab, "labor"), (cost_tab, "cost")):
        with tab:
            st.plotly_chart(charts[key], width="stretch", key=f"chart-{key}")
            st.caption("Blank bars mean unavailable inputs. Hover for the calculated value; exact values appear in the table below.")
    st.dataframe(step_table(analysis), hide_index=True, width="stretch")
    st.subheader("Potential bottleneck indicators")
    names = {step.step_id: step.name for step in analysis.steps}
    for column, ranking in zip(st.columns(2), (analysis.waiting_ranking, analysis.labor_ranking), strict=True):
        with column:
            st.caption(ranking.description)
            if ranking.entries:
                st.dataframe(pd.DataFrame([
                    {"Rank": entry.rank, "Step": names[entry.step_id], ranking.unit: _format(entry.value)}
                    for entry in ranking.entries
                ]), hide_index=True, width="stretch")
            else:
                st.info("No positive confirmed contributors to compare yet.")
    with st.expander("Calculation evidence and formulas"):
        st.caption("Money rounds half up to cents per step, then step costs are summed and scaled by monthly volume.")
        for label, metric in metrics:
            st.write(f"**{label}: {format_metric(metric)}**")
            st.code(metric.formula, language=None)
            for evidence in metric.evidence:
                st.text(f"{evidence.message_id}: {evidence.quote}")
