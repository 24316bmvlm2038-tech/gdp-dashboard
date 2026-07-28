"""PulsePlay — a short-video feed and an AI chat assistant in one app.

Two areas:
  * For You: a TikTok-style vertical video feed in a phone frame — snap
    scrolling, autoplay, double-tap to like, comments, share, follow.
    Likes/comments persist in the browser (localStorage). You can also
    add your own video to the feed for the current session.
  * AI Chat: a ChatGPT-style chat with a conversation sidebar. Switch
    between Claude (Anthropic API) and GPT (OpenAI API). A built-in demo
    assistant answers when no API key is configured, so the app always
    works. Conversations persist in ``data/chats.json``.
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title='PulsePlay', page_icon='⚡', layout='wide')

DATA_DIR = Path(__file__).parent / 'data'
DATA_DIR.mkdir(exist_ok=True)
CHATS_FILE = DATA_DIR / 'chats.json'

CLAUDE_MODEL = 'claude-opus-5'
OPENAI_MODEL = 'gpt-4o'

SYSTEM_PROMPT = (
    'You are a helpful, friendly AI assistant inside PulsePlay, an app that '
    'combines a short-video feed with an AI chat. Answer clearly and '
    'concisely, use markdown when it helps, and match the length of your '
    'answer to the question.'
)


# ---------------------------------------------------------------------------
# Chat storage
# ---------------------------------------------------------------------------

def load_chats():
    if CHATS_FILE.exists():
        try:
            return json.loads(CHATS_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {'order': [], 'chats': {}}


def save_chats(store):
    CHATS_FILE.write_text(json.dumps(store, indent=1))


def new_chat(store):
    cid = uuid.uuid4().hex[:12]
    store['chats'][cid] = {
        'title': 'New chat',
        'created': datetime.now().isoformat(timespec='seconds'),
        'messages': [],
    }
    store['order'].insert(0, cid)
    save_chats(store)
    return cid


# ---------------------------------------------------------------------------
# Assistants
# ---------------------------------------------------------------------------

def get_secret(name):
    val = os.environ.get(name, '')
    if not val:
        try:
            val = st.secrets.get(name, '')
        except Exception:
            val = ''
    return val


def stream_claude(api_key, messages):
    """Stream a reply from Claude. Yields text chunks; sets
    st.session_state['_stop_reason'] afterwards."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    kwargs = dict(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        messages=[{'role': m['role'], 'content': m['content']} for m in messages],
    )
    try:
        # Server-side refusal fallback: if Claude's safety classifiers
        # decline, the API retries the request on a fallback model.
        stream_cm = client.beta.messages.stream(
            betas=['server-side-fallback-2026-07-01'],
            extra_body={'fallbacks': 'default'},
            **kwargs,
        )
    except TypeError:
        stream_cm = client.messages.stream(**kwargs)

    with stream_cm as stream:
        for text in stream.text_stream:
            yield text
        final = stream.get_final_message()
    if final.stop_reason == 'refusal':
        yield ('\n\n*Claude declined this request for safety reasons. '
               'Try rephrasing it.*')


def stream_openai(api_key, messages):
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    stream = client.chat.completions.create(
        model=OPENAI_MODEL,
        stream=True,
        messages=[{'role': 'system', 'content': SYSTEM_PROMPT}]
        + [{'role': m['role'], 'content': m['content']} for m in messages],
    )
    for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def stream_demo(messages):
    """Offline assistant used when no API key is configured."""
    import time

    prompt = messages[-1]['content'].strip()
    lower = prompt.lower()
    if any(w in lower for w in ('hello', 'hi', 'hey', 'yo')):
        reply = ("Hey! I'm the built-in demo assistant. Add an Anthropic or "
                 "OpenAI API key in the sidebar to chat with Claude or GPT "
                 "for real. Meanwhile, ask me anything and I'll do my best!")
    elif '?' in prompt:
        reply = (f'Great question! In demo mode I can\'t reason deeply about '
                 f'"{prompt[:80]}" — but once you add an API key in the '
                 f'sidebar, Claude ({CLAUDE_MODEL}) or GPT ({OPENAI_MODEL}) '
                 f'will give you a proper answer with full streaming.')
    else:
        reply = (f'You said: "{prompt[:120]}". I\'m the demo assistant — '
                 'plug in an API key in the sidebar to unlock the real '
                 'Claude and GPT models. Everything else (conversations, '
                 'history, the video feed) already works!')
    for word in reply.split(' '):
        yield word + ' '
        time.sleep(0.02)


