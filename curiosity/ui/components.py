"""Reusable UI pieces: the top bar, the floating nav, and the card renderer
that every surface of the app shares.
"""

from __future__ import annotations

import html
import time

import streamlit as st

from .. import ai, engine, share
from ..models import (CARD_TYPES, CATEGORIES, SHARE_TARGETS, ago, level_for_xp,
                      now_iso)
from ..store import (card as get_card, comments, collections, db, interaction,
                     notifications, save, users)
from ..theme import avatar_html, gradient_for, haptic

APP_URL = 'https://curiosityfeed.app'

ROUTES = [
    ('feed', 'Feed', '✨'),
    ('daily', 'Daily', '🌅'),
    ('explore', 'Explore', '🔎'),
    ('assistant', 'Assistant', '🤖'),
    ('collections', 'Saved', '🔖'),
    ('social', 'People', '👥'),
    ('stats', 'Stats', '📈'),
    ('profile', 'Profile', '👤'),
]


def go(route: str, **params) -> None:
    st.session_state['route'] = route
    for key, value in params.items():
        st.session_state[key] = value


def esc(text: str) -> str:
    return html.escape(str(text or ''))


# ---------------------------------------------------------------- chrome

def top_bar(user: dict) -> None:
    stats = engine.user_stats(user)
    unread = sum(1 for n in notifications(user['id']) if not n.get('read'))
    left, right = st.columns([0.62, 0.38], vertical_alignment='center')
    with left:
        st.markdown(
            f"""<div class="cf-topbar">
              <div class="cf-brand"><span class="cf-orb">◎</span> Curiosity Feed</div>
              <div class="cf-row">
                <span class="cf-chip">🔥 {stats['streak']}</span>
                <span class="cf-chip">⭐ L{stats['level']}</span>
                <span class="cf-chip">{esc(stats['title'])}</span>
              </div>
            </div>""", unsafe_allow_html=True)
    with right:
        c1, c2, c3 = st.columns(3)
        if c1.button(f'🔔 {unread}' if unread else '🔔', key='nav_notif',
                     use_container_width=True, help='Notifications'):
            go('notifications')
            st.rerun()
        if c2.button('🔍', key='nav_search', use_container_width=True, help='Search'):
            go('explore')
            st.rerun()
        if c3.button('⚙️', key='nav_settings', use_container_width=True, help='Settings'):
            go('settings')
            st.rerun()


def floating_nav(user: dict) -> None:
    current = st.session_state.get('route', 'feed')
    with st.container(key='cf_nav'):
        cols = st.columns(len(ROUTES))
        for col, (route, label, icon) in zip(cols, ROUTES):
            with col:
                if st.button(f'{icon}\n{label}', key=f'nav_{route}',
                             use_container_width=True,
                             type='primary' if current == route else 'secondary'):
                    go(route)
                    st.rerun()


def section(title: str, subtitle: str = '', eyebrow: str = '') -> None:
    bits = []
    if eyebrow:
        bits.append(f'<div class="cf-eyebrow">{esc(eyebrow)}</div>')
    bits.append(f'<h2 style="margin:.15rem 0 .1rem">{esc(title)}</h2>')
    if subtitle:
        bits.append(f'<div class="cf-sub">{esc(subtitle)}</div>')
    st.markdown(f'<div class="cf-in" style="margin:.9rem 0 .7rem">{"".join(bits)}</div>',
                unsafe_allow_html=True)


def empty_state(icon: str, title: str, body: str) -> None:
    st.markdown(
        f"""<div class="cf-card cf-in" style="text-align:center;padding:2.4rem 1.4rem">
              <div style="font-size:2.6rem;margin-bottom:.4rem">{icon}</div>
              <div style="font-weight:750;font-size:1.1rem;color:var(--text)">{esc(title)}</div>
              <div class="cf-body" style="margin-top:.3rem">{esc(body)}</div>
            </div>""", unsafe_allow_html=True)


