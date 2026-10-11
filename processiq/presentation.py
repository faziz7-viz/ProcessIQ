"""Small, scoped presentation helpers; no business facts or provider calls."""
import base64
from functools import lru_cache
from html import escape
from pathlib import Path
import streamlit as st
from processiq.interview import FIRST_QUESTION

UI = Path(__file__).parent / 'ui'
OPENING_HINTS = [
    'I start by checking my messages…',
    'First, I see what orders came in…',
    'I check what my team needs…',
    'My day usually starts with a customer…',
]


@lru_cache(maxsize=1)
def app_css():
    css = (UI / 'app.css').read_text()
    for token, filename in [('GEIST_DATA', 'Geist.ttf'), ('SERIF_DATA', 'InstrumentSerif-Italic.ttf')]:
        css = css.replace(token, base64.b64encode((UI / 'fonts' / filename).read_bytes()).decode())
    return css


def brand_html():
    return '''<div class="pi-brand"><span class="pi-brand-mark" aria-hidden="true"><i></i><i></i><i></i></span><span>Process<span class="pi-brand-iq">IQ</span><small>WORKFLOW INTELLIGENCE</small></span></div>'''


@lru_cache(maxsize=1)
def interview_css():
    css = (UI / 'interview.css').read_text()
    for token, filename in [('GEIST_DATA','Geist.ttf'),('SERIF_DATA','InstrumentSerif-Italic.ttf')]:
        css = css.replace(token, base64.b64encode((UI/'fonts'/filename).read_bytes()).decode())
    return css


def answer_hints(state):
    if not state.sources:
        return OPENING_HINTS
    question = (state.question or '').lower()
    if state.target and state.target != 'process_details':
        return ['What I know is…', 'I’m not sure about this yet…']
    if any(word in question for word in ['who ', 'person', 'role']):
        return ['This is usually handled by…', 'The person responsible is…']
    if any(word in question for word in ['where ', 'place', 'location']):
        return ['I do this at…', 'This usually happens in…']
    return ['The next thing I do is…', 'What happens is…', 'Usually, I…']


def question_html(question):
    text = escape(question)
    if question == FIRST_QUESTION:
        text = text.replace('typical workday.', '<em>typical workday.</em>')
    return f'<h1 class="pi-question">{text}</h1>'


def enhance_hints(state):
    hints_component = st.components.v2.component('processiq_answer_hints', js=(UI / 'hints.js').read_text())
    hints_component(data={'hints':answer_hints(state)}, key='interview-hints')