# ---------------------------------------------------------------------------
# For You feed (self-contained HTML/JS component)
# ---------------------------------------------------------------------------

FEED_VIDEOS = [
    {
        'src': 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerFun.mp4',
        'user': '@chromecast.fun', 'caption': 'When the weekend finally hits 🎉 #fun #vibes',
        'song': '♫ original sound — chromecast.fun', 'likes': 4231, 'avatar': '🎉',
    },
    {
        'src': 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4',
        'user': '@bunny.films', 'caption': 'Big Buck Bunny never misses 🐰 #animation #classic',
        'song': '♫ Big Buck Bunny theme', 'likes': 12876, 'avatar': '🐰',
    },
    {
        'src': 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerEscapes.mp4',
        'user': '@escape.artist', 'caption': 'POV: you booked the trip ✈️ #travel #escape',
        'song': '♫ wanderlust beats', 'likes': 8054, 'avatar': '✈️',
    },
    {
        'src': 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4',
        'user': '@dream.scenes', 'caption': 'Elephants Dream hits different at 2am 🌌 #scifi',
        'song': '♫ dreamcore mix', 'likes': 6390, 'avatar': '🌌',
    },
    {
        'src': 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4',
        'user': '@blaze.tv', 'caption': 'Movie night just got an upgrade 🔥 #bingewatch',
        'song': '♫ trending sound — blaze.tv', 'likes': 9911, 'avatar': '🔥',
    },
    {
        'src': 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerJoyrides.mp4',
        'user': '@joyride.daily', 'caption': 'Sunday drives >>> everything 🚗 #joyride',
        'song': '♫ open road radio', 'likes': 5478, 'avatar': '🚗',
    },
    {
        'src': 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerMeltdowns.mp4',
        'user': '@meltdown.moments', 'caption': 'Relatable level: 100 😅 #mood',
        'song': '♫ original sound — meltdown.moments', 'likes': 7245, 'avatar': '😅',
    },
]


