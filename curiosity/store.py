"""Persistence for Curiosity Feed.

The default backend is a single JSON document on disk (``data/curiosity.json``)
held in a process-wide cache, so every browser session in the same server
process sees the same data — that is what makes follows, comments and
leaderboards feel live without a database.

If Supabase credentials are configured the same document is mirrored to a
``app_state`` row (see ``supabase/schema.sql``); the local file always stays
the source of truth for reads so the app works offline.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from pathlib import Path
from typing import Any

import streamlit as st

from .models import now_iso

DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
STORE_FILE = DATA_DIR / 'curiosity.json'
MEDIA_DIR = DATA_DIR / 'media'

_LOCK = threading.RLock()

EMPTY: dict[str, Any] = {
    'version': 1,
    'users': {},
    'handles': {},          # handle -> uid
    'emails': {},           # lowercase email -> uid
    'content': {},          # cid -> card
    'votes': {},            # cid -> {option: count}
    'stances': {},          # cid -> {agree/unsure/disagree: count}
    'interactions': {},     # uid -> cid -> {...}
    'comments': {},         # cid -> [comment]
    'collections': {},      # uid -> name -> {emoji, items, shared_with, notes}
    'follows': {},          # uid -> [uid]
    'friends': {},          # uid -> [uid]
    'friend_requests': [],  # {id, from, to, status, at}
    'threads': {},          # tid -> {members, name, messages}
    'notifications': {},    # uid -> [notification]
    'assistant': {},        # uid -> [message]
    'reports': [],
    'daily': {},            # date -> {slot -> cid}
    'events': [],           # lightweight analytics
    'flags': {
        'ai_generation': True,
        'social_feed': True,
        'premium_upsell': True,
        'voice_assistant': True,
        'ai_moderation': True,
        'leaderboards': True,
    },
    'seeded': False,
}


def new_id(prefix: str = 'c') -> str:
    return f'{prefix}_{uuid.uuid4().hex[:12]}'


def _read_disk() -> dict:
    if STORE_FILE.exists():
        try:
            raw = json.loads(STORE_FILE.read_text('utf-8'))
        except (json.JSONDecodeError, OSError):
            backup = STORE_FILE.with_suffix('.corrupt.json')
            try:
                STORE_FILE.replace(backup)
            except OSError:
                pass
            raw = {}
        base = json.loads(json.dumps(EMPTY))
        base.update(raw)
        for key, value in EMPTY.items():
            base.setdefault(key, value)
        return base
    return json.loads(json.dumps(EMPTY))


@st.cache_resource(show_spinner=False)
def _db() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    return _read_disk()


def db() -> dict:
    return _db()


def save() -> None:
    """Atomically write the whole document to disk."""
    with _LOCK:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STORE_FILE.with_suffix('.tmp')
        tmp.write_text(json.dumps(_db(), ensure_ascii=False, indent=1), 'utf-8')
        os.replace(tmp, STORE_FILE)
    _mirror_remote()


# ---------------------------------------------------------------- supabase

def supabase_config() -> tuple[str, str] | None:
    """Read Supabase credentials from secrets or environment, if present."""
    url = key = ''
    try:
        url = st.secrets.get('SUPABASE_URL', '')      # type: ignore[union-attr]
        key = st.secrets.get('SUPABASE_KEY', '')      # type: ignore[union-attr]
    except Exception:
        pass
    url = url or os.environ.get('SUPABASE_URL', '')
    key = key or os.environ.get('SUPABASE_KEY', '')
    return (url, key) if url and key else None


def _mirror_remote() -> None:
    """Best-effort snapshot push to Supabase; never blocks the UI on failure."""
    cfg = supabase_config()
    if not cfg:
        return
    url, key = cfg
    try:
        import urllib.request

        payload = json.dumps({
            'id': 'singleton',
            'document': _db(),
            'updated_at': now_iso(),
        }).encode()
        req = urllib.request.Request(
            f'{url.rstrip("/")}/rest/v1/app_state?on_conflict=id',
            data=payload,
            method='POST',
            headers={
                'apikey': key,
                'Authorization': f'Bearer {key}',
                'Content-Type': 'application/json',
                'Prefer': 'resolution=merge-duplicates',
            },
        )
        urllib.request.urlopen(req, timeout=3).read()
    except Exception:  # offline, bad creds, missing table — stay local
        pass


# ---------------------------------------------------------------- accessors

def users() -> dict:
    return db()['users']


def user(uid: str | None) -> dict | None:
    return db()['users'].get(uid or '')


def content() -> dict:
    return db()['content']


def card(cid: str) -> dict | None:
    return db()['content'].get(cid)


def interactions(uid: str) -> dict:
    return db()['interactions'].setdefault(uid, {})


def interaction(uid: str, cid: str) -> dict:
    return interactions(uid).setdefault(cid, {})


def comments(cid: str) -> list:
    return db()['comments'].setdefault(cid, [])


def collections(uid: str) -> dict:
    return db()['collections'].setdefault(uid, {})


def follows(uid: str) -> list:
    return db()['follows'].setdefault(uid, [])


def followers(uid: str) -> list:
    return [other for other, targets in db()['follows'].items() if uid in targets]


def friends(uid: str) -> list:
    return db()['friends'].setdefault(uid, [])


def notifications(uid: str) -> list:
    return db()['notifications'].setdefault(uid, [])


def notify(uid: str, kind: str, text: str, icon: str = '🔔', link: str | None = None) -> None:
    if not uid:
        return
    notifications(uid).insert(0, {
        'id': new_id('n'), 'kind': kind, 'text': text, 'icon': icon,
        'link': link, 'at': now_iso(), 'read': False,
    })
    del notifications(uid)[80:]


def log_event(kind: str, uid: str | None = None, **extra) -> None:
    events = db()['events']
    events.append({'kind': kind, 'uid': uid, 'at': now_iso(), **extra})
    del events[:-4000]


def flag(name: str) -> bool:
    return bool(db()['flags'].get(name, True))
