"""Clode — a Claude-style chat assistant.

The UI is a chat client with saved conversations. Behind it sit two backends
(see ``clode/backends.py``):

* the real Claude API, when ``ANTHROPIC_API_KEY`` is configured;
* otherwise ``Clode-mini``, a ~3.5M parameter transformer written from scratch
  in NumPy (``clode/model.py``) and trained on this machine by ``clode.train``.

Conversations persist to ``data/chats.json``.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st

from clode import search as websearch
from clode.backends import (
    API_MODELS,
    DEFAULT_SYSTEM,
    AnthropicBackend,
    LocalBackend,
    Message,
    describe_status,
)

st.set_page_config(page_title='Clode', page_icon='✳️', layout='wide')

DATA_DIR = Path(__file__).parent / 'data'
CHATS_FILE = DATA_DIR / 'chats.json'
DATA_DIR.mkdir(parents=True, exist_ok=True)

STYLE = """
<style>
  :root { --clode-accent: #d97757; --clode-ink: #1f1e1c; }
  .stApp { background: #faf9f5; }
  section[data-testid='stSidebar'] { background: #f0eee6; border-right: 1px solid #e5e1d6; }
  .block-container { padding-top: 2.2rem; max-width: 52rem; }
  .clode-title {
    font-family: Georgia, 'Times New Roman', serif;
    font-size: 2.4rem; color: var(--clode-ink); margin: 0 0 .2rem 0;
  }
  .clode-title span { color: var(--clode-accent); }
  .clode-sub { color: #6b6862; margin-bottom: 1.6rem; font-size: .95rem; }
  .stChatMessage { background: transparent; border: none; }
  .stChatMessage[data-testid='stChatMessage']:has(+ div) { margin-bottom: .2rem; }
  div[data-testid='stChatMessageContent'] p { line-height: 1.65; }
  .clode-pill {
    display: inline-block; padding: .18rem .55rem; border-radius: 999px;
    font-size: .72rem; border: 1px solid #ded9cc; background: #fff; color: #6b6862;
  }
  .clode-pill.on { border-color: var(--clode-accent); color: var(--clode-accent); }
  .searchline { font-size: .88rem; padding-top: .55rem; color: #6b6862; }
  .searchline.on { color: var(--clode-accent); }
  .searchline b { color: inherit; }
  .rule { border-top: 1px solid #e5e1d6; margin: .35rem 0 .9rem; }
  .src { font-size: .8rem; opacity: .6; }
  @media (prefers-color-scheme: dark) {
    .searchline { color: #a8a49b; }
    .rule { border-top-color: #35342f; }
  }
  @media (prefers-color-scheme: dark) {
    .stApp { background: #262624; }
    section[data-testid='stSidebar'] { background: #1f1e1d; border-right-color: #35342f; }
    .clode-title { color: #f5f4ee; }
    .clode-sub { color: #a8a49b; }
    .clode-pill { background: #2c2b28; border-color: #3d3b35; color: #a8a49b; }
  }
</style>
"""
st.markdown(STYLE, unsafe_allow_html=True)


# --------------------------------------------------------------------------
# persistence
# --------------------------------------------------------------------------

def load_chats() -> dict:
    if CHATS_FILE.exists():
        try:
            return json.loads(CHATS_FILE.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            pass
    return {'chats': {}, 'order': []}


def save_chats(store: dict) -> None:
    CHATS_FILE.write_text(json.dumps(store, indent=1), encoding='utf-8')


def new_chat(store: dict) -> str:
    chat_id = uuid.uuid4().hex[:12]
    store['chats'][chat_id] = {
        'title': 'New chat',
        'created': datetime.now().isoformat(timespec='seconds'),
        'messages': [],
    }
    store['order'].insert(0, chat_id)
    return chat_id


def title_from(text: str) -> str:
    clean = ' '.join(text.split())
    return clean[:38] + ('…' if len(clean) > 38 else '')


if 'store' not in st.session_state:
    st.session_state.store = load_chats()
store = st.session_state.store

if not store['order']:
    st.session_state.current = new_chat(store)
    save_chats(store)
if 'current' not in st.session_state or st.session_state.current not in store['chats']:
    st.session_state.current = store['order'][0]


# --------------------------------------------------------------------------
# backend selection
# --------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def get_local_backend(mtime: float):
    """Cached on the weights' mtime so a fresh checkpoint is picked up."""
    return LocalBackend()


status = describe_status()
api_ready = status['api_key'] and status['sdk']

with st.sidebar:
    st.markdown('### ✳️ Clode')
    if st.button('＋  New chat', use_container_width=True):
        st.session_state.current = new_chat(store)
        save_chats(store)
        st.rerun()

    st.markdown('---')
    options = []
    if api_ready:
        options.append('Claude API')
    if status['local_weights']:
        options.append('Clode-mini (local)')
    if not options:
        options = ['Clode-mini (local)']

    engine = st.radio('Engine', options, index=0, key='engine')
    model_id = 'claude-opus-5'
    if engine == 'Claude API':
        model_id = st.selectbox(
            'Model', [m for m, _ in API_MODELS],
            format_func=lambda m: dict(API_MODELS)[m],
        )
        effort = st.select_slider('Effort', ['low', 'medium', 'high', 'xhigh'], value='high')
    else:
        effort = 'high'
        temperature = st.slider('Temperature', 0.1, 1.4, 0.75, 0.05)

    st.markdown('---')
    st.caption('Conversations')
    for chat_id in store['order'][:25]:
        chat = store['chats'][chat_id]
        mark = '●' if chat_id == st.session_state.current else '○'
        if st.button(f'{mark}  {chat["title"]}', key=f'open-{chat_id}',
                     use_container_width=True):
            st.session_state.current = chat_id
            st.rerun()

    st.markdown('---')
    pill = lambda ok, text: (
        f'<span class="clode-pill {"on" if ok else ""}">{"✓" if ok else "○"} {text}</span>'
    )
    st.markdown(
        pill(status['api_key'], 'API key')
        + ' ' + pill(status['local_weights'], 'local weights'),
        unsafe_allow_html=True,
    )
    if not status['api_key']:
        st.caption('Set `ANTHROPIC_API_KEY` to chat with the real Claude models. '
                   'Without it, the locally trained model answers.')


# --------------------------------------------------------------------------
# chat surface
# --------------------------------------------------------------------------

def search_controls(engine: str) -> bool:
    """The web-search switch, stated plainly above the conversation.

    It sits here rather than in the sidebar because whether an answer came off
    the web or out of the model is the single most important thing to know
    about it, and it should be readable without opening anything.
    """
    left, mid, right = st.columns([1, 1, 2.2])
    with left:
        on = st.toggle('🌐  Search the web', value=st.session_state.get('web_on', False),
                       key='web_on')
    with mid:
        if on:
            st.toggle('🔍  Deep search', value=st.session_state.get('deep_on', False),
                      key='deep_on',
                      help='Search, read what comes back, then search again on the '
                           'terms those results introduced.')
    with right:
        if not on:
            st.markdown('<div class="searchline off">Off — answers come only from '
                        'what the model learned during training.</div>',
                        unsafe_allow_html=True)
        elif engine == 'Claude API':
            st.markdown('<div class="searchline on">On — Claude runs the search itself '
                        'and cites what it used.</div>', unsafe_allow_html=True)
        else:
            st.markdown(
                '<div class="searchline on">On — the app searches with '
                f'<b>{websearch.provider_name()}</b> and shows the sources. Clode-mini '
                'cannot read web pages, so it does not answer these.</div>',
                unsafe_allow_html=True)
    return on


def _failure_note(exc: Exception) -> str:
    return (f'⚠️ **The search did not go through.** {exc}\n\n'
            'This machine may block outbound web requests. Setting '
            '`BRAVE_API_KEY` or `SERPER_API_KEY` switches provider.')


def answer_from_web(query: str, deep: bool = False) -> str:
    """Search the web and render the findings, attributed to their sources.

    Deep search runs several rounds, each query chosen from the terms the last
    round's results introduced. Every round is shown as it happens, so what
    was searched is as visible as what came back.
    """
    provider = websearch.provider_name()
    rounds: list[tuple[str, list]] = []
    failures: list[Exception] = []
    label = f'{"Deep search" if deep else "Searching"} with {provider}…'

    with st.status(label, expanded=True) as box:
        try:
            if deep:
                stream = websearch.deep_search(query, rounds=2, limit=4, per_round=2)
            else:
                stream = iter([(query, websearch.search(query, limit=4))])
            for asked, found in stream:
                if isinstance(found, Exception):
                    failures.append(found)
                    st.markdown(f'✗ `{asked}` — {found}')
                    continue
                rounds.append((asked, found))
                st.markdown(f'✓ `{asked}` — {len(found)} results')
        except websearch.SearchError as exc:
            failures.append(exc)

        total = sum(len(r) for _, r in rounds)
        if not total:
            box.update(label='Search failed', state='error')
        else:
            box.update(label=f'{total} results across {len(rounds)} '
                             f'{"searches" if len(rounds) > 1 else "search"}',
                       state='complete')

    if not total:
        message = _failure_note(failures[0]) if failures else \
            f'The search for “{query}” came back empty.'
        st.markdown(message)
        return message

    lines = [f'🌐 **Live from the web** — {provider}, just now', '']
    n = 0
    for asked, found in rounds:
        if len(rounds) > 1:
            lines.append(f'*searched:* `{asked}`')
        for r in found:
            n += 1
            lines.append(f'**{n}. [{r.title}]({r.url})**  \n'
                         f'{r.snippet or "No summary was given for this result."}  \n'
                         f'<span class="src">{r.cite()}</span>\n')
    if failures:
        lines.append(f'<span class="src">{len(failures)} of the searches failed; '
                     'the results above are the ones that came back.</span>\n')
    lines.append('<span class="src">These are the sources\' words, quoted. Clode-mini '
                 'cannot read web pages, so it did not write this answer.</span>')
    body = '\n'.join(lines)
    st.markdown(body, unsafe_allow_html=True)
    return body


chat = store['chats'][st.session_state.current]

st.markdown('<div class="clode-title">Clo<span>de</span></div>', unsafe_allow_html=True)
if engine == 'Claude API':
    st.markdown(
        f'<div class="clode-sub">Talking to <b>{dict(API_MODELS)[model_id]}</b> '
        f'at {effort} effort.</div>', unsafe_allow_html=True)
else:
    detail = ''
    if status['local_weights']:
        try:
            n = get_local_backend(Path('data/clode-mini.npz').stat().st_mtime).n_params
            detail = f' — {n / 1e6:.1f}M parameters, trained from scratch on this machine'
        except Exception:
            detail = ''
    st.markdown(f'<div class="clode-sub">Talking to <b>Clode-mini</b>{detail}.</div>',
                unsafe_allow_html=True)

web_on = search_controls(engine)
st.markdown('<div class="rule"></div>', unsafe_allow_html=True)

for msg in chat['messages']:
    with st.chat_message(msg['role'], avatar='✳️' if msg['role'] == 'assistant' else '🧑'):
        st.markdown(msg['content'])

if not chat['messages']:
    st.info('Ask me something — try "who are you", "what is the capital of Japan", '
            '"how do I reverse a list in Python", or "what is 12 + 30".')

prompt = st.chat_input('Message Clode…')
if prompt:
    chat['messages'].append({'role': 'user', 'content': prompt})
    if chat['title'] == 'New chat':
        chat['title'] = title_from(prompt)
    with st.chat_message('user', avatar='🧑'):
        st.markdown(prompt)

    history = [Message(m['role'], m['content']) for m in chat['messages']]
    with st.chat_message('assistant', avatar='✳️'):
        try:
            if engine == 'Claude API':
                backend = AnthropicBackend(model=model_id)
                system = DEFAULT_SYSTEM
                if web_on and st.session_state.get('deep_on'):
                    system += (' Research thoroughly: search, read what you find, '
                               'then search again on what it raises, before answering. '
                               'Cite the sources you used.')
                reply = st.write_stream(
                    backend.stream(history, system, effort=effort, web_search=web_on))
            elif web_on:
                # Clode-mini cannot read web prose, so the app answers from the
                # source and says so, rather than dressing it up as the model's.
                reply = answer_from_web(prompt, deep=st.session_state.get('deep_on', False))
            else:
                backend = get_local_backend(Path('data/clode-mini.npz').stat().st_mtime)
                reply = st.write_stream(backend.stream(history, temperature=temperature))
        except Exception as exc:  # surface the real reason rather than a blank bubble
            reply = f'⚠️ {type(exc).__name__}: {exc}'
            st.error(reply)

    chat['messages'].append({'role': 'assistant', 'content': reply})
    save_chats(store)
    st.rerun()
