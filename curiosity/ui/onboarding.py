"""The three-step onboarding questionnaire that seeds personalisation."""

from __future__ import annotations

import streamlit as st

from ..models import CATEGORIES, DIFFICULTIES, LEARNING_STYLES
from ..store import save
from ..theme import haptic
from .components import esc, section


def _progress(step: int) -> None:
    labels = ['Interests', 'How you learn', 'Your profile']
    chips = []
    for i, label in enumerate(labels, start=1):
        active = i <= step
        style = ('background:linear-gradient(120deg,var(--primary),var(--accent));color:#fff;'
                 'border:none' if active else '')
        chips.append(f'<span class="cf-chip" style="{style}">{i}. {label}</span>')
    st.markdown(f'<div class="cf-row" style="justify-content:center;margin-bottom:.9rem">'
                f'{"".join(chips)}</div>', unsafe_allow_html=True)
    st.progress(step / 3)


def _step_interests(user: dict) -> None:
    section('What are you curious about?', 'Pick at least three. You can change this any time.',
            'Step 1 of 3')
    chosen = set(st.session_state.setdefault('ob_interests', set(user.get('interests', []))))
    cols = st.columns(4)
    for i, (name, meta) in enumerate(CATEGORIES.items()):
        with cols[i % 4]:
            on = name in chosen
            if st.button(f'{meta["emoji"]}  {name}', key=f'ob_int_{name}',
                         use_container_width=True,
                         type='primary' if on else 'secondary'):
                chosen.discard(name) if on else chosen.add(name)
                st.session_state['ob_interests'] = chosen
                haptic('light')
                st.rerun()
    st.markdown(f'<div class="cf-meta" style="margin:.6rem 0">{len(chosen)} selected</div>',
                unsafe_allow_html=True)
    if st.button('Continue', type='primary', use_container_width=True,
                 disabled=len(chosen) < 3):
        user['interests'] = sorted(chosen)
        st.session_state['ob_step'] = 2
        save()
        st.rerun()


def _step_style(user: dict) -> None:
    section('How do you like to learn?', 'This decides which card types dominate your feed.',
            'Step 2 of 3')
    cols = st.columns(3)
    for i, (name, meta) in enumerate(LEARNING_STYLES.items()):
        with cols[i % 3]:
            picked = st.session_state.get('ob_style') == name
            st.markdown(
                f'<div class="cf-panel cf-flat cf-in" style="margin-bottom:.4rem;text-align:center">'
                f'<div style="font-size:1.7rem">{meta["emoji"]}</div>'
                f'<div style="font-weight:700;color:var(--text)">{esc(name)}</div>'
                f'<div class="cf-meta">{esc(", ".join(meta["favours"][:2]))}</div></div>',
                unsafe_allow_html=True)
            if st.button('Choose' if not picked else '✓ Chosen', key=f'ob_sty_{name}',
                         use_container_width=True, type='primary' if picked else 'secondary'):
                st.session_state['ob_style'] = name
                haptic('light')
                st.rerun()

    st.markdown('<div class="cf-spacer"></div>', unsafe_allow_html=True)
    level = st.select_slider(
        'How hard should your cards be?', options=list(DIFFICULTIES),
        value=user.get('difficulty', 3),
        format_func=lambda v: f'{v} · {DIFFICULTIES[v]}')
    c1, c2 = st.columns([0.3, 0.7])
    if c1.button('← Back', use_container_width=True):
        st.session_state['ob_step'] = 1
        st.rerun()
    if c2.button('Continue', type='primary', use_container_width=True,
                 disabled=not st.session_state.get('ob_style')):
        user['learning_style'] = st.session_state['ob_style']
        user['difficulty'] = level
        st.session_state['ob_step'] = 3
        save()
        st.rerun()


def _step_profile(user: dict) -> None:
    from ..models import AVATAR_COLORS, COUNTRIES
    section('Make it yours', 'Everything here is optional and editable later.', 'Step 3 of 3')
    c1, c2 = st.columns([0.55, 0.45], gap='medium')
    with c1:
        name = st.text_input('Display name', value=user.get('name', ''))
        handle = st.text_input('Handle', value=user.get('handle', ''), max_chars=18)
        bio = st.text_area('Bio', value=user.get('bio', ''), height=90,
                           placeholder='One line about what you are chasing.')
        country = st.selectbox('Country (for the country leaderboard)', COUNTRIES,
                               index=COUNTRIES.index(user.get('country', 'Other')))
    with c2:
        st.markdown('<div class="cf-eyebrow">Avatar colour</div>', unsafe_allow_html=True)
        cols = st.columns(5)
        for i, colour in enumerate(AVATAR_COLORS):
            with cols[i % 5]:
                if st.button('●', key=f'ob_col_{colour}', use_container_width=True,
                             help=colour):
                    user['color'] = colour
                    save()
                    st.rerun()
        from ..theme import avatar_html
        st.markdown(
            f'<div style="text-align:center;margin-top:.7rem">'
            f'{avatar_html(name or "You", user.get("color", "#2563EB"), 84, ring=True)}</div>',
            unsafe_allow_html=True)

    c3, c4 = st.columns([0.3, 0.7])
    if c3.button('← Back', use_container_width=True):
        st.session_state['ob_step'] = 2
        st.rerun()
    if c4.button('Start exploring', type='primary', use_container_width=True):
        from ..store import db
        old_handle = user.get('handle')
        clean = (handle or old_handle).lstrip('@').lower()
        if clean != old_handle and clean in db()['handles']:
            st.error('That handle is taken.')
            return
        db()['handles'].pop(old_handle, None)
        db()['handles'][clean] = user['id']
        user.update({'name': name.strip() or user['name'], 'handle': clean,
                     'bio': bio.strip()[:180], 'country': country, 'onboarded': True})
        for key in ('ob_step', 'ob_interests', 'ob_style'):
            st.session_state.pop(key, None)
        save()
        haptic('success')
        st.balloons()
        st.rerun()


def render(user: dict) -> None:
    step = st.session_state.setdefault('ob_step', 1)
    _, mid, _ = st.columns([0.06, 0.88, 0.06])
    with mid:
        _progress(step)
        if step == 1:
            _step_interests(user)
        elif step == 2:
            _step_style(user)
        else:
            _step_profile(user)