def user_chip(u: dict, size: int = 34, meta: str = '') -> str:
    tick = ' <span title="Verified creator">✔️</span>' if u.get('verified_creator') else ''
    crown = ' 👑' if u.get('premium') else ''
    line2 = f'<div class="cf-meta">{esc(meta)}</div>' if meta else ''
    return (
        f'<div class="cf-row" style="gap:.6rem">{avatar_html(u.get("name", "?"), u.get("color", "#2563EB"), size)}'
        f'<div><div style="font-weight:680;color:var(--text)">{esc(u.get("name"))}{tick}{crown}</div>'
        f'<div class="cf-meta">@{esc(u.get("handle"))}</div>{line2}</div></div>'
    )


# ---------------------------------------------------------------- card parts

def _difficulty_dots(level: int) -> str:
    filled = '<span class="cf-dot" style="background:var(--primary)"></span>'
    empty = '<span class="cf-dot" style="background:var(--border-strong)"></span>'
    return ' '.join(filled if i < level else empty for i in range(5))


def card_header(card: dict) -> str:
    meta = CARD_TYPES.get(card['type'], {'emoji': '✨', 'grad': 'indigo'})
    cat = CATEGORIES.get(card['category'], {'emoji': '✨'})
    g1, g2 = gradient_for(card.get('grad', meta['grad']))
    source = {'ai': 'AI generated', 'composed': 'Generated for you',
              'seed': 'Curated', 'user': 'Community'}.get(card.get('source', 'seed'), '')
    return f"""
      <div class="cf-aura" style="background:linear-gradient(135deg,{g1},{g2})"></div>
      <div class="cf-row" style="justify-content:space-between">
        <div class="cf-row">
          <span class="cf-chip cf-chip-grad" style="background:linear-gradient(120deg,{g1},{g2})">
            {meta['emoji']} {esc(card['type'])}</span>
          <span class="cf-chip">{cat['emoji']} {esc(card['category'])}</span>
        </div>
        <div class="cf-row" style="gap:.5rem">
          <span class="cf-meta">{_difficulty_dots(card.get('difficulty', 3))}</span>
          <span class="cf-meta">· {card.get('read_time', 20)}s · {source}</span>
        </div>
      </div>
      <div class="cf-q">{esc(card['title'])}</div>
      {'<div class="cf-body">' + esc(card.get('body', '')) + '</div>' if card.get('body') else ''}
    """


def result_bars(card: dict, my_choice: int | None) -> None:
    options = card.get('options', [])
    pcts = engine.vote_percentages(card['id'], options)
    totals = engine.vote_totals(card['id'], options)
    rows = []
    for i, option in enumerate(options):
        mine = ' cf-bar-mine' if my_choice == i else ''
        check = ' ✓' if my_choice == i else ''
        rows.append(
            f'<div class="cf-bar{mine}"><div class="cf-bar-fill" style="width:{max(2, pcts[i])}%"></div>'
            f'<div class="cf-bar-label"><span>{esc(option)}{check}</span>'
            f'<span>{pcts[i]}%</span></div></div>')
    st.markdown(''.join(rows), unsafe_allow_html=True)
    st.markdown(f'<div class="cf-meta">{sum(totals)} answer(s) so far</div>',
                unsafe_allow_html=True)


def _my_percent(card: dict, choice: int | None) -> int | None:
    if choice is None or not card.get('options'):
        return None
    pcts = engine.vote_percentages(card['id'], card['options'])
    return pcts[choice] if choice < len(pcts) else None


# ---------------------------------------------------------------- share sheet

