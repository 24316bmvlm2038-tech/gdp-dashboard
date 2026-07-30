"""Sign in, sign up, guest mode, email verification, 2FA and password reset."""

from __future__ import annotations

import secrets

import streamlit as st

from .. import auth
from ..models import now_iso
from ..store import save
from .components import esc

HERO_POINTS = [
    ('🧠', 'Questions, not noise', 'Debates, mysteries, brain teasers and predictions — '
                                   'chosen for the way you think.'),
    ('🔥', 'A streak worth keeping', 'Ten daily rituals, XP, levels and achievements that '
                                     'reward curiosity instead of time spent.'),
    ('🤖', 'An AI that argues back', 'Ask it to explain, teach, debate you, or build a '
                                     'study plan in seconds.'),
]


def _hero() -> None:
    st.markdown(
        f"""<div class="cf-in" style="text-align:center;margin:1.6rem 0 1.1rem">
              <div class="cf-orb" style="width:64px;height:64px;border-radius:22px;margin:0 auto .9rem;
                   font-size:30px">◎</div>
              <div class="cf-display">Curiosity Feed</div>
              <div class="cf-sub" style="max-width:520px;margin:0 auto">
                An antidote to doom-scrolling. A personalised feed of fascinating questions,
                debates, mysteries and challenges — and an AI that thinks with you.</div>
            </div>""", unsafe_allow_html=True)
    cols = st.columns(3, gap='medium')
    for col, (icon, title, body) in zip(cols, HERO_POINTS):
        with col:
            st.markdown(
                f'<div class="cf-card cf-in cf-d2" style="padding:1.1rem">'
                f'<div style="font-size:1.5rem">{icon}</div>'
                f'<div style="font-weight:720;color:var(--text);margin:.35rem 0 .2rem">'
                f'{esc(title)}</div><div class="cf-body" style="font-size:.9rem">{esc(body)}</div>'
                f'</div>', unsafe_allow_html=True)


def _finish_login(user: dict) -> None:
    if user.get('twofa') and user.get('totp_secret'):
        st.session_state['pending_2fa'] = user['id']
    else:
        auth.login(user['id'])
    st.rerun()


def _sign_in_tab() -> None:
    with st.form('signin', border=False):
        email = st.text_input('Email', placeholder='you@example.com')
        password = st.text_input('Password', type='password')
        c1, c2 = st.columns([0.55, 0.45])
        submitted = c1.form_submit_button('Sign in', type='primary', use_container_width=True)
        forgot = c2.form_submit_button('Forgot password?', use_container_width=True)
    if forgot:
        st.session_state['auth_mode'] = 'reset'
        st.rerun()
    if submitted:
        user = auth.find_by_email(email)
        if not user or not auth.verify_password(password, user.get('pw_hash', ''),
                                                user.get('pw_salt', '')):
            st.error('Wrong email or password.')
        else:
            _finish_login(user)


def _sign_up_tab() -> None:
    with st.form('signup', border=False):
        name = st.text_input('Display name', placeholder='Ada Lovelace')
        email = st.text_input('Email', placeholder='you@example.com')
        password = st.text_input('Password', type='password',
                                 help='At least 8 characters. Longer beats complicated.')
        confirm = st.text_input('Confirm password', type='password')
        agreed = st.checkbox('I agree to the community guidelines and privacy policy.')
        submitted = st.form_submit_button('Create account', type='primary',
                                          use_container_width=True)
    if password:
        score, label = auth.password_strength(password)
        st.progress(score / 4, text=f'Password strength: {label}')
    if submitted:
        if not name.strip():
            st.error('Pick a display name.')
        elif not auth.EMAIL_RE.match(email):
            st.error('That email address does not look right.')
        elif auth.find_by_email(email):
            st.error('An account with that email already exists.')
        elif len(password) < 8:
            st.error('Passwords need at least 8 characters.')
        elif password != confirm:
            st.error('The two passwords do not match.')
        elif not agreed:
            st.error('Please accept the guidelines to continue.')
        else:
            user = auth.create_user(name=name, email=email, password=password)
            auth.promote_first_admin(user)
            auth.send_email(email, 'Verify your Curiosity Feed account',
                            f'Your code is {user["verify_code"]}')
            auth.login(user['id'])
            st.rerun()


def _reset_view() -> None:
    st.markdown('<div class="cf-eyebrow">Password reset</div>', unsafe_allow_html=True)
    email = st.text_input('Account email', key='reset_email')
    if st.button('Send reset code', type='primary', use_container_width=True):
        user = auth.find_by_email(email)
        if not user:
            st.error('No account with that email.')
        else:
            user['reset_code'] = f'{secrets.randbelow(1_000_000):06d}'
            save()
            delivered = auth.send_email(email, 'Your reset code', user['reset_code'])
            if delivered:
                st.success('Check your inbox for the code.')
            else:
                st.info(f'Email delivery is not configured in this build. '
                        f'Your reset code is **{user["reset_code"]}**.')
    code = st.text_input('Reset code', key='reset_code_input')
    new_password = st.text_input('New password', type='password', key='reset_pw')
    if st.button('Set new password', use_container_width=True):
        user = auth.find_by_email(st.session_state.get('reset_email', ''))
        if not user or not user.get('reset_code') or code.strip() != user['reset_code']:
            st.error('That code is not right.')
        elif len(new_password) < 8:
            st.error('Passwords need at least 8 characters.')
        else:
            user['pw_hash'], user['pw_salt'] = auth.hash_password(new_password)
            user['reset_code'] = ''
            save()
            st.success('Password updated — sign in with it now.')
            st.session_state['auth_mode'] = 'main'
    if st.button('← Back to sign in', use_container_width=True):
        st.session_state['auth_mode'] = 'main'
        st.rerun()


