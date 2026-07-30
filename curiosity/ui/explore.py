"""Explore: universal search plus what the whole community is arguing about."""

from __future__ import annotations

import re

import streamlit as st

from .. import engine
from ..models import CATEGORIES, ago
from ..store import (card as get_card, collections, content, db, interactions,
                     users)
from ..theme import haptic
from .components import (card_preview, empty_state, esc, go, render_card,
                         section, user_chip)


def _tokens(query: str) -> set[str]:
    return {t for t in re.findall(r'\w+', query.lower()) if len(t) > 1}


def _match(text: str, tokens: set[str]) -> int:
    haystack = (text or '').lower()
    return sum(1 for t in tokens if t in haystack)


def search_cards(tokens: set[str], limit: int = 20) -> list[dict]:
    scored = []
    for card in content().values():
        blob = f'{card["title"]} {card["body"]} {card.get("reveal", "")} {card.get("explain", "")} ' \
               f'{card["category"]} {card["type"]} {" ".join(card.get("tags", []))}'
        hits = _match(blob, tokens)
        if hits:
            scored.append((hits + 2 * _match(card['title'], tokens), card))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [c for _, c in scored[:limit]]


def search_people(tokens: set[str], limit: int = 12) -> list[dict]:
    out = []
    for u in users().values():
        if not u.get('settings', {}).get('privacy', {}).get('public_profile', True):
            continue
        blob = f'{u.get("name", "")} {u.get("handle", "")} {u.get("bio", "")} ' \
               f'{" ".join(u.get("interests", []))}'
        hits = _match(blob, tokens)
        if hits:
            out.append((hits, u))
    out.sort(key=lambda pair: pair[0], reverse=True)
    return [u for _, u in out[:limit]]


def _trending_block(user: dict) -> None:
    section('Trending now', 'What the community is answering and arguing about.', 'Explore')
    topics = engine.trending_topics(8)
    chips = []
    for name, weight in topics:
        emoji = CATEGORIES.get(name, {}).get('emoji', '✨')
        chips.append(f'<span class="cf-chip">{emoji} {esc(name)} · {weight}</span>')
    st.markdown(f'<div class="cf-row" style="margin-bottom:.8rem">{"".join(chips)}</div>',
                unsafe_allow_html=True)

    hot = engine.trending(6)
    if not hot:
        empty_state('📊', 'No trends yet', 'Answer a few cards and this fills up fast.')
        return
    for card in hot[:3]:
        render_card(user, card, ns='trend')
    if len(hot) > 3:
        st.markdown('<div class="cf-eyebrow" style="margin:.6rem 0 .4rem">Also heating up</div>',
                    unsafe_allow_html=True)
        cols = st.columns(3)
        for col, card in zip(cols, hot[3:6]):
            with col:
                if card_preview(card, f'trendp_{card["id"]}'):
                    go('card', focus_card=card['id'])
                    st.rerun()


def _browse_block(user: dict) -> None:
    section('Browse by topic', 'Nineteen worlds to fall into.', '')
    cols = st.columns(4)
    for i, (name, meta) in enumerate(CATEGORIES.items()):
        with cols[i % 4]:
            count = sum(1 for c in content().values() if c['category'] == name)
            if st.button(f'{meta["emoji"]}  {name}\n{count} cards', key=f'browse_{name}',
                         use_container_width=True):
                st.session_state['search_query'] = name
                haptic('light')
                st.rerun()


def render(user: dict) -> None:
    query = st.text_input('Search', key='search_query',
                          placeholder='Search questions, people, collections, bookmarks, messages…',
                          label_visibility='collapsed')

    if not query.strip():
        _trending_block(user)
        _browse_block(user)
        return

    tokens = _tokens(query)
    cards = search_cards(tokens)
    people = search_people(tokens)

    my_cols = [(name, folder) for name, folder in collections(user['id']).items()
               if _match(name, tokens)]
    saved = [get_card(cid) for cid, inter in interactions(user['id']).items()
             if inter.get('bookmarked')]
    saved = [c for c in saved if c and _match(f'{c["title"]} {c["body"]}', tokens)]
    messages = []
    for tid, thread in db()['threads'].items():
        if user['id'] not in thread.get('members', []):
            continue
        for msg in thread.get('messages', []):
            if _match(msg.get('text', ''), tokens):
                messages.append((thread, msg))
    my_comments = []
    for cid, thread in db()['comments'].items():
        for comment in thread:
            if _match(comment.get('text', ''), tokens):
                my_comments.append((cid, comment))

    total = len(cards) + len(people) + len(my_cols) + len(saved) + len(messages) + len(my_comments)
    section(f'{total} results', f'for “{query}”', 'Search')
    if not total:
        empty_state('🔍', 'Nothing found',
                    'Try a broader word — or ask the assistant, it does not need exact matches.')
        return

    tabs = st.tabs([f'Cards {len(cards)}', f'People {len(people)}',
                    f'Collections {len(my_cols)}', f'Bookmarks {len(saved)}',
                    f'Messages {len(messages)}', f'Comments {len(my_comments)}'])

    with tabs[0]:
        for card in cards[:8]:
            render_card(user, card, ns='search')
    with tabs[1]:
        if not people:
            st.caption('No matching people.')
        for u in people:
            with st.container(key=f'panelbox_sp_{u["id"]}'):
                st.markdown(user_chip(u, 40, u.get('bio', '')[:70]), unsafe_allow_html=True)
                if st.button('View profile', key=f'sp_go_{u["id"]}', use_container_width=True):
                    go('user', focus_user=u['id'])
                    st.rerun()
    with tabs[2]:
        if not my_cols:
            st.caption('No matching collections.')
        for name, folder in my_cols:
            st.markdown(f'<div class="cf-panel cf-flat">{folder.get("emoji", "📁")} '
                        f'<b>{esc(name)}</b> · {len(folder.get("items", []))} saved</div>',
                        unsafe_allow_html=True)
    with tabs[3]:
        for card in saved[:12]:
            if card_preview(card, f'sb_{card["id"]}'):
                go('card', focus_card=card['id'])
                st.rerun()
    with tabs[4]:
        for thread, msg in messages[:20]:
            sender = users().get(msg.get('uid'), {})
            st.markdown(f'<div class="cf-panel cf-flat" style="margin-bottom:.4rem">'
                        f'<div class="cf-eyebrow">{esc(thread.get("name", "Direct message"))} · '
                        f'{esc(sender.get("name", "Someone"))} · {ago(msg.get("at", ""))}</div>'
                        f'<div class="cf-body">{esc(msg.get("text", ""))}</div></div>',
                        unsafe_allow_html=True)
    with tabs[5]:
        for cid, comment in my_comments[:20]:
            card = get_card(cid)
            author = users().get(comment['uid'], {})
            st.markdown(f'<div class="cf-panel cf-flat" style="margin-bottom:.4rem">'
                        f'<div class="cf-eyebrow">on “{esc(card["title"] if card else "a card")}” · '
                        f'{esc(author.get("name", "Someone"))}</div>'
                        f'<div class="cf-body">{esc(comment["text"])}</div></div>',
                        unsafe_allow_html=True)