@st.dialog('Share your answer', width='large')
def share_dialog(user: dict, card: dict) -> None:
    inter = interaction(user['id'], card['id'])
    choice = inter.get('answer')
    answer_text = ''
    if isinstance(choice, int) and card.get('options'):
        answer_text = card['options'][choice] if choice < len(card['options']) else ''
    elif inter.get('answer_text'):
        answer_text = inter['answer_text'][:90]
    percent = _my_percent(card, choice if isinstance(choice, int) else None)
    stats = engine.user_stats(user)

    image = share.render(card, answer_text=answer_text, percent=percent,
                         user_name=user['name'], streak=stats['streak'], level=stats['level'])
    png = share.to_png(image)
    text = share.caption(card, answer_text, percent)

    left, right = st.columns([0.52, 0.48], gap='medium')
    with left:
        st.image(image, use_container_width=True)
    with right:
        st.markdown('<div class="cf-eyebrow">Caption</div>', unsafe_allow_html=True)
        st.code(text, language=None)
        st.download_button('⬇️  Download card (PNG)', png,
                           file_name=f'curiosity-{card["id"]}.png', mime='image/png',
                           use_container_width=True, type='primary',
                           key=f'dl_{card["id"]}')
        st.markdown('<div class="cf-eyebrow" style="margin-top:.7rem">Send to</div>',
                    unsafe_allow_html=True)
        links = []
        for name, icon, template in SHARE_TARGETS:
            if template:
                url = share.share_url(template, text, APP_URL)
                links.append(f'<a class="cf-chip" style="text-decoration:none" href="{url}" '
                             f'target="_blank" rel="noopener">{icon} {esc(name)}</a>')
            else:
                links.append(f'<span class="cf-chip" title="Download the PNG, then post it">'
                             f'{icon} {esc(name)}</span>')
        st.markdown(f'<div class="cf-row">{"".join(links)}</div>', unsafe_allow_html=True)
        st.caption('Instagram, TikTok and Snapchat do not accept web share links — '
                   'download the PNG and post it there.')
        if st.button('Mark as shared  (+15 XP)', key=f'shared_{card["id"]}',
                     use_container_width=True):
            engine.record_share(user, card, 'manual')
            haptic('success')
            st.rerun()


# ---------------------------------------------------------------- comments

def comment_block(user: dict, card: dict, ns: str) -> None:
    thread = [c for c in comments(card['id']) if not c.get('hidden')]
    with st.expander(f'💬  Discussion ({len(thread)})', expanded=False):
        for comment in thread[-25:]:
            author = users().get(comment['uid'])
            if not author or author['id'] in user.get('blocked', []):
                continue
            liked = user['id'] in comment.get('likes', [])
            st.markdown(
                f'<div class="cf-panel cf-flat" style="margin-bottom:.5rem">'
                f'{user_chip(author, 30, ago(comment["at"]))}'
                f'<div class="cf-body" style="margin-top:.45rem">{esc(comment["text"])}</div></div>',
                unsafe_allow_html=True)
            c1, c2, c3 = st.columns([0.18, 0.18, 0.64])
            if c1.button(f'{"❤️" if liked else "🤍"} {len(comment.get("likes", []))}',
                         key=f'{ns}_cl_{comment["id"]}'):
                likes = comment.setdefault('likes', [])
                if liked:
                    likes.remove(user['id'])
                else:
                    likes.append(user['id'])
                    if comment['uid'] != user['id']:
                        from ..store import notify
                        notify(comment['uid'], 'like', f'{user["name"]} liked your comment.', '❤️')
                save()
                st.rerun()
            if c2.button('↩︎ Reply', key=f'{ns}_rp_{comment["id"]}'):
                st.session_state[f'reply_to_{card["id"]}'] = comment['id']
                st.rerun()
            if c3.button('⚑ Report', key=f'{ns}_rep_{comment["id"]}'):
                db()['reports'].append({
                    'id': comment['id'], 'kind': 'comment', 'by': user['id'],
                    'target_uid': comment['uid'], 'text': comment['text'],
                    'card': card['id'], 'at': now_iso(), 'status': 'open'})
                save()
                st.toast('Reported. A moderator will review it.', icon='⚑')

        reply_to = st.session_state.get(f'reply_to_{card["id"]}')
        label = 'Write a reply' if reply_to else 'Add to the discussion'
        with st.form(f'{ns}_cform_{card["id"]}', clear_on_submit=True, border=False):
            text = st.text_area(label, key=f'{ns}_ct_{card["id"]}', height=88,
                                placeholder='Say something worth reading…',
                                label_visibility='collapsed')
            c1, c2 = st.columns([0.3, 0.7])
            posted = c1.form_submit_button('Post', type='primary', use_container_width=True)
            if reply_to and c2.form_submit_button('Cancel reply', use_container_width=True):
                st.session_state.pop(f'reply_to_{card["id"]}', None)
                st.rerun()
        if posted:
            ok, reason = ai.moderate(text)
            if not ok:
                st.error(reason)
            elif ai.rate_limited(user, 'comments', 60):
                st.error('You are commenting very fast — take a breath and try again later.')
            else:
                engine.add_comment(user, card, text, reply_to)
                st.session_state.pop(f'reply_to_{card["id"]}', None)
                haptic('light')
                st.rerun()


# ---------------------------------------------------------------- main card

