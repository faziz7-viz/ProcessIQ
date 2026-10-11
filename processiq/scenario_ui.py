"""A reversible what-if workspace with an unchanged reviewed baseline."""

from decimal import Decimal
import hashlib
from html import escape

import streamlit as st

from processiq.dashboard import format_metric
from processiq.models import AnalysisMetric, Workflow, WorkflowAnalysis
from processiq.scenarios import calculate_scenario

_STEP = "scenario.step_id"
_ACTIVE = "scenario.active_reduction"
_WAITING = "scenario.waiting_reduction"
_SNAPSHOT = "scenario.snapshot"


def _reset_reductions() -> None:
    st.session_state[_ACTIVE] = 0
    st.session_state[_WAITING] = 0


def _delta_label(value: Decimal | None, *, money: bool = False) -> str | None:
    if value is None:
        return None
    if value == 0:
        return "No change"
    if money:
        return f"-${value:,.2f} vs baseline"
    amount = f"{value:,f}"
    if "." in amount:
        amount = amount.rstrip("0").rstrip(".")
    return f"-{amount} min vs baseline"


def _partial_note(metric: AnalysisMetric) -> str:
    if metric.value is not None:
        return ""
    if metric.known_subtotal is None:
        return "Required facts are missing or unconfirmed."
    amount = format_metric(metric.model_copy(update={"value": metric.known_subtotal}))
    return f"Known steps only: {amount} {metric.unit}. A full total is unavailable."


def render_scenarios(workflow: Workflow, analysis: WorkflowAnalysis) -> None:
    """Render controls scoped to the current workflow, without changing facts."""
    snapshot = hashlib.sha256(workflow.model_dump_json().encode()).hexdigest()
    if st.session_state.get(_SNAPSHOT) != snapshot:
        for key in (_STEP, _ACTIVE, _WAITING):
            st.session_state.pop(key, None)
        st.session_state[_SNAPSHOT] = snapshot

    st.markdown('<p class="pi-eyebrow">EXPLORE A POSSIBILITY</p>', unsafe_allow_html=True)
    st.subheader("What if one step took less time?")
    st.caption("Hypothetical scenario · Explore an assumption before you choose a small trial.")

    with st.container(border=True, key="pi-scenario-controls"):
        labels = {step.id: f"{step.order:02d} · {step.name}" for step in workflow.steps}
        selected = st.selectbox("Step to explore", options=list(labels), format_func=labels.get, key=_STEP)
        selected_baseline = next((step for step in analysis.steps if step.step_id == selected), None)
        st.markdown(
            f'<p class="pi-note">Adjust the assumption for <strong>{escape(labels[selected])}</strong>.</p>',
            unsafe_allow_html=True,
        )
        active_col, waiting_col = st.columns(2)
        with active_col:
            active = st.slider("Active time reduction", 0, 100, 0, step=5, format="%d%%", key=_ACTIVE,
                               help="Less time actively working. Staffing and hourly labor cost stay the same.")
            if selected_baseline:
                st.caption(f"Reviewed active time: {format_metric(selected_baseline.active_minutes)} min / case")
        with waiting_col:
            waiting = st.slider("Wait before step reduction", 0, 100, 0, step=5, format="%d%%", key=_WAITING,
                                help="Less elapsed time before work begins, including nights and weekends. Waiting is not labor cost.")
            if selected_baseline:
                st.caption(f"Reviewed wait before step: {format_metric(selected_baseline.waiting_minutes)} min / case")
        st.button("Reset scenario", on_click=_reset_reductions, key="scenario.reset")

    result = calculate_scenario(workflow, selected, active_reduction_pct=active, waiting_reduction_pct=waiting)
    st.markdown('<p class="pi-eyebrow">BASELINE → HYPOTHETICAL</p>', unsafe_allow_html=True)
    comparison_specs = (
        ("total_elapsed_minutes", "Hypothetical elapsed / case", False),
        ("labor_cost_per_case", "Hypothetical labor / case", True),
        ("monthly_labor_cost", "Hypothetical monthly labor", True),
    )
    for column, (attribute, label, money) in zip(st.columns(3), comparison_specs, strict=True):
        baseline = getattr(result.baseline, attribute)
        hypothetical = getattr(result.hypothetical, attribute)
        with column, st.container(border=True, key=f"pi-scenario-comparison-{attribute}"):
            baseline_suffix = " min" if not money and baseline.value is not None else ""
            hypothetical_suffix = " min" if not money and hypothetical.value is not None else ""
            st.caption(f"Baseline · {format_metric(baseline)}{baseline_suffix}")
            st.metric(label, format_metric(hypothetical) + hypothetical_suffix,
                      delta=_delta_label(getattr(result.delta, attribute), money=money), delta_color="inverse")
            note = _partial_note(hypothetical)
            if note:
                st.caption(note)

    volume = workflow.monthly_volume
    if volume.value is not None and volume.confirmed:
        st.caption(f"Monthly projection assumes the same {volume.value:,} cases per month, staffing and hourly labor costs. Materials and overhead are excluded.")
    else:
        st.caption("A monthly projection needs confirmed monthly case volume and complete labor-cost inputs. Materials and overhead are excluded.")
    st.markdown(
        '<p class="pi-note">These are assumed changes to one representative case. '
        'Your reviewed facts stay unchanged. A shorter wait changes elapsed time; '
        'it does not reduce labor cost. Projected differences are not realized savings.</p>',
        unsafe_allow_html=True,
    )
    with st.expander("Compare exact scenario values"):
        rows = []
        for attribute, label in (
            ("total_active_minutes", "Active time / case"),
            ("total_waiting_minutes", "Waiting / case"),
            ("total_elapsed_minutes", "Elapsed time / case"),
            ("total_labor_minutes", "Labor effort / case"),
            ("labor_cost_per_case", "Labor cost / case"),
            ("monthly_labor_cost", "Projected monthly labor"),
        ):
            baseline = getattr(result.baseline, attribute)
            hypothetical = getattr(result.hypothetical, attribute)
            delta = getattr(result.delta, attribute)
            rows.append({
                "Measure": label, "Unit": baseline.unit,
                "Baseline": format_metric(baseline), "Hypothetical": format_metric(hypothetical),
                "Assumed reduction": "Unavailable" if delta is None else format_metric(baseline.model_copy(update={"value": delta})),
            })
        st.dataframe(rows, hide_index=True, width="stretch")
        st.caption("Costs are recalculated and rounded half up to cents for each step before summing. Unknown inputs remain unknown, even with a 100% reduction.")
