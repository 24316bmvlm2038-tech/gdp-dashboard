"""The home feed: a personalised, endless stream of interactive cards."""

from __future__ import annotations

from datetime import datetime

import streamlit as st

from .. import ai, engine
from ..models import CARD_TYPES, CATEGORIES, level_for_xp
from ..store import card as get_card, content, flag, interactions, save
from ..theme import haptic
from .components import empty_state, esc, go, render_card, section, track_reading

PAGE = 6


def _greeting(user: dict) -> str:
    hour = datetime.now().hour
    if hour < 5:
        return 'Still awake'
    if hour < 12:
        return 'Good morning'
    if hour < 18:
        return 'Good afternoon'
    return 'Good evening'


def _hero(user: dict) -> None:
    stats = engine.user_stats(user)
    level, into, need, title = level_for_xp(user.get('xp', 0))
    pct = int(100 * into / need)
    st.markdown(
        f"""<div class="cf-card cf-in" style="margin-bottom:1rem">
          <div class="cf-aura" style="background:linear-gradient(135deg,#2563EB,#7C3AED)"></div>
          <div class="cf-eyebrow">{_greeting(user)}, {esc(user['name'].split()[0])}</div>
          <div class="cf-display" style="font-size:2.1rem;margin:.25rem 0 .5rem">
            Something worth thinking about.</div>
          <div class="cf-row" style="gap:.45rem;margin-bottom:.7rem">
            <span class="cf-chip">🔥 {stats['streak']}-day streak</span>
            <span class="cf-chip">⭐ Level {level} · {esc(title)}</span>
            <span class="cf-chip">🧠 {stats['answers']} answered</span>
            <span class="cf-chip">🎯 {stats['accuracy']}% accuracy</span>
          </div>
          <div style="height:8px;border-radius:99px;background:var(--surface-2);overflow:hidden">
            <div style="height:100%;width:{pct}%;border-radius:99px;
              background:linear-gradient(90deg,var(--primary),var(--accent))"></div>
          </div>
          <div class="cf-meta" style="margin-top:.35rem">{into} / {need} XP to level {level + 1}</div>
        </div>""", unsafe_allow_html=True)


def _filters(user: dict) -> tuple[str, str]:
    c1, c2, c3 = st.columns([0.42, 0.42, 0.16])
    cats = ['All my interests'] + list(CATEGORIES)
    category = c1.selectbox('Topic', cats, key='feed_cat', label_visibility='collapsed')
    types = ['All card types'] + list(CARD_TYPES)
    ctype = c2.selectbox('Card type', types, key='feed_type', label_visibility='collapsed')
    if c3.button('↻', key='feed_refresh', use_container_width=True, help='Refresh the feed'):
        st.session_state['feed_ids'] = []
        st.session_state['feed_page'] = 1
        haptic('light')
        st.rerun()
    return category, ctype


def _ai_row(user: dict) -> None:
    if not flag('ai_generation'):
        return
    c1, c2 = st.columns([0.62, 0.38])
    with c1:
        st.markdown(
            f'<div class="cf-panel cf-flat cf-in"><div class="cf-eyebrow">AI engine · '
            f'{ai.engine_name()}</div><div class="cf-body">Generate three new cards tuned to '
            f'your interests, streak and difficulty right now.</div></div>',
            unsafe_allow_html=True)
    with c2:
        st.markdown('<div style="height:.35rem"></div>', unsafe_allow_html=True)
        if st.button('✨  Generate for me', key='feed_gen', type='primary',
                     use_container_width=True):
            if ai.rate_limited(user, 'generate', 12):
                st.warning('Free generation limit reached for today. Premium removes the cap.')
            else:
                with st.spinner('Thinking…'):
                    fresh = ai.generate_cards(user, 3)
                st.session_state['feed_ids'] = [c['id'] for c in fresh] + \
                    st.session_state.get('feed_ids', [])
                haptic('success')
                st.rerun()


def _apply_filters(cards: list[dict], category: str, ctype: str) -> list[dict]:
    out = cards
    if category != 'All my interests':
        out = [c for c in out if c['category'] == category]
    if ctype != 'All card types':
        out = [c for c in out if c['type'] == ctype]
    return out


def render(user: dict) -> None:
    _hero(user)
    category, ctype = _filters(user)
    _ai_row(user)

    page = st.session_state.setdefault('feed_page', 1)
    ids = st.session_state.setdefault('feed_ids', [])

    wanted = PAGE * page
    if len(ids) < wanted:
        fresh = engine.build_feed(user, limit=wanted - len(ids) + 4, exclude=set(ids))
        for card in fresh:
            if card['id'] not in ids:
                ids.append(card['id'])
        st.session_state['feed_ids'] = ids

    cards = [get_card(cid) for cid in ids[:wanted]]
    cards = [c for c in cards if c]
    cards = _apply_filters(cards, category, ctype)

    if not cards:
        empty_state('🔭', 'Nothing matches that filter yet',
                    'Try a different topic or card type — or let the AI generate something new.')
    else:
        section('For you', 'Ranked by what you read, answer, save and skip.', 'Your feed')
        for card in cards:
            render_card(user, card, ns='feed')

        c1, c2, c3 = st.columns([0.2, 0.6, 0.2])
        if c2.button('Load more', key='feed_more', use_container_width=True, type='primary'):
            st.session_state['feed_page'] = page + 1
            haptic('light')
            st.rerun()

    track_reading(user, cards)
    save()