def feed_html():
    videos_json = json.dumps(FEED_VIDEOS)
    return """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin:0; padding:0; box-sizing:border-box; font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif; }
  body { background:#0b0b0f; display:flex; justify-content:center; align-items:flex-start; }
  .phone { position:relative; width:390px; height:700px; background:#000; border-radius:36px;
           overflow:hidden; border:6px solid #1c1c22; box-shadow:0 18px 60px rgba(0,0,0,.65); }
  .topbar { position:absolute; top:0; left:0; right:0; z-index:30; display:flex; gap:18px;
            justify-content:center; padding:14px 0 8px; color:#fff; font-size:15px; font-weight:600;
            background:linear-gradient(#000a,#0000); pointer-events:none; }
  .topbar .dim { color:#ffffff88; }
  .topbar .active { border-bottom:2px solid #fff; padding-bottom:2px; }
  .feed { height:100%; overflow-y:scroll; scroll-snap-type:y mandatory; scrollbar-width:none; }
  .feed::-webkit-scrollbar { display:none; }
  .slide { position:relative; height:700px; scroll-snap-align:start; scroll-snap-stop:always; background:#000; }
  .slide video { width:100%; height:100%; object-fit:cover; }
  .meta { position:absolute; left:12px; right:76px; bottom:22px; color:#fff; z-index:10;
          text-shadow:0 1px 3px rgba(0,0,0,.8); }
  .meta .user { font-weight:700; font-size:16px; margin-bottom:6px; }
  .meta .cap { font-size:14px; line-height:1.35; margin-bottom:8px; }
  .meta .song { font-size:12.5px; opacity:.9; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .rail { position:absolute; right:10px; bottom:30px; display:flex; flex-direction:column;
          align-items:center; gap:16px; z-index:10; }
  .avatar { position:relative; width:46px; height:46px; border-radius:50%; background:#26262e;
            border:2px solid #fff; display:flex; align-items:center; justify-content:center;
            font-size:22px; cursor:pointer; }
  .avatar .plus { position:absolute; bottom:-8px; left:50%; transform:translateX(-50%);
                  width:18px; height:18px; border-radius:50%; background:#fe2c55; color:#fff;
                  font-size:13px; line-height:17px; text-align:center; font-weight:700; }
  .avatar .plus.followed { background:#2bd97c; }
  .act { display:flex; flex-direction:column; align-items:center; color:#fff; cursor:pointer;
         user-select:none; }
  .act .ico { font-size:30px; filter:drop-shadow(0 1px 3px rgba(0,0,0,.7)); transition:transform .12s; }
  .act:active .ico { transform:scale(1.25); }
  .act .n { font-size:12px; font-weight:600; margin-top:2px; text-shadow:0 1px 2px #000; }
  .liked .ico { color:#fe2c55; }
  .heartburst { position:absolute; z-index:20; font-size:84px; pointer-events:none;
                animation:burst .7s ease-out forwards; }
  @keyframes burst { 0%{transform:scale(.4);opacity:0} 25%{transform:scale(1.15);opacity:1}
                     100%{transform:scale(1) translateY(-46px);opacity:0} }
  .paused-badge { position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);
                  font-size:64px; color:#ffffffcc; z-index:15; pointer-events:none;
                  text-shadow:0 2px 10px #000; }
  .drawer { position:absolute; left:0; right:0; bottom:-62%; height:62%; background:#16161c;
            border-radius:16px 16px 0 0; z-index:40; transition:bottom .25s ease; color:#eee;
            display:flex; flex-direction:column; }
  .drawer.open { bottom:0; }
  .drawer .head { padding:12px; text-align:center; font-size:14px; font-weight:600;
                  border-bottom:1px solid #26262e; position:relative; }
  .drawer .close { position:absolute; right:14px; top:10px; cursor:pointer; color:#aaa; font-size:16px; }
  .drawer .list { flex:1; overflow-y:auto; padding:10px 14px; font-size:14px; }
  .cmt { margin-bottom:12px; }
  .cmt .who { font-weight:700; font-size:12.5px; color:#bbb; }
  .drawer .compose { display:flex; gap:8px; padding:10px; border-top:1px solid #26262e; }
  .drawer input { flex:1; background:#26262e; border:none; border-radius:18px; color:#fff;
                  padding:9px 14px; font-size:14px; outline:none; }
  .drawer button { background:#fe2c55; color:#fff; border:none; border-radius:18px;
                   padding:0 16px; font-weight:700; cursor:pointer; }
  .uploadbar { position:absolute; top:10px; right:12px; z-index:35; }
  .uploadbar label { background:#ffffff22; color:#fff; font-size:12px; padding:6px 10px;
                     border-radius:14px; cursor:pointer; backdrop-filter:blur(4px); }
  .toast { position:absolute; bottom:90px; left:50%; transform:translateX(-50%);
           background:#000c; color:#fff; padding:8px 16px; border-radius:18px; font-size:13px;
           z-index:50; opacity:0; transition:opacity .25s; pointer-events:none; }
  .toast.show { opacity:1; }
</style>
</head>
<body>
<div class="phone">
  <div class="topbar"><span class="dim">Following</span><span class="active">For You</span></div>
  <div class="uploadbar"><label for="upl">＋ Upload</label>
    <input id="upl" type="file" accept="video/*" style="display:none"></div>
  <div class="feed" id="feed"></div>
  <div class="drawer" id="drawer">
    <div class="head">Comments <span class="close" onclick="closeDrawer()">✕</span></div>
    <div class="list" id="cmtlist"></div>
    <div class="compose">
      <input id="cmtinput" placeholder="Add a comment..."
             onkeydown="if(event.key==='Enter')postComment()">
      <button onclick="postComment()">Post</button>
    </div>
  </div>
  <div class="toast" id="toast"></div>
</div>
<script>
const VIDEOS = __VIDEOS__;
const feed = document.getElementById('feed');
const store = {
  get likes()    { return JSON.parse(localStorage.getItem('pp_likes')    || '{}'); },
  get follows()  { return JSON.parse(localStorage.getItem('pp_follows')  || '{}'); },
  get comments() { return JSON.parse(localStorage.getItem('pp_comments') || '{}'); },
  set(key, val)  { localStorage.setItem('pp_' + key, JSON.stringify(val)); },
};
let drawerIdx = null;

function fmt(n) { return n >= 1000 ? (n/1000).toFixed(1).replace(/\\.0$/,'') + 'K' : n; }
function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 1500);
}

function buildSlide(v, i) {
  const el = document.createElement('div');
  el.className = 'slide'; el.dataset.idx = i;
  const liked = !!store.likes[i];
  const followed = !!store.follows[v.user];
  const nCmts = (store.comments[i] || []).length;
  el.innerHTML = `
    <video src="${v.src}" loop muted playsinline preload="metadata"></video>
    <div class="meta">
      <div class="user">${v.user}</div>
      <div class="cap">${v.caption}</div>
      <div class="song">${v.song}</div>
    </div>
    <div class="rail">
      <div class="avatar" onclick="toggleFollow(${i})">${v.avatar}
        <div class="plus ${followed ? 'followed' : ''}" id="plus${i}">${followed ? '✓' : '+'}</div></div>
      <div class="act ${liked ? 'liked' : ''}" id="like${i}" onclick="toggleLike(${i})">
        <div class="ico">${liked ? '❤️' : '🤍'}</div><div class="n" id="likeN${i}">${fmt(v.likes + (liked ? 1 : 0))}</div></div>
      <div class="act" onclick="openDrawer(${i})">
        <div class="ico">💬</div><div class="n" id="cmtN${i}">${nCmts || 'Add'}</div></div>
      <div class="act" onclick="share(${i})"><div class="ico">↗️</div><div class="n">Share</div></div>
    </div>`;
  const vid = el.querySelector('video');
  let lastTap = 0;
  vid.addEventListener('click', () => {
    const now = Date.now();
    if (now - lastTap < 300) { doubleTapLike(el, i); }
    else { setTimeout(() => { if (Date.now() - lastTap >= 300) togglePlay(el, vid); }, 310); }
    lastTap = now;
  });
  return el;
}

function togglePlay(slide, vid) {
  const badge = slide.querySelector('.paused-badge');
  if (vid.paused) { vid.play(); if (badge) badge.remove(); }
  else { vid.pause(); const b = document.createElement('div');
         b.className = 'paused-badge'; b.textContent = '▶'; slide.appendChild(b); }
}

function doubleTapLike(slide, i) {
  if (!store.likes[i]) toggleLike(i);
  const h = document.createElement('div');
  h.className = 'heartburst'; h.textContent = '❤️';
  h.style.left = '150px'; h.style.top = '280px';
  slide.appendChild(h); setTimeout(() => h.remove(), 700);
}

function toggleLike(i) {
  const likes = store.likes; likes[i] = !likes[i]; store.set('likes', likes);
  const btn = document.getElementById('like' + i);
  btn.classList.toggle('liked', likes[i]);
  btn.querySelector('.ico').textContent = likes[i] ? '❤️' : '🤍';
  const base = VIDEOS[i].likes || 0;
  document.getElementById('likeN' + i).textContent = fmt(base + (likes[i] ? 1 : 0));
}

function toggleFollow(i) {
  const user = VIDEOS[i].user, follows = store.follows;
  follows[user] = !follows[user]; store.set('follows', follows);
  document.querySelectorAll('.slide').forEach(s => {
    const j = +s.dataset.idx;
    if (VIDEOS[j] && VIDEOS[j].user === user) {
      const p = document.getElementById('plus' + j);
      p.textContent = follows[user] ? '✓' : '+';
      p.classList.toggle('followed', follows[user]);
    }
  });
  toast(follows[user] ? 'Following ' + user : 'Unfollowed ' + user);
}

function openDrawer(i) {
  drawerIdx = i; renderComments();
  document.getElementById('drawer').classList.add('open');
}
function closeDrawer() { document.getElementById('drawer').classList.remove('open'); }
function renderComments() {
  const list = document.getElementById('cmtlist');
  const cmts = store.comments[drawerIdx] || [];
  list.innerHTML = cmts.length
    ? cmts.map(c => `<div class="cmt"><div class="who">${c.who}</div><div>${c.text
        .replace(/&/g,'&amp;').replace(/</g,'&lt;')}</div></div>`).join('')
    : '<div style="color:#888;text-align:center;margin-top:30px">No comments yet — say something nice!</div>';
  list.scrollTop = list.scrollHeight;
}
function postComment() {
  const inp = document.getElementById('cmtinput');
  const text = inp.value.trim(); if (!text) return;
  const all = store.comments;
  (all[drawerIdx] = all[drawerIdx] || []).push({ who: '@you', text });
  store.set('comments', all); inp.value = '';
  renderComments();
  document.getElementById('cmtN' + drawerIdx).textContent = all[drawerIdx].length;
}

function share(i) {
  const link = VIDEOS[i].src;
  if (navigator.clipboard) navigator.clipboard.writeText(link).catch(() => {});
  toast('Link copied to clipboard');
}

document.getElementById('upl').addEventListener('change', e => {
  const f = e.target.files[0]; if (!f) return;
  const idx = VIDEOS.length;
  VIDEOS.push({ src: URL.createObjectURL(f), user: '@you',
                caption: f.name + ' — uploaded by you 🎬', song: '♫ your sound',
                likes: 0, avatar: '🫵' });
  const slide = buildSlide(VIDEOS[idx], idx);
  feed.insertBefore(slide, feed.firstChild);
  observer.observe(slide);
  feed.scrollTo({ top: 0, behavior: 'smooth' });
  toast('Added to your feed');
});

// Autoplay only the visible slide.
const observer = new IntersectionObserver(entries => {
  entries.forEach(en => {
    const vid = en.target.querySelector('video');
    if (en.isIntersecting && en.intersectionRatio > 0.6) {
      vid.play().catch(() => {});
      const b = en.target.querySelector('.paused-badge'); if (b) b.remove();
    } else { vid.pause(); }
  });
}, { threshold: [0.6] });

VIDEOS.forEach((v, i) => {
  const slide = buildSlide(v, i);
  feed.appendChild(slide);
  observer.observe(slide);
});
</script>
</body>
</html>
""".replace('__VIDEOS__', videos_json)


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def page_feed():
    feed_file = DATA_DIR / 'feed.html'
    feed_file.write_text(feed_html())
    left, mid, right = st.columns([1, 2, 1])
    with mid:
        if hasattr(st, 'iframe'):
            st.iframe(feed_file, height=730)
        else:
            components.html(feed_html(), height=730, scrolling=False)
    with right:
        st.markdown('#### How to use the feed')
        st.markdown(
            '- **Scroll** to snap between videos (autoplay)\n'
            '- **Tap** a video to pause / play\n'
            '- **Double-tap** to like ❤️\n'
            '- **💬** opens comments — yours are saved in your browser\n'
            '- **＋ Upload** adds your own video for this session\n'
            '- **+ on the avatar** follows the creator'
        )
        st.caption('Demo clips are openly licensed sample videos '
                   '(Blender Foundation / Google sample bucket).')


