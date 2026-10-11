"""Present the verified report; AI selections never become free-form claims."""

from html import escape

import streamlit as st

from processiq.recommendations import Finding, ImprovementPlan


def render_evidence(finding: Finding) -> None:
    with st.expander(f'Evidence: {finding.title}'):
        if finding.metric:
            st.caption('Calculation rule')
            st.text(finding.metric.formula)
        for path in finding.input_paths:
            st.text(f'Input: {path}')
        for gap in finding.blocked_by:
            st.text(f'Needs review: {gap.path} ({gap.reason})')
        for source in finding.evidence:
            st.text(f'{source.message_id}: {source.quote}')
        if not finding.evidence:
            st.caption('This finding describes assessment gaps or an absence of positive confirmed contributors; it supplies no new numeric estimate.')


def render_plan(plan: ImprovementPlan) -> None:
    st.markdown('<p class="pi-eyebrow">FROM INSIGHT TO ACTION</p>', unsafe_allow_html=True)
    st.subheader('Your improvement plan')
    st.caption('AI-prioritized plan' if plan.mode == 'ai' else 'Rule-based offline plan · No AI request')
    st.caption('Choose a small trial with your team. Suggested owners and effort are starting points to agree together; no hours or implementation costs are estimated.')
    with st.expander('What the numbers mean'):
        for finding in plan.summary:
            st.text(finding.explanation)
            render_evidence(finding)
    st.subheader('Suggested actions in priority order')
    for priority, action in enumerate(plan.actions, start=1):
        with st.container(border=True, key=f'pi-action-card-{priority}'):
            st.markdown(f'<p class="pi-eyebrow">PRIORITY {priority:02d}</p>', unsafe_allow_html=True)
            st.subheader(action.title)
            effort = getattr(action, 'effort', 'Not assessed; regenerate this plan')
            st.markdown(
                '<div class="pi-action-card">'
                f'<span class="pi-chip">Suggested owner · {escape(action.suggested_owner)}</span> '
                f'<span class="pi-chip">Suggested effort · {escape(effort)}</span>'
                '</div>',
                unsafe_allow_html=True,
            )
            st.write(action.instruction)
            st.markdown(
                f'<p class="pi-note">Based on: {escape(action.finding.title)}</p>',
                unsafe_allow_html=True,
            )
            with st.expander('How to measure this trial'):
                st.text(f'Suggested owner: {action.suggested_owner} — confirm with your team')
                st.text(f'Suggested effort: {effort} — review with your team; no hours or cost estimated')
                st.write(action.measure)
                st.caption('Agree on a baseline and check service quality as well as time. Any benefit needs to be observed during the trial.')
            with st.expander('Why this action'):
                st.text(action.finding.explanation)
                render_evidence(action.finding)
    with st.expander('All findings and supporting evidence'):
        for finding in plan.findings:
            st.text(finding.explanation)
            render_evidence(finding)
    st.markdown(f'<p class="pi-note">{escape(plan.limitations)}</p>', unsafe_allow_html=True)