def render_card(user: dict, card: dict, ns: str = 'feed', compact: bool = False) -> None:
    """Render one interactive card with all of its controls."""
    cid = card['id']
    key = f'{ns}_{cid}'
    inter = interaction(user['id'], cid)
    answered = inter.get('answer') is not None
    revealed = inter.get('revealed', False)

    with st.container(key=f'cardbox_{key}'):
        st.markdown(card_header(card), unsafe_allow_html=True)

        if compact:
            if st.button('Open', key=f'{key}_open', use_container_width=True):
                go('card', focus_card=cid)
                st.rerun()
            return

        kind = card.get('kind', 'choice')
        options = card.get('options', [])

        # ---- answering ------------------------------------------------
        if kind in ('choice', 'stance'):
            if not answered:
                cols = st.columns(min(len(options), 3) or 1)
                for i, option in enumerate(options):
                    with cols[i % len(cols)]:
                        if st.button(option, key=f'{key}_opt{i}', use_container_width=True,
                                     type='primary' if i == 0 and kind == 'stance' else 'secondary'):
                            engine.record_answer(user, card, i)
                            haptic('medium')
                            st.rerun()
            else:
                result_bars(card, inter.get('answer') if isinstance(inter.get('answer'), int) else None)
                if card.get('explain'):
                    st.markdown(f'<div class="cf-panel cf-flat" style="margin-top:.6rem">'
                                f'<div class="cf-eyebrow">Context</div>'
                                f'<div class="cf-body">{esc(card["explain"])}</div></div>',
                                unsafe_allow_html=True)

        elif kind == 'quiz':
            if not answered:
                for i, option in enumerate(options):
                    if st.button(f'{chr(65 + i)}.  {option}', key=f'{key}_q{i}',
                                 use_container_width=True):
                        result = engine.record_answer(user, card, i)
                        haptic('success' if result['correct'] else 'heavy')
                        st.session_state[f'quiz_flash_{cid}'] = result['correct']
                        st.rerun()
            else:
                correct = inter.get('correct')
                chosen = inter.get('answer')
                right = card.get('answer')
                for i, option in enumerate(options):
                    if i == right:
                        st.markdown(f'<div class="cf-bar cf-bar-mine"><div class="cf-bar-fill" '
                                    f'style="width:100%;background:linear-gradient(90deg,'
                                    f'rgba(34,197,94,.55),rgba(34,197,94,.25))"></div>'
                                    f'<div class="cf-bar-label"><span>✓ {esc(option)}</span>'
                                    f'<span>Correct</span></div></div>', unsafe_allow_html=True)
                    elif i == chosen:
                        st.markdown(f'<div class="cf-bar"><div class="cf-bar-fill" '
                                    f'style="width:100%;background:linear-gradient(90deg,'
                                    f'rgba(239,68,68,.45),rgba(239,68,68,.18))"></div>'
                                    f'<div class="cf-bar-label"><span>✗ {esc(option)}</span>'
                                    f'<span>Your answer</span></div></div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div class="cf-bar"><div class="cf-bar-label">'
                                    f'<span>{esc(option)}</span><span></span></div></div>',
                                    unsafe_allow_html=True)
                verdict = ('Correct — +25 XP' if correct else 'Not this time — +6 XP for trying')
                st.markdown(f'<div class="cf-panel cf-flat" style="margin-top:.6rem">'
                            f'<div class="cf-eyebrow">{esc(verdict)}</div>'
                            f'<div class="cf-body">{esc(card.get("explain", ""))}</div></div>',
                            unsafe_allow_html=True)

        elif kind == 'open':
            if not answered:
                with st.form(f'{key}_openform', clear_on_submit=False, border=False):
                    text = st.text_area('Your answer', key=f'{key}_txt', height=110,
                                        placeholder='There is no right answer. Say what you think…',
                                        label_visibility='collapsed')
                    if st.form_submit_button('Submit answer', type='primary',
                                             use_container_width=True):
                        ok, reason = ai.moderate(text)
                        if not ok:
                            st.error(reason)
                        else:
                            engine.record_answer(user, card, 'open', text)
                            haptic('medium')
                            st.rerun()
            else:
                st.markdown(f'<div class="cf-panel cf-flat"><div class="cf-eyebrow">Your answer</div>'
                            f'<div class="cf-body cf-quote" style="margin-top:.4rem">'
                            f'{esc(inter.get("answer_text", ""))}</div></div>',
                            unsafe_allow_html=True)
                if card.get('explain'):
                    st.markdown(f'<div class="cf-body" style="margin-top:.5rem">'
                                f'{esc(card["explain"])}</div>', unsafe_allow_html=True)

        elif kind == 'reveal':
            if not revealed:
                if st.button('Reveal', key=f'{key}_rev', type='primary',
                             use_container_width=True):
                    engine.reveal(user, card)
                    haptic('light')
                    st.rerun()
            else:
                st.markdown(f'<div class="cf-panel cf-flat" style="margin-top:.2rem">'
                            f'<div class="cf-body">{esc(card.get("reveal") or card.get("explain"))}'
                            f'</div></div>', unsafe_allow_html=True)

        elif kind == 'task':
            done = inter.get('done')
            if done:
                st.markdown('<div class="cf-chip" style="background:rgba(34,197,94,.16);'
                            'color:var(--success);border:none">✓ Completed — +30 XP</div>',
                            unsafe_allow_html=True)
            else:
                c1, c2 = st.columns(2)
                if c1.button('Accept challenge', key=f'{key}_acc', type='primary',
                             use_container_width=True):
                    interaction(user['id'], cid)['accepted'] = True
                    save()
                    st.rerun()
                if c2.button('Mark as done', key=f'{key}_done', use_container_width=True):
                    engine.complete_challenge(user, card)
                    haptic('success')
                    st.balloons()
                    st.rerun()

        # ---- action row -----------------------------------------------
        st.markdown('<div class="cf-spacer"></div>', unsafe_allow_html=True)
        a1, a2, a3, a4, a5 = st.columns(5)
        liked = inter.get('liked', False)
        saved = inter.get('bookmarked', False)
        if a1.button('❤️ Liked' if liked else '🤍 Like', key=f'{key}_like',
                     use_container_width=True):
            engine.toggle_like(user, card)
            haptic('light')
            st.rerun()
        if a2.button('🔖 Saved' if saved else '🔖 Save', key=f'{key}_save',
                     use_container_width=True):
            target = st.session_state.get('default_collection', 'Favorites')
            engine.toggle_bookmark(user, card, target)
            haptic('light')
            st.rerun()
        if a3.button(f'💬 {len(comments(cid))}', key=f'{key}_cmt', use_container_width=True):
            st.session_state[f'show_comments_{key}'] = not st.session_state.get(
                f'show_comments_{key}', False)
            st.rerun()
        if a4.button('📤 Share', key=f'{key}_shr', use_container_width=True):
            share_dialog(user, card)
        if a5.button('⤵ Skip', key=f'{key}_skip', use_container_width=True):
            inter['skipped'] = True
            engine.learn(user, card, -0.4)
            save()
            st.rerun()

        if st.session_state.get(f'show_comments_{key}'):
            comment_block(user, card, ns=key)


def card_preview(card: dict, on_click_key: str) -> bool:
    """A compact tappable summary used in search results and collections."""
    meta = CARD_TYPES.get(card['type'], {'emoji': '✨'})
    st.markdown(
        f'<div class="cf-panel cf-flat cf-in" style="margin-bottom:.45rem">'
        f'<div class="cf-row" style="justify-content:space-between">'
        f'<span class="cf-chip">{meta["emoji"]} {esc(card["type"])}</span>'
        f'<span class="cf-meta">{esc(card["category"])}</span></div>'
        f'<div style="font-weight:680;color:var(--text);margin-top:.4rem">{esc(card["title"])}</div>'
        f'</div>', unsafe_allow_html=True)
    return st.button('Open', key=on_click_key, use_container_width=True)


def track_reading(user: dict, cards: list[dict]) -> None:
    """Attribute time-on-page to the cards that were on screen."""
    now = time.time()
    last = st.session_state.get('_read_tick')
    st.session_state['_read_tick'] = now
    if not last or not cards:
        return
    elapsed = min(120, int(now - last))
    if elapsed < 2:
        return
    per_card = max(1, elapsed // max(1, len(cards)))
    for card in cards[:6]:
        engine.record_reading(user, card, per_card)
    save()
