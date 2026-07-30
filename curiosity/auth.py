"""Accounts, sessions and credentials.

Passwords are stored as PBKDF2-HMAC-SHA256 hashes with a per-user salt (never
in plain text). Two-factor authentication uses standard TOTP (RFC 6238), so any
authenticator app works. Email verification and password reset issue codes that
this build surfaces in-app — wire ``send_email()`` to a real provider or a
Supabase Edge Function to deliver them for production.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import secrets
import struct
import time

import streamlit as st

from .models import AVATAR_COLORS, now_iso, today_str
from .store import db, log_event, new_id, save, users

PBKDF2_ROUNDS = 240_000
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$')


# ---------------------------------------------------------------- passwords

def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), PBKDF2_ROUNDS)
    return digest.hex(), salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    if not stored_hash or not salt:
        return False
    candidate, _ = hash_password(password, salt)
    return hmac.compare_digest(candidate, stored_hash)


def password_strength(password: str) -> tuple[int, str]:
    """Return ``(score 0-4, label)``."""
    score = 0
    if len(password) >= 8:
        score += 1
    if len(password) >= 12:
        score += 1
    if re.search(r'[A-Z]', password) and re.search(r'[a-z]', password):
        score += 1
    if re.search(r'\d', password) and re.search(r'[^\w\s]', password):
        score += 1
    return score, ['Too short', 'Weak', 'Fair', 'Strong', 'Excellent'][score]


# ---------------------------------------------------------------- TOTP (2FA)

def new_totp_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode().rstrip('=')


def totp_code(secret: str, at: float | None = None, step: int = 30) -> str:
    padded = secret + '=' * (-len(secret) % 8)
    key = base64.b32decode(padded, casefold=True)
    counter = int((at or time.time()) // step)
    mac = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = struct.unpack('>I', mac[offset:offset + 4])[0] & 0x7FFFFFFF
    return f'{code % 1_000_000:06d}'


def verify_totp(secret: str, code: str, window: int = 1) -> bool:
    code = (code or '').strip().replace(' ', '')
    if not code.isdigit():
        return False
    now = time.time()
    return any(hmac.compare_digest(totp_code(secret, now + drift * 30), code)
               for drift in range(-window, window + 1))


def otpauth_uri(secret: str, email: str) -> str:
    label = f'CuriosityFeed:{email}'.replace(' ', '%20')
    return f'otpauth://totp/{label}?secret={secret}&issuer=CuriosityFeed&algorithm=SHA1&digits=6&period=30'


# ---------------------------------------------------------------- messaging

def send_email(to: str, subject: str, body: str) -> bool:
    """Hook for a real transactional email provider.

    Returns False in this build, which makes the UI show the code on screen
    instead of pretending a message was delivered.
    """
    log_event('email_queued', None, to=to, subject=subject)
    return False


# ---------------------------------------------------------------- accounts

def _unique_handle(base: str) -> str:
    handle = re.sub(r'[^a-z0-9_]', '', base.lower().replace(' ', '_'))[:18] or 'curious'
    handles = db()['handles']
    if handle not in handles:
        return handle
    for n in range(2, 999):
        candidate = f'{handle}{n}'
        if candidate not in handles:
            return candidate
    return f'{handle}_{secrets.token_hex(3)}'


def default_settings() -> dict:
    return {
        'theme': 'System',
        'font_size': 'Default',
        'motion': True,
        'haptics': True,
        'language': 'English',
        'reduce_data': False,
        'notifications': {
            'daily_reminder': True, 'friend_activity': True, 'replies': True,
            'likes': True, 'comments': True, 'achievements': True,
            'trending': True, 'followers': True, 'ai_recommendations': True,
        },
        'privacy': {
            'public_profile': True, 'show_stats': True, 'allow_messages': 'Everyone',
            'show_in_leaderboards': True, 'personalised_ai': True,
        },
    }


def create_user(*, name: str, email: str = '', password: str = '',
                is_guest: bool = False, role: str = 'user') -> dict:
    uid = new_id('u')
    handle = _unique_handle(name if not is_guest else 'guest')
    pw_hash, salt = hash_password(password) if password else ('', '')
    user = {
        'id': uid,
        'name': name.strip() or 'Curious Human',
        'handle': handle,
        'email': email.strip().lower(),
        'pw_hash': pw_hash,
        'pw_salt': salt,
        'is_guest': is_guest,
        'role': role,
        'verified_email': is_guest,
        'verify_code': '' if is_guest else f'{secrets.randbelow(1_000_000):06d}',
        'reset_code': '',
        'totp_secret': '',
        'twofa': False,
        'color': AVATAR_COLORS[secrets.randbelow(len(AVATAR_COLORS))],
        'banner': 'indigo',
        'bio': '',
        'country': 'Other',
        'verified_creator': False,
        'premium': False,
        'onboarded': False,
        'interests': [],
        'learning_style': '',
        'difficulty': 3,
        'created_at': now_iso(),
        'last_seen': now_iso(),
        'xp': 0,
        'streak': {'current': 0, 'longest': 0, 'last_day': '', 'days': []},
        'achievements': [],
        'blocked': [],
        'settings': default_settings(),
        'counters': {
            'answers': 0, 'quiz_correct': 0, 'quiz_total': 0, 'debates': 0,
            'bookmarks': 0, 'comments': 0, 'shares': 0, 'challenges': 0,
            'reading_seconds': 0, 'assistant_msgs': 0, 'night_answers': 0,
            'notes': 0,
        },
        'topics': {},          # category -> times engaged
        'type_affinity': {},   # card type -> score
        'daily_done': {},      # date -> [slot names]
    }
    users()[uid] = user
    db()['handles'][handle] = uid
    if user['email']:
        db()['emails'][user['email']] = uid
    log_event('signup', uid, guest=is_guest)
    save()
    return user


def find_by_email(email: str) -> dict | None:
    uid = db()['emails'].get((email or '').strip().lower())
    return users().get(uid) if uid else None


def find_by_handle(handle: str) -> dict | None:
    uid = db()['handles'].get((handle or '').lstrip('@').lower())
    return users().get(uid) if uid else None


def login(uid: str) -> None:
    st.session_state['uid'] = uid
    user = users().get(uid)
    if user:
        user['last_seen'] = now_iso()
        log_event('login', uid)
        save()


def logout() -> None:
    for key in ('uid', 'route', 'pending_2fa', 'feed_cursor', 'assistant_draft'):
        st.session_state.pop(key, None)


def current_user() -> dict | None:
    uid = st.session_state.get('uid')
    if not uid:
        return None
    user = users().get(uid)
    if user is None:
        st.session_state.pop('uid', None)
    return user


def is_admin(user: dict | None) -> bool:
    return bool(user and (user.get('role') == 'admin'))


def promote_first_admin(user: dict) -> None:
    """The first registered account owns the admin dashboard."""
    if any(u.get('role') == 'admin' for u in users().values()):
        return
    user['role'] = 'admin'
    save()


def upgrade_guest(user: dict, name: str, email: str, password: str) -> tuple[bool, str]:
    if not EMAIL_RE.match(email):
        return False, 'That email address does not look right.'
    if find_by_email(email):
        return False, 'An account with that email already exists.'
    user['name'] = name.strip() or user['name']
    user['email'] = email.strip().lower()
    user['pw_hash'], user['pw_salt'] = hash_password(password)
    user['is_guest'] = False
    user['verified_email'] = False
    user['verify_code'] = f'{secrets.randbelow(1_000_000):06d}'
    db()['emails'][user['email']] = user['id']
    save()
    return True, 'Account created — verify your email to finish.'


def delete_account(user: dict) -> None:
    uid = user['id']
    data = db()
    data['handles'].pop(user.get('handle', ''), None)
    data['emails'].pop(user.get('email', ''), None)
    for bucket in ('users', 'interactions', 'collections', 'follows', 'friends',
                   'notifications', 'assistant'):
        data[bucket].pop(uid, None)
    for followers in data['follows'].values():
        if uid in followers:
            followers.remove(uid)
    for cid, thread in list(data['comments'].items()):
        data['comments'][cid] = [c for c in thread if c.get('uid') != uid]
    data['friend_requests'] = [r for r in data['friend_requests']
                               if uid not in (r.get('from'), r.get('to'))]
    log_event('account_deleted', uid)
    save()
    logout()


def export_data(user: dict) -> dict:
    """Everything the app holds about one account, for GDPR-style export."""
    uid = user['id']
    data = db()
    safe = {k: v for k, v in user.items() if k not in ('pw_hash', 'pw_salt', 'totp_secret',
                                                       'verify_code', 'reset_code')}
    return {
        'exported_at': now_iso(),
        'profile': safe,
        'interactions': data['interactions'].get(uid, {}),
        'collections': data['collections'].get(uid, {}),
        'comments': {cid: [c for c in thread if c.get('uid') == uid]
                     for cid, thread in data['comments'].items()
                     if any(c.get('uid') == uid for c in thread)},
        'assistant_history': data['assistant'].get(uid, []),
        'following': data['follows'].get(uid, []),
        'notifications': data['notifications'].get(uid, []),
    }


def touch_session(user: dict) -> None:
    """Update presence and roll the streak forward on first visit of a day."""
    user['last_seen'] = now_iso()
    streak = user.setdefault('streak', {'current': 0, 'longest': 0, 'last_day': '', 'days': []})
    today = today_str()
    if today not in streak.setdefault('days', []):
        streak['days'].append(today)
        del streak['days'][:-400]
