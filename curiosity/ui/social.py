"""People: discovery, follows, friend requests, direct messages and group chats."""

from __future__ import annotations

import streamlit as st

from .. import ai, engine
from ..models import ago, level_for_xp, now_iso
from ..store import (db, follows, followers, friends, interactions, new_id,
                     notify, save, users)
from ..theme import avatar_html, haptic
from .components import empty_state, esc, go, section, user_chip


# ---------------------------------------------------------------- helpers

def _follow(user: dict, target_id: str) -> None:
    mine = follows(user['id'])
    if target_id in mine:
        mine.remove(target_id)
    else:
        mine.append(target_id)
        engine.award_xp(user, 'follow')
        target = users().get(target_id, {})
        if target.get('settings', {}).get('notifications', {}).get('followers', True):
            notify(target_id, 'follow', f'{user["name"]} started following you.', '➕')
    save()


def _request_friend(user: dict, target_id: str) -> None:
    requests = db()['friend_requests']
    if any(r for r in requests if r['from'] == user['id'] and r['to'] == target_id
           and r['status'] == 'pending'):
        return
    requests.append({'id': new_id('fr'), 'from': user['id'], 'to': target_id,
                     'status': 'pending', 'at': now_iso()})
    notify(target_id, 'friend', f'{user["name"]} sent you a friend request.', '🤝')
    save()


def _accept(user: dict, request: dict) -> None:
    request['status'] = 'accepted'
    friends(user['id']).append(request['from'])
    friends(request['from']).append(user['id'])
    notify(request['from'], 'friend', f'{user["name"]} accepted your friend request.', '🤝')
    save()


def _thread_between(uid_a: str, uid_b: str) -> dict:
    for thread in db()['threads'].values():
        if set(thread['members']) == {uid_a, uid_b} and not thread.get('group'):
            return thread
    tid = new_id('t')
    thread = {'id': tid, 'members': [uid_a, uid_b], 'name': '', 'group': False,
              'messages': [], 'created_at': now_iso()}
    db()['threads'][tid] = thread
    save()
    return thread


def can_message(sender: dict, target: dict) -> bool:
    policy = target.get('settings', {}).get('privacy', {}).get('allow_messages', 'Everyone')
    if sender['id'] in target.get('blocked', []):
        return False
    if policy == 'Nobody':
        return False
    if policy == 'Friends only':
        return sender['id'] in friends(target['id'])
    return True


# ---------------------------------------------------------------- tabs

def _discover(user: dict) -> None:
    others = [u for u in users().values()
              if u['id'] != user['id']
              and u['id'] not in user.get('blocked', [])
              and u.get('settings', {}).get('privacy', {}).get('public_profile', True)]
    if not others:
        empty_state('👥', 'Nobody else here yet',
                    'Curiosity Feed is more fun with people. Invite a friend to sign up — '
                    'every account in this deployment shares the same live feed.')
        return

    my_interests = set(user.get('interests', []))
    ranked = sorted(
        others,
        key=lambda u: (len(my_interests & set(u.get('interests', []))) * 10 + u.get('xp', 0) / 100),
        reverse=True)

    cols = st.columns(2)
    for i, other in enumerate(ranked[:12]):
        shared = sorted(my_interests & set(other.get('interests', [])))
        with cols[i % 2]:
            with st.container(key=f'panelbox_disc_{other["id"]}'):
                level = level_for_xp(other.get('xp', 0))[0]
                st.markdown(
                    user_chip(other, 44,
                              f'Level {level} · {len(shared)} shared interest(s)'),
                    unsafe_allow_html=True)
                if other.get('bio'):
                    st.markdown(f'<div class="cf-body" style="font-size:.9rem;margin:.4rem 0">'
                                f'{esc(other["bio"][:110])}</div>', unsafe_allow_html=True)
                if shared:
                    st.markdown('<div class="cf-row">' + ''.join(
                        f'<span class="cf-chip">{esc(s)}</span>' for s in shared[:4]) + '</div>',
                        unsafe_allow_html=True)
                b1, b2, b3 = st.columns(3)
                following = other['id'] in follows(user['id'])
                if b1.button('Following' if following else 'Follow', key=f'f_{other["id"]}',
                             use_container_width=True,
                             type='secondary' if following else 'primary'):
                    _follow(user, other['id'])
                    haptic('light')
                    st.rerun()
                is_friend = other['id'] in friends(user['id'])
                if b2.button('Friends ✓' if is_friend else 'Add friend', key=f'fr_{other["id"]}',
                             use_container_width=True, disabled=is_friend):
                    _request_friend(user, other['id'])
                    st.toast('Friend request sent.', icon='🤝')
                    st.rerun()
                if b3.button('Profile', key=f'p_{other["id"]}', use_container_width=True):
                    go('user', focus_user=other['id'])
                    st.rerun()