def two_factor_gate() -> None:
    uid = st.session_state['pending_2fa']
    user = auth.users().get(uid)
    if not user:
        st.session_state.pop('pending_2fa')
        st.rerun()
    st.markdown('<div style="height:8vh"></div>', unsafe_allow_html=True)
    _, mid, _ = st.columns([0.2, 0.6, 0.2])
    with mid:
        st.markdown(
            '<div class="cf-card cf-in" style="text-align:center">'
            '<div style="font-size:2rem">🔐</div>'
            '<div class="cf-q" style="font-size:1.3rem">Two-factor authentication</div>'
            '<div class="cf-body">Enter the 6-digit code from your authenticator app.</div></div>',
            unsafe_allow_html=True)
        code = st.text_input('Code', max_chars=6, label_visibility='collapsed',
                             placeholder='000000')
        c1, c2 = st.columns(2)
        if c1.button('Verify', type='primary', use_container_width=True):
            if auth.verify_totp(user['totp_secret'], code):
                st.session_state.pop('pending_2fa')
                auth.login(uid)
                st.rerun()
            else:
                st.error('That code is not valid right now.')
        if c2.button('Cancel', use_container_width=True):
            st.session_state.pop('pending_2fa')
            st.rerun()


def verify_email_banner(user: dict) -> None:
    if user.get('verified_email') or user.get('is_guest'):
        return
    with st.container(key='panelbox_verify'):
        st.markdown(
            f'<div class="cf-row" style="justify-content:space-between">'
            f'<div><div class="cf-eyebrow">Verify your email</div>'
            f'<div class="cf-body">We sent a 6-digit code to {esc(user["email"])}. '
            f'Verifying unlocks messaging and leaderboards.</div></div></div>',
            unsafe_allow_html=True)
        c1, c2, c3 = st.columns([0.4, 0.3, 0.3])
        code = c1.text_input('Code', key='verify_code_input', max_chars=6,
                             label_visibility='collapsed', placeholder='000000')
        if c2.button('Verify', key='verify_go', type='primary', use_container_width=True):
            if code.strip() == user.get('verify_code'):
                user['verified_email'] = True
                user['verify_code'] = ''
                save()
                st.toast('Email verified.', icon='✅')
                st.rerun()
            else:
                st.error('Wrong code.')
        if c3.button('Resend', key='verify_resend', use_container_width=True):
            user['verify_code'] = f'{secrets.randbelow(1_000_000):06d}'
            save()
            if not auth.send_email(user['email'], 'Verify your account', user['verify_code']):
                st.info(f'Email is not configured in this build — your code is '
                        f'**{user["verify_code"]}**.')


def render() -> None:
    """The whole signed-out experience."""
    if st.session_state.get('pending_2fa'):
        two_factor_gate()
        return

    _hero()
    st.markdown('<div class="cf-spacer"></div>', unsafe_allow_html=True)
    _, mid, _ = st.columns([0.16, 0.68, 0.16])
    with mid:
        with st.container(key='panelbox_auth'):
            if st.session_state.get('auth_mode') == 'reset':
                _reset_view()
                return
            tab_in, tab_up = st.tabs(['Sign in', 'Create account'])
            with tab_in:
                _sign_in_tab()
            with tab_up:
                _sign_up_tab()

            st.markdown('<div class="cf-row" style="justify-content:center;margin:.9rem 0 .4rem">'
                        '<span class="cf-meta">or continue with</span></div>',
                        unsafe_allow_html=True)
            g1, g2 = st.columns(2)
            if g1.button('  Continue with Google', key='oauth_google',
                         use_container_width=True):
                st.info('Google Sign-In needs an OAuth client. Add `GOOGLE_CLIENT_ID` to '
                        '`.streamlit/secrets.toml` and enable the Google provider in Supabase '
                        'Auth — see README. Guest mode works right now.')
            if g2.button('  Continue with Apple', key='oauth_apple', use_container_width=True):
                st.info('Apple Sign-In needs a Services ID and key pair. Configure the Apple '
                        'provider in Supabase Auth — see README. Guest mode works right now.')

            if st.button('👤  Continue as guest', key='guest', use_container_width=True,
                         type='primary'):
                user = auth.create_user(name='Guest Explorer', is_guest=True)
                auth.login(user['id'])
                st.rerun()
            st.caption('Guest accounts keep everything locally and can be upgraded to a full '
                       'account at any time without losing progress.')