def page_chat():
    store = load_chats()

    # --- sidebar: assistant + keys + conversation list -------------------
    with st.sidebar:
        st.markdown('### 🤖 Assistant')
        provider = st.radio(
            'Model', ['Claude', 'GPT'],
            horizontal=True, label_visibility='collapsed',
        )
        with st.expander('🔑 API keys', expanded=False):
            anthropic_key = st.text_input(
                'Anthropic API key', type='password',
                value=get_secret('ANTHROPIC_API_KEY'))
            openai_key = st.text_input(
                'OpenAI API key', type='password',
                value=get_secret('OPENAI_API_KEY'))
            st.caption('No key? A demo assistant replies instead.')

        st.divider()
        if st.button('＋ New chat', use_container_width=True):
            st.session_state.chat_id = new_chat(store)
            st.rerun()

        for cid in list(store['order']):
            chat = store['chats'][cid]
            c1, c2 = st.columns([5, 1])
            label = chat['title'][:34] or 'New chat'
            if c1.button(label, key=f'open_{cid}', use_container_width=True):
                st.session_state.chat_id = cid
                st.rerun()
            if c2.button('🗑', key=f'del_{cid}'):
                store['order'].remove(cid)
                del store['chats'][cid]
                save_chats(store)
                if st.session_state.get('chat_id') == cid:
                    st.session_state.pop('chat_id', None)
                st.rerun()

    # --- active conversation --------------------------------------------
    if 'chat_id' not in st.session_state or st.session_state.chat_id not in store['chats']:
        if store['order']:
            st.session_state.chat_id = store['order'][0]
        else:
            st.session_state.chat_id = new_chat(store)
    chat = store['chats'][st.session_state.chat_id]

    st.markdown(f"### 💬 {chat['title']}")
    for msg in chat['messages']:
        avatar = '🧑' if msg['role'] == 'user' else ('🟠' if msg.get('by') == 'Claude' else '🟢')
        with st.chat_message(msg['role'], avatar=avatar):
            st.markdown(msg['content'])

    prompt = st.chat_input(f'Message {provider}...')
    if not prompt:
        return

    chat['messages'].append({'role': 'user', 'content': prompt})
    if chat['title'] == 'New chat':
        chat['title'] = prompt[:40]
    save_chats(store)
    with st.chat_message('user', avatar='🧑'):
        st.markdown(prompt)

    key = anthropic_key if provider == 'Claude' else openai_key
    avatar = '🟠' if provider == 'Claude' else '🟢'
    with st.chat_message('assistant', avatar=avatar):
        try:
            if not key:
                reply = st.write_stream(stream_demo(chat['messages']))
                by = 'Demo'
            elif provider == 'Claude':
                reply = st.write_stream(stream_claude(key, chat['messages']))
                by = 'Claude'
            else:
                reply = st.write_stream(stream_openai(key, chat['messages']))
                by = 'GPT'
        except Exception as exc:
            reply = f'⚠️ {provider} request failed: `{exc}`'
            by = provider
            st.markdown(reply)

    chat['messages'].append({'role': 'assistant', 'content': str(reply), 'by': by})
    save_chats(store)


# ---------------------------------------------------------------------------
# App shell
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown('## ⚡ PulsePlay')
    page = st.radio('Go to', ['🎬 For You', '💬 AI Chat'], label_visibility='collapsed')
    st.divider()

if page == '🎬 For You':
    page_feed()
else:
    page_chat()