def _requests(user: dict) -> None:
    incoming = [r for r in db()['friend_requests']
                if r['to'] == user['id'] and r['status'] == 'pending']
    outgoing = [r for r in db()['friend_requests']
                if r['from'] == user['id'] and r['status'] == 'pending']
    if not incoming and not outgoing:
        empty_state('🤝', 'No pending requests', 'Send one from the Discover tab.')
        return
    for request in incoming:
        sender = users().get(request['from'])
        if not sender:
            continue
        with st.container(key=f'panelbox_req_{request["id"]}'):
            st.markdown(user_chip(sender, 40, ago(request['at'])), unsafe_allow_html=True)
            c1, c2 = st.columns(2)
            if c1.button('Accept', key=f'acc_{request["id"]}', type='primary',
                         use_container_width=True):
                _accept(user, request)
                haptic('success')
                st.rerun()
            if c2.button('Decline', key=f'dec_{request["id"]}', use_container_width=True):
                request['status'] = 'declined'
                save()
                st.rerun()
    for request in outgoing:
        target = users().get(request['to'], {})
        st.markdown(f'<div class="cf-panel cf-flat" style="margin-bottom:.4rem">'
                    f'<span class="cf-meta">Pending → {esc(target.get("name", "someone"))}</span>'
                    f'</div>', unsafe_allow_html=True)


def _messages(user: dict) -> None:
    my_threads = [t for t in db()['threads'].values() if user['id'] in t['members']]
    my_threads.sort(key=lambda t: (t['messages'][-1]['at'] if t['messages'] else t['created_at']),
                    reverse=True)

    with st.expander('➕  New group chat'):
        others = [u for u in users().values() if u['id'] != user['id']]
        labels = {f'{u["name"]} (@{u["handle"]})': u['id'] for u in others}
        name = st.text_input('Group name', key='grp_name', placeholder='Deep Space Nerds')
        picked = st.multiselect('Members', list(labels), key='grp_members')
        if st.button('Create group', key='grp_create', type='primary'):
            if not picked:
                st.warning('Pick at least one member.')
            else:
                tid = new_id('t')
                db()['threads'][tid] = {
                    'id': tid, 'members': [user['id']] + [labels[p] for p in picked],
                    'name': name.strip() or 'Group chat', 'group': True,
                    'messages': [], 'created_at': now_iso()}
                for label in picked:
                    notify(labels[label], 'message',
                           f'{user["name"]} added you to “{name or "a group chat"}”.', '💬')
                save()
                st.rerun()

    if not my_threads:
        empty_state('💬', 'No conversations yet',
                    'Open someone’s profile and send the first message.')
        return

    left, right = st.columns([0.36, 0.64], gap='medium')
    with left:
        for thread in my_threads:
            if thread.get('group'):
                title = thread.get('name') or 'Group chat'
                sub = f'{len(thread["members"])} members'
            else:
                other_id = next((m for m in thread['members'] if m != user['id']), user['id'])
                other = users().get(other_id, {})
                title = other.get('name', 'Someone')
                sub = f'@{other.get("handle", "")}'
            last = thread['messages'][-1]['text'][:38] + '…' if thread['messages'] else 'No messages'
            if st.button(f'{title}\n{sub} · {last}', key=f'th_{thread["id"]}',
                         use_container_width=True,
                         type='primary' if st.session_state.get('open_thread') == thread['id']
                         else 'secondary'):
                st.session_state['open_thread'] = thread['id']
                st.rerun()

    with right:
        tid = st.session_state.get('open_thread')
        thread = db()['threads'].get(tid or '')
        if not thread or user['id'] not in thread['members']:
            st.caption('Pick a conversation.')
            return
        for msg in thread['messages'][-40:]:
            sender = users().get(msg['uid'], {})
            mine = msg['uid'] == user['id']
            align = 'flex-end' if mine else 'flex-start'
            bubble = ('background:linear-gradient(120deg,var(--primary),var(--accent));color:#fff'
                      if mine else 'background:var(--surface-2);color:var(--text)')
            st.markdown(
                f'<div style="display:flex;justify-content:{align};margin:.3rem 0">'
                f'<div style="max-width:78%;padding:.6rem .85rem;border-radius:18px;{bubble}">'
                f'<div style="font-size:.72rem;opacity:.75">{esc(sender.get("name", ""))} · '
                f'{ago(msg["at"])}</div>{esc(msg["text"])}</div></div>',
                unsafe_allow_html=True)

        text = st.chat_input('Message…', key=f'msg_{thread["id"]}')
        if text:
            ok, reason = ai.moderate(text)
            if not ok:
                st.error(reason)
            else:
                thread['messages'].append({'uid': user['id'], 'text': text.strip()[:1000],
                                           'at': now_iso()})
                del thread['messages'][:-300]
                for member in thread['members']:
                    if member != user['id']:
                        notify(member, 'message', f'{user["name"]}: {text.strip()[:48]}', '💬')
                save()
                haptic('light')
                st.rerun()


