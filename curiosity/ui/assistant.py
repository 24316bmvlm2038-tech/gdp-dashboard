"""The built-in conversational AI: explain, teach, debate, plan, summarise."""

from __future__ import annotations

import streamlit as st

from .. import ai, engine
from ..models import CATEGORIES, now_iso
from ..store import db, flag, save
from ..theme import haptic
from .components import esc, section

MODES = {
    'Explain': ('💡', 'Clear answers with the interesting part left in.'),
    'Teach': ('🎓', 'One idea, one analogy, one question back to you.'),
    'Debate': ('⚔️', 'It takes the opposite side and argues it properly.'),
}

QUICK = [
    ('Explain my last answer', 'Explain the reasoning behind the last card I answered, '
                               'including what most people get wrong about it.'),
    ('Quiz me', 'Give me a five-question quiz on my favourite topics, one question at a time.'),
    ('Recommend books', 'Recommend five books based on my interests, with one line each on why.'),
    ('Build a study plan', 'Build me a four-week study plan for the topic I engage with most.'),
    ('Startup ideas', 'Give me three startup ideas that fit my interests, with the hardest '
                      'problem in each named honestly.'),
    ('Summarise this', 'I will paste an article next — summarise it in three bullets.'),
]


def _history(uid: str) -> list[dict]:
    return db()['assistant'].setdefault(uid, [])


def _render_message(msg: dict) -> None:
    """User turns get a gradient bubble; assistant turns render as markdown."""
    if msg['role'] == 'user':
        st.markdown(
            f'<div style="display:flex;justify-content:flex-end;margin:.5rem 0">'
            f'<div style="max-width:80%;padding:.7rem .95rem;border-radius:20px 20px 6px 20px;'
            f'background:linear-gradient(120deg,var(--primary),var(--accent));color:#fff;'
            f'box-shadow:0 10px 26px rgba(37,99,235,.28)">{esc(msg["content"])}</div></div>',
            unsafe_allow_html=True)
    else:
        with st.chat_message('assistant', avatar='🤖'):
            st.markdown(msg['content'])


def render(user: dict) -> None:
    section('Assistant', f'Running on the {ai.engine_name().lower()} engine.', 'AI')

    c1, c2 = st.columns([0.68, 0.32])
    with c1:
        mode = st.radio('Mode', list(MODES), horizontal=True, key='ai_mode',
                        label_visibility='collapsed',
                        format_func=lambda m: f'{MODES[m][0]}  {m}')
    with c2:
        if st.button('🗑  Clear conversation', use_container_width=True):
            db()['assistant'][user['id']] = []
            save()
            st.rerun()
    st.caption(MODES[mode][1])

    quick_cols = st.columns(3)
    for i, (label, prompt) in enumerate(QUICK):
        with quick_cols[i % 3]:
            if st.button(label, key=f'quick_{i}', use_container_width=True):
                st.session_state['ai_pending'] = prompt

    if flag('voice_assistant'):
        with st.expander('🎙  Voice conversation'):
            st.write('Record a question and the assistant answers it in text. '
                     'Speech-to-text and spoken replies are a Premium feature — this build '
                     'captures the audio and stores it with your message.')
            audio = st.audio_input('Ask out loud', key='ai_voice')
            if audio is not None:
                st.audio(audio)
                if not user.get('premium'):
                    st.info('Transcription runs on the Premium plan. Type the question for now.')

    history = _history(user['id'])
    for msg in history[-24:]:
        _render_message(msg)

    pending = st.session_state.pop('ai_pending', None)
    typed = st.chat_input('Ask anything — or paste something to summarise')
    question = pending or typed
    if not question:
        if not history:
            st.markdown(
                '<div class="cf-card cf-in" style="text-align:center;padding:2rem 1.2rem">'
                '<div style="font-size:2.2rem">🤖</div>'
                '<div style="font-weight:740;color:var(--text);margin-top:.3rem">'
                'Ask it something you would not Google</div>'
                '<div class="cf-body">It explains, teaches, argues back, writes study plans and '
                'builds quizzes from what you have been reading.</div></div>',
                unsafe_allow_html=True)
        return

    ok, reason = ai.moderate(question)
    if not ok:
        st.error(reason)
        return
    if ai.rate_limited(user, 'assistant', ai.FREE_DAILY_MESSAGES):
        st.warning(f'Free plan limit of {ai.FREE_DAILY_MESSAGES} messages a day reached. '
                   'Premium removes the cap.')
        return

    history.append({'role': 'user', 'content': question, 'at': now_iso()})
    with st.spinner('Thinking…'):
        answer = ai.ask(user, question, history[:-1], mode)
    history.append({'role': 'assistant', 'content': answer, 'at': now_iso()})
    del history[:-60]

    counters = user.setdefault('counters', {})
    counters['assistant_msgs'] = counters.get('assistant_msgs', 0) + 1
    engine.award_xp(user, 'assistant')
    engine.register_activity(user)
    engine.check_achievements(user)
    save()
    haptic('light')
    st.rerun()
