"""Present the verified report; AI selections never become free-form claims."""

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
    st.subheader('Your improvement plan')
    st.caption('AI-prioritized plan' if plan.mode == 'ai' else 'Rule-based offline plan · No AI request')
    st.caption('Figures and quotes come from the reviewed assessment. Actions are suggestions to test with your team.')
    with st.expander('What the numbers mean', expanded=True):
        for finding in plan.summary:
            st.text(finding.explanation)
            render_evidence(finding)
    st.subheader('Findings to focus on')
    for finding in plan.findings:
        st.text(finding.explanation)
        render_evidence(finding)
    st.subheader('Suggested actions in priority order')
    for priority, action in enumerate(plan.actions, start=1):
        st.subheader(f'{priority}. {action.title}')
        st.text(f'Target: {action.finding.title}')
        st.text(f'Suggested owner: {action.suggested_owner} — confirm with your team')
        effort = getattr(action, 'effort', 'Not assessed; regenerate this plan')
        st.text(f'Suggested effort: {effort} — review with your team; no hours or cost estimated')
        st.write(action.instruction)
        st.write(f'How to check whether it helps: {action.measure}')
    st.info(plan.limitations)