def _following_lists(user: dict) -> None:
    c1, c2 = st.columns(2, gap='medium')
    with c1:
        st.markdown('<div class="cf-eyebrow">Following</div>', unsafe_allow_html=True)
        ids = follows(user['id'])
        if not ids:
            st.caption('Nobody yet.')
        for uid in ids:
            other = users().get(uid)
            if not other:
                continue
            st.markdown(f'<div class="cf-panel cf-flat" style="margin-bottom:.4rem">'
                        f'{user_chip(other, 32)}</div>', unsafe_allow_html=True)
            if st.button('Unfollow', key=f'unf_{uid}', use_container_width=True):
                _follow(user, uid)
                st.rerun()
    with c2:
        st.markdown('<div class="cf-eyebrow">Followers</div>', unsafe_allow_html=True)
        ids = followers(user['id'])
        if not ids:
            st.caption('Nobody yet.')
        for uid in ids:
            other = users().get(uid)
            if other:
                st.markdown(f'<div class="cf-panel cf-flat" style="margin-bottom:.4rem">'
                            f'{user_chip(other, 32)}</div>', unsafe_allow_html=True)


def render(user: dict) -> None:
    section('People', 'Follow thinkers, argue with friends, share what you find.', 'Social')
    pending = sum(1 for r in db()['friend_requests']
                  if r['to'] == user['id'] and r['status'] == 'pending')
    tabs = st.tabs(['Discover', f'Requests {pending or ""}'.strip(), 'Messages', 'Connections'])
    with tabs[0]:
        _discover(user)
    with tabs[1]:
        _requests(user)
    with tabs[2]:
        _messages(user)
    with tabs[3]:
        _following_lists(user)


# ---------------------------------------------------------------- public profile

def render_public_profile(user: dict, target_id: str) -> None:
    target = users().get(target_id)
    if not target:
        empty_state('👤', 'Profile not found', 'That account no longer exists.')
        return
    private = not target.get('settings', {}).get('privacy', {}).get('public_profile', True)
    if private and target_id != user['id']:
        empty_state('🔒', 'This profile is private', 'Only the owner can see it.')
        return

    stats = engine.user_stats(target)
    from .profile import profile_header
    profile_header(target, stats)

    c1, c2, c3, c4 = st.columns(4)
    following = target_id in follows(user['id'])
    if c1.button('Following' if following else 'Follow', key='pub_follow',
                 use_container_width=True, type='secondary' if following else 'primary'):
        _follow(user, target_id)
        st.rerun()
    is_friend = target_id in friends(user['id'])
    if c2.button('Friends ✓' if is_friend else 'Add friend', key='pub_friend',
                 use_container_width=True, disabled=is_friend):
        _request_friend(user, target_id)
        st.toast('Friend request sent.', icon='🤝')
    if c3.button('Message', key='pub_msg', use_container_width=True):
        if not can_message(user, target):
            st.warning('This person only accepts messages from friends.')
        else:
            thread = _thread_between(user['id'], target_id)
            st.session_state['open_thread'] = thread['id']
            go('social')
            st.rerun()
    blocked = target_id in user.get('blocked', [])
    if c4.button('Unblock' if blocked else 'Block', key='pub_block', use_container_width=True):
        blocked_list = user.setdefault('blocked', [])
        if blocked:
            blocked_list.remove(target_id)
        else:
            blocked_list.append(target_id)
            if target_id in follows(user['id']):
                follows(user['id']).remove(target_id)
        save()
        st.rerun()

    if target.get('settings', {}).get('privacy', {}).get('show_stats', True):
        from .stats import stat_grid, achievement_wall
        stat_grid(stats)
        achievement_wall(target)

    recent = [(cid, i) for cid, i in interactions(target_id).items() if i.get('answered_at')]
    recent.sort(key=lambda pair: pair[1]['answered_at'], reverse=True)
    if recent:
        st.markdown('<div class="cf-eyebrow" style="margin:.9rem 0 .4rem">Recent activity</div>',
                    unsafe_allow_html=True)
        from ..store import card as get_card
        for cid, inter in recent[:6]:
            card = get_card(cid)
            if not card:
                continue
            answer = ''
            if isinstance(inter.get('answer'), int) and card.get('options'):
                idx = inter['answer']
                if idx < len(card['options']):
                    answer = f' → “{card["options"][idx]}”'
            st.markdown(f'<div class="cf-panel cf-flat" style="margin-bottom:.4rem">'
                        f'<div class="cf-eyebrow">{esc(card["type"])} · {ago(inter["answered_at"])}'
                        f'</div><div class="cf-body">{esc(card["title"])}{esc(answer)}</div></div>',
                        unsafe_allow_html=True)
