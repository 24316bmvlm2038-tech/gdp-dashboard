"""Curiosity Feed — questions, learning, and discovery."""

from __future__ import annotations

import streamlit as st

from curiosity import auth, engine
from curiosity.models import CATEGORIES, now_iso
from curiosity.store import db, notify, save, users
from curiosity.theme import inject
from curiosity.ui import auth_view, onboarding
from curiosity.ui import (assistant, collections_view, daily, explore, feed,
                          social)
from curiosity.ui.components import floating_nav, top_bar

st.set_page_config(
    page_title='Curiosity Feed',
    page_icon='🧠',
    layout='wide',
    initial_sidebar_state='collapsed',
)

inject()

user = auth.current_user()

if not user:
    if st.session_state.get('page') == 'auth':
        auth_view.render()
    else:
        auth_view.render()
    st.stop()

if not user.get('onboarded'):
    onboarding.render(user)
    st.stop()

auth.touch_session(user)

with st.sidebar:
    st.markdown('<div class="cf-spacer"></div>', unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button('⚙️', key='settings_btn', help='Settings',
                     use_container_width=True):
            st.session_state['page'] = 'settings'
    with col2:
        if st.button('📊', key='admin_btn', help='Admin' if user.get('admin') else 'Stats',
                     use_container_width=True):
            st.session_state['page'] = 'admin' if user.get('admin') else 'stats'
    with col3:
        if st.button('👤', key='profile_btn', help='Profile',
                     use_container_width=True):
            st.session_state['page'] = 'profile'
    st.divider()
    if st.button('Logout', key='logout_btn', use_container_width=True):
        auth.logout()
        st.rerun()

top_bar(user)

page = st.session_state.get('page', 'feed')

if page == 'feed':
    feed.render(user)
elif page == 'daily':
    daily.render(user)
elif page == 'explore':
    explore.render(user)
elif page == 'assistant':
    assistant.render(user)
elif page == 'collections':
    collections_view.render(user)
elif page == 'social':
    social.render(user)
elif page == 'card':
    focus_id = st.session_state.get('focus_card')
    from curiosity.store import card as get_card
    from curiosity.ui.components import render_card
    card = get_card(focus_id)
    if card:
        render_card(user, card)
        if st.button('← Back', key='back_from_card'):
            st.session_state['page'] = st.session_state.get('prev_page', 'feed')
            st.rerun()
    else:
        st.error('Card not found')
elif page == 'user':
    focus_id = st.session_state.get('focus_user')
    if focus_id and focus_id in users():
        social.render_public_profile(user, focus_id)
        if st.button('← Back', key='back_from_user'):
            st.session_state['page'] = st.session_state.get('prev_page', 'social')
            st.rerun()
    else:
        st.error('User not found')
elif page == 'settings':
    st.title('⚙️ Settings')
    st.divider()
    st.subheader('Account')
    if st.button('Change password', key='chg_pwd'):
        st.session_state['subpage'] = 'password'
    if st.button('Two-factor authentication', key='2fa'):
        st.session_state['subpage'] = '2fa'
    if st.button('Export data', key='export'):
        data = auth.export_data(user)
        import json
        st.download_button('Download JSON', json.dumps(data, indent=2),
                          file_name='curiosity-export.json')
    st.divider()
    st.subheader('Privacy & notifications')
    settings = user.setdefault('settings', {})
    privacy = settings.setdefault('privacy', {})
    notif = settings.setdefault('notifications', {})
    if st.checkbox('Public profile', value=privacy.get('public_profile', True),
                   key='pub_profile'):
        privacy['public_profile'] = True
    else:
        privacy['public_profile'] = False
    if st.checkbox('Show stats on profile', value=privacy.get('show_stats', True),
                   key='show_stats'):
        privacy['show_stats'] = True
    else:
        privacy['show_stats'] = False
    st.caption('Message privacy')
    allow_msg = st.radio('Allow messages from',
                        ['Everyone', 'Friends only', 'Nobody'],
                        index=['Everyone', 'Friends only', 'Nobody'].index(
                            privacy.get('allow_messages', 'Everyone')),
                        key='msg_policy')
    privacy['allow_messages'] = allow_msg
    st.caption('Notifications')
    notif['followers'] = st.checkbox('New followers', value=notif.get('followers', True),
                                     key='notif_followers')
    notif['messages'] = st.checkbox('New messages', value=notif.get('messages', True),
                                    key='notif_messages')
    notif['likes'] = st.checkbox('Likes on my answers', value=notif.get('likes', True),
                                 key='notif_likes')
    if st.button('Save settings', key='save_settings', type='primary'):
        save()
        st.success('Settings saved')
        st.rerun()
    st.divider()
    if st.button('🗑️ Delete my account', key='delete_account'):
        st.session_state['confirm_delete'] = True
    if st.session_state.get('confirm_delete'):
        st.warning('This cannot be undone.')
        if st.button('Yes, delete everything', key='confirm_delete_yes', type='secondary'):
            auth.delete_account(user['id'])
            auth.logout()
            st.rerun()
        if st.button('Cancel', key='cancel_delete'):
            st.session_state['confirm_delete'] = False
            st.rerun()
elif page == 'profile':
    st.title('👤 Your profile')
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input('Name', value=user.get('name', ''), key='edit_name')
        handle = st.text_input('Handle', value=user.get('handle', ''), key='edit_handle',
                              help='Your unique username')
    with col2:
        bio = st.text_area('Bio', value=user.get('bio', ''), key='edit_bio',
                          height=90, max_chars=280)
    country = st.text_input('Country', value=user.get('country', ''), key='edit_country')
    st.caption('Interests')
    interests = user.get('interests', [])
    selected = []
    cols = st.columns(4)
    for i, (cat, meta) in enumerate(CATEGORIES.items()):
        with cols[i % 4]:
            if st.checkbox(f'{meta["emoji"]} {cat}', value=cat in interests,
                          key=f'int_{cat}'):
                selected.append(cat)
    if st.button('Save profile', key='save_profile', type='primary'):
        user['name'] = name.strip() or user.get('name', 'Anon')
        user['handle'] = handle.strip() or user.get('handle', 'user')
        user['bio'] = bio.strip()
        user['country'] = country.strip()
        user['interests'] = selected
        save()
        st.success('Profile updated')
elif page == 'stats':
    st.title('📊 Your stats')
    st.divider()
    stats = engine.user_stats(user)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric('Level', stats['level'], f"+{stats['xp_this_level']} XP")
    with col2:
        st.metric('Streak', f"{stats['streak']} days", 'Keep going!')
    with col3:
        st.metric('Total XP', stats['xp'])
    with col4:
        st.metric('Answers', stats['total_answered'])
    st.divider()
    st.subheader('Activity')
    hm_data = engine.heatmap_days(user)
    st.caption('Days you answered at least one card (last 30 days)')
    if hm_data:
        st.bar_chart(hm_data)
    monthly = engine.monthly_progress(user)
    if monthly:
        st.caption('Cards answered per week')
        st.bar_chart(monthly)
    st.divider()
    st.subheader('Leaderboard')
    lb_type = st.radio('Show', ['Friends', 'Country', 'Global'], horizontal=True,
                       key='lb_type')
    board = engine.leaderboard(user, lb_type.lower(), 10)
    if board:
        for rank, (name, xp, level) in enumerate(board, 1):
            cols = st.columns([0.1, 0.5, 0.2, 0.2])
            cols[0].metric('#', rank)
            cols[1].write(f'**{name}** Level {level}')
            cols[2].metric('XP', xp)
elif page == 'admin':
    if not user.get('admin'):
        st.error('Admin access required')
        st.stop()
    st.title('🛠️ Admin')
    st.divider()
    all_users = users()
    st.metric('Total users', len(all_users))
    st.metric('Total cards', len(db()['content']))
    st.subheader('Users')
    for uid, u in sorted(all_users.items(), key=lambda x: x[1].get('created_at', ''), reverse=True)[:20]:
        col1, col2, col3 = st.columns([0.5, 0.3, 0.2])
        col1.write(f"{u.get('name', 'Anon')} (@{u.get('handle', 'user')})")
        col2.write(f"Level {engine.user_stats(u)['level']}")
        if col3.button('Ban', key=f'ban_{uid}'):
            u['banned'] = True
            save()
            st.rerun()

floating_nav(user, page)
