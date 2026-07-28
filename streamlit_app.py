"""PulsePlay — a short-video feed and an AI chat assistant in one app.

Two areas:
  * For You: a vertical short-video feed in a phone frame — snap scrolling,
    autoplay, sound toggle, double-tap to like, comments, bookmarks, share,
    follow, a bottom nav bar and a spinning music disc. Real MP4 videos
    (openly licensed sample clips) with loading spinners and progress bar.
    Likes/comments/bookmarks persist in the browser (localStorage).
  * AI Chat: a modern chat with a conversation sidebar. Talk to Claude
    (Anthropic API) with live web search, adjustable reasoning effort,
    visible thinking and image understanding — or to GPT (OpenAI API),
    also with image understanding. A smarter built-in demo assistant
    answers when no API key is configured. Chats persist in
    ``data/chats.json``.
"""

import base64
import json
import os
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title='PulsePlay', page_icon='⚡', layout='wide',
                   initial_sidebar_state='expanded')

DATA_DIR = Path(__file__).parent / 'data'
DATA_DIR.mkdir(exist_ok=True)
CHATS_FILE = DATA_DIR / 'chats.json'

CLAUDE_MODEL = 'claude-opus-5'
OPENAI_MODEL = 'gpt-4o'

EFFORT_LEVELS = {'⚡ Fast': 'low', '⚖️ Balanced': 'high', '🧠 Max power': 'max'}


def system_prompt():
    today = datetime.now().strftime('%A, %B %d, %Y')
    return (
        'You are the AI assistant inside PulsePlay, an app that combines a '
        'short-video feed with an AI chat. You are knowledgeable, sharp and '
        f'genuinely helpful. Today is {today}.\n\n'
        'Guidelines:\n'
        '- Answer directly; lead with the answer, then supporting detail.\n'
        '- Use markdown (headers, bullet points, tables, code blocks) '
        'whenever it makes the answer clearer.\n'
        '- Match length to the question: short for simple questions, '
        'thorough for complex ones.\n'
        '- If you have a web search tool, use it for anything involving '
        'current events, prices, versions, or facts that may have changed.\n'
        '- When the user shares an image, look at it carefully and reference '
        'specific details from it.\n'
        '- Admit uncertainty rather than guessing.'
    )


# ---------------------------------------------------------------------------
# Custom avatars (original inline SVG art, served as data URIs)
# ---------------------------------------------------------------------------

def _svg_avatar(bg1, bg2, glyph):
    svg = (
        f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
        f"<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
        f"<stop offset='0' stop-color='{bg1}'/>"
        f"<stop offset='1' stop-color='{bg2}'/></linearGradient></defs>"
        f"<rect width='64' height='64' rx='16' fill='url(#g)'/>"
        f"<text x='32' y='42' font-size='30' text-anchor='middle' "
        f"fill='white' font-family='Arial'>{glyph}</text></svg>"
    )
    return 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode()


AVATAR_USER = _svg_avatar('#4f7cff', '#8a5cff', '👤')
AVATAR_CLAUDE = _svg_avatar('#e8703a', '#c2410c', '✳')
AVATAR_GPT = _svg_avatar('#10a37f', '#0f766e', '✦')
AVATAR_DEMO = _svg_avatar('#64748b', '#334155', '🤖')

AVATARS = {'Claude': AVATAR_CLAUDE, 'GPT': AVATAR_GPT, 'Demo': AVATAR_DEMO}


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


def get_secret(name):
    val = os.environ.get(name, '')
    if not val:
        try:
            val = st.secrets.get(name, '')
        except Exception:
            val = ''
    return val


# ---------------------------------------------------------------------------
# Assistants
# ---------------------------------------------------------------------------

def _claude_content(msg):
    """Convert a stored message into Anthropic content blocks."""
    blocks = []
    for img in msg.get('images', []):
        blocks.append({
            'type': 'image',
            'source': {'type': 'base64', 'media_type': img['mime'],
                       'data': img['data']},
        })
    blocks.append({'type': 'text', 'text': msg['content'] or 'See the image.'})
    return blocks if msg.get('images') else msg['content']


def _openai_content(msg):
    """Convert a stored message into OpenAI content parts."""
    if not msg.get('images'):
        return msg['content']
    parts = [{'type': 'image_url',
              'image_url': {'url': f"data:{img['mime']};base64,{img['data']}"}}
             for img in msg['images']]
    parts.append({'type': 'text', 'text': msg['content'] or 'See the image.'})
    return parts


def stream_claude(api_key, messages, effort, web_search, show_thinking,
                  thinking_slot):
    """Stream a reply from Claude with web search + adjustable effort."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    kwargs = dict(
        model=CLAUDE_MODEL,
        max_tokens=16000,
        system=system_prompt(),
        output_config={'effort': effort},
        messages=[{'role': m['role'], 'content': _claude_content(m)}
                  for m in messages],
    )
    if web_search:
        kwargs['tools'] = [{'type': 'web_search_20260209', 'name': 'web_search',
                            'max_uses': 5}]
    if show_thinking:
        kwargs['thinking'] = {'type': 'adaptive', 'display': 'summarized'}

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

    thinking_text = ''
    searching_shown = False
    with stream_cm as stream:
        for event in stream:
            if event.type == 'content_block_start':
                block = event.content_block
                if block.type == 'server_tool_use' and not searching_shown:
                    searching_shown = True
                    yield '🔎 *Searching the web…*\n\n'
            elif event.type == 'content_block_delta':
                delta = event.delta
                if delta.type == 'thinking_delta' and thinking_slot is not None:
                    thinking_text += delta.thinking
                    thinking_slot.markdown(thinking_text)
                elif delta.type == 'text_delta':
                    yield delta.text
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
        messages=[{'role': 'system', 'content': system_prompt()}]
        + [{'role': m['role'], 'content': _openai_content(m)}
           for m in messages],
    )
    for chunk in stream:
        if chunk.choices and chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content


def _demo_math(expr):
    """Safely evaluate a plain arithmetic expression, or return None."""
    import ast
    import operator as op

    ops = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
           ast.Div: op.truediv, ast.Pow: op.pow, ast.Mod: op.mod,
           ast.USub: op.neg, ast.UAdd: op.pos, ast.FloorDiv: op.floordiv}

    def ev(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in ops:
            return ops[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in ops:
            return ops[type(node.op)](ev(node.operand))
        raise ValueError

    import re
    pct = re.search(r'(\d+(?:\.\d+)?)\s*%\s*of\s*(\d+(?:\.\d+)?)', expr, re.I)
    if pct:
        return f'{float(pct.group(1)) / 100 * float(pct.group(2)):g}'
    try:
        cleaned = expr.replace('^', '**').replace('x', '*').replace('×', '*')
        cleaned = ''.join(c for c in cleaned if c in '0123456789.+-*/() %')
        if not any(c.isdigit() for c in cleaned):
            return None
        result = ev(ast.parse(cleaned.strip(), mode='eval').body)
        return f'{result:g}'
    except Exception:
        return None


def stream_demo(messages):
    """Offline assistant used when no API key is configured."""
    import random
    import time

    prompt = messages[-1]['content'].strip()
    lower = prompt.lower()

    math = _demo_math(prompt)
    if math is not None:
        reply = f'**{math}**\n\n*(computed offline by the demo assistant)*'
    elif any(w in lower for w in ('hello', 'hi ', 'hey', 'yo ', 'sup')) or lower in ('hi', 'yo'):
        reply = ("Hey! 👋 I'm PulsePlay's built-in demo assistant. I can do "
                 "quick math, tell you the time, or flip a coin — but the "
                 "real magic happens when you add an **Anthropic** or "
                 "**OpenAI** key in the sidebar: then you get Claude with "
                 "live web search, deep reasoning and image understanding, "
                 "or GPT. Try me: `what's 18% of 260?`")
    elif 'time' in lower or 'date' in lower or 'today' in lower:
        now = datetime.now()
        reply = (f"It's **{now.strftime('%H:%M')}** on "
                 f"**{now.strftime('%A, %B %d, %Y')}** (server time).")
    elif 'flip' in lower and 'coin' in lower:
        reply = f'🪙 **{random.choice(["Heads", "Tails"])}!**'
    elif 'roll' in lower and ('dice' in lower or 'die' in lower):
        reply = f'🎲 You rolled a **{random.randint(1, 6)}**!'
    elif 'joke' in lower:
        reply = random.choice([
            'Why do programmers prefer dark mode? Because light attracts bugs. 🐛',
            'I would tell you a UDP joke, but you might not get it. 📡',
            'There are 10 types of people: those who understand binary and those who don\'t.',
        ])
    elif '?' in prompt:
        reply = (f'That\'s a good question — but deep answers need a real '
                 f'model. Add an API key in the sidebar and **Claude** '
                 f'(`{CLAUDE_MODEL}`, with web search and Max-power '
                 f'reasoning) or **GPT** (`{OPENAI_MODEL}`) will answer '
                 f'"{prompt[:80]}" properly, with streaming.')
    else:
        reply = (f'Noted! In demo mode I can handle math, time, coin flips '
                 f'and jokes. For everything else — like "{prompt[:60]}" — '
                 'add an API key in the sidebar to unlock Claude or GPT.')

    for word in reply.split(' '):
        yield word + ' '
        time.sleep(0.015)


# ---------------------------------------------------------------------------
# For You feed (self-contained HTML/JS component)
# ---------------------------------------------------------------------------

_BUCKET = 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/'
ASSETS_DIR = Path(__file__).parent / 'assets'

# Locally generated animated clips, embedded as data URIs. Used as automatic
# fallbacks so the feed keeps playing real video even if the remote CDN is
# unreachable (offline demos, restricted networks).
FALLBACK_CLIPS = ['neon_waves.webm', 'sunset_drive.webm',
                  'hyper_stars.webm', 'blob_party.webm']


def _fallback_data_uris():
    uris = []
    for name in FALLBACK_CLIPS:
        path = ASSETS_DIR / name
        if path.exists():
            b64 = base64.b64encode(path.read_bytes()).decode()
            uris.append(f'data:video/webm;base64,{b64}')
    return uris

FEED_VIDEOS = [
    {'src': _BUCKET + 'ForBiggerFun.mp4', 'user': '@weekend.vibes',
     'caption': 'When the weekend finally hits 🎉 #fun #vibes #fyp',
     'song': 'original sound — weekend.vibes', 'likes': 423100, 'cmts': 1832,
     'saves': 9210, 'shares': 4470, 'avatar': '🎉'},
    {'src': _BUCKET + 'BigBuckBunny.mp4', 'user': '@bunny.films',
     'caption': 'Big Buck Bunny never misses 🐰 the animation holds up #classic',
     'song': 'Big Buck Bunny theme — Blender', 'likes': 1287600, 'cmts': 8213,
     'saves': 45120, 'shares': 12980, 'avatar': '🐰'},
    {'src': _BUCKET + 'ForBiggerEscapes.mp4', 'user': '@escape.artist',
     'caption': 'POV: you finally booked the trip ✈️ #travel #escape #wanderlust',
     'song': 'wanderlust beats — travelcore', 'likes': 805400, 'cmts': 3921,
     'saves': 28800, 'shares': 8120, 'avatar': '✈️'},
    {'src': _BUCKET + 'Sintel.mp4', 'user': '@sintel.official',
     'caption': 'This short film lives rent free in my head 🐉 #sintel #film',
     'song': 'Sintel OST — Blender Studio', 'likes': 2390000, 'cmts': 15400,
     'saves': 88200, 'shares': 31000, 'avatar': '🐉'},
    {'src': _BUCKET + 'ForBiggerBlazes.mp4', 'user': '@blaze.tv',
     'caption': 'Movie night just got a serious upgrade 🔥 #bingewatch #setup',
     'song': 'trending sound — blaze.tv', 'likes': 991100, 'cmts': 4102,
     'saves': 19700, 'shares': 7430, 'avatar': '🔥'},
    {'src': _BUCKET + 'TearsOfSteel.mp4', 'user': '@scifi.daily',
     'caption': 'Practical effects + open source = cinema 🤖 #tearsofsteel #scifi',
     'song': 'Tears of Steel OST', 'likes': 1560000, 'cmts': 9870,
     'saves': 61400, 'shares': 18800, 'avatar': '🤖'},
    {'src': _BUCKET + 'ForBiggerJoyrides.mp4', 'user': '@joyride.daily',
     'caption': 'Sunday drives >>> everything 🚗💨 #joyride #roadtrip',
     'song': 'open road radio — drivetime', 'likes': 547800, 'cmts': 2210,
     'saves': 12300, 'shares': 5100, 'avatar': '🚗'},
    {'src': _BUCKET + 'ElephantsDream.mp4', 'user': '@dream.scenes',
     'caption': 'Elephants Dream hits different at 2am 🌌 #surreal #animation',
     'song': 'dreamcore mix vol. 3', 'likes': 639000, 'cmts': 3480,
     'saves': 21900, 'shares': 6890, 'avatar': '🌌'},
    {'src': _BUCKET + 'WeAreGoingOnBullrun.mp4', 'user': '@bullrun.crew',
     'caption': 'WE. ARE. GOING. 🏁 #bullrun #carsoftiktok',
     'song': 'engine anthem — rev.limit', 'likes': 724500, 'cmts': 3011,
     'saves': 15600, 'shares': 9240, 'avatar': '🏁'},
    {'src': _BUCKET + 'ForBiggerMeltdowns.mp4', 'user': '@meltdown.moments',
     'caption': 'Relatable level: 100 😅 tag someone #mood #meltdown',
     'song': 'original sound — meltdown.moments', 'likes': 724500, 'cmts': 5312,
     'saves': 17300, 'shares': 11020, 'avatar': '😅'},
]

FEED_TEMPLATE = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin:0; padding:0; box-sizing:border-box;
      font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;
      -webkit-tap-highlight-color:transparent; }
  body { background:radial-gradient(1200px 700px at 50% -10%, #1b1b26 0%, #0a0a0e 60%);
         display:flex; justify-content:center; padding-top:4px; }
  .phone { position:relative; width:400px; height:770px; background:#000;
           border-radius:44px; overflow:hidden; border:10px solid #17171d;
           box-shadow:0 0 0 1.5px #2a2a33, 0 30px 80px rgba(0,0,0,.75),
                      0 6px 24px rgba(254,44,85,.08); }
  .notch { position:absolute; top:8px; left:50%; transform:translateX(-50%);
           width:120px; height:24px; background:#000; border:1.5px solid #1d1d24;
           border-radius:14px; z-index:60; }

  .topbar { position:absolute; top:0; left:0; right:0; z-index:30; display:flex; gap:20px;
            justify-content:center; padding:40px 0 10px; color:#fff; font-size:16px;
            font-weight:600; background:linear-gradient(#000b, #0000); pointer-events:none;
            letter-spacing:.2px; }
  .topbar span { pointer-events:auto; cursor:pointer; }
  .topbar .dim { color:#ffffff99; font-weight:500; }
  .topbar .active { position:relative; }
  .topbar .active::after { content:''; position:absolute; left:25%; right:25%;
            bottom:-6px; height:3px; border-radius:2px; background:#fff; }
  .sound { position:absolute; top:42px; left:16px; z-index:35; width:34px; height:34px;
           border-radius:50%; background:#ffffff1f; backdrop-filter:blur(6px);
           display:flex; align-items:center; justify-content:center; cursor:pointer; }
  .sound svg { width:18px; height:18px; fill:#fff; }

  .feed { height:100%; overflow-y:scroll; scroll-snap-type:y mandatory; scrollbar-width:none; }
  .feed::-webkit-scrollbar { display:none; }
  .slide { position:relative; height:750px; scroll-snap-align:start;
           scroll-snap-stop:always; background:#000; overflow:hidden; }
  .slide video { width:100%; height:100%; object-fit:cover; }

  .spinner { position:absolute; top:50%; left:50%; margin:-22px 0 0 -22px; width:44px;
             height:44px; border:3px solid #ffffff2a; border-top-color:#fe2c55;
             border-radius:50%; animation:spin .8s linear infinite; z-index:8; }
  @keyframes spin { to { transform:rotate(360deg); } }
  .viderr { position:absolute; inset:0; display:flex; flex-direction:column; gap:10px;
            align-items:center; justify-content:center; color:#bbb; font-size:14px; z-index:8; }
  .viderr button { background:#fe2c55; border:none; color:#fff; padding:8px 18px;
                   border-radius:18px; font-weight:700; cursor:pointer; }

  .progress { position:absolute; left:0; right:0; bottom:62px; height:2.5px;
              background:#ffffff26; z-index:12; }
  .progress .bar { height:100%; width:0%; background:#fff; border-radius:2px; }

  .meta { position:absolute; left:14px; right:86px; bottom:84px; color:#fff; z-index:10;
          text-shadow:0 1px 3px rgba(0,0,0,.85); }
  .meta .user { font-weight:700; font-size:17px; margin-bottom:7px; }
  .meta .cap { font-size:14.5px; line-height:1.4; margin-bottom:9px; }
  .meta .cap .tag { font-weight:700; }
  .music { display:flex; align-items:center; gap:7px; font-size:13.5px; max-width:100%; }
  .music svg { width:14px; height:14px; fill:#fff; flex:none; }
  .marquee { overflow:hidden; white-space:nowrap; max-width:210px; }
  .marquee span { display:inline-block; padding-right:40px;
                  animation:scroll 8s linear infinite; }
  @keyframes scroll { from { transform:translateX(0); } to { transform:translateX(-50%); } }

  .rail { position:absolute; right:8px; bottom:84px; display:flex; flex-direction:column;
          align-items:center; gap:17px; z-index:10; }
  .avatar { position:relative; width:50px; height:50px; border-radius:50%;
            background:linear-gradient(135deg,#25f4ee,#fe2c55); padding:2px; cursor:pointer;
            margin-bottom:6px; }
  .avatar .inner { width:100%; height:100%; border-radius:50%; background:#26262e;
            display:flex; align-items:center; justify-content:center; font-size:24px;
            border:2px solid #000; }
  .avatar .plus { position:absolute; bottom:-9px; left:50%; transform:translateX(-50%);
                  width:20px; height:20px; border-radius:50%; background:#fe2c55; color:#fff;
                  font-size:14px; line-height:19px; text-align:center; font-weight:700;
                  transition:all .15s; border:1.5px solid #000; }
  .avatar .plus.followed { background:#fff; color:#fe2c55; }
  .act { display:flex; flex-direction:column; align-items:center; color:#fff;
         cursor:pointer; user-select:none; }
  .act svg { width:32px; height:32px; fill:#fff;
             filter:drop-shadow(0 1px 3px rgba(0,0,0,.7)); transition:transform .12s; }
  .act:active svg { transform:scale(1.3); }
  .act.liked svg { fill:#fe2c55; }
  .act.saved svg { fill:#face15; }
  .act .n { font-size:12px; font-weight:600; margin-top:3px; text-shadow:0 1px 2px #000; }
  .disc { width:42px; height:42px; border-radius:50%; margin-top:2px;
          background:conic-gradient(#111 0deg,#3a3a44 90deg,#111 180deg,#3a3a44 270deg,#111 360deg);
          border:5px solid #1d1d24; display:flex; align-items:center; justify-content:center;
          animation:rotate 4s linear infinite; font-size:14px; }
  @keyframes rotate { to { transform:rotate(360deg); } }

  .heartburst { position:absolute; z-index:20; pointer-events:none;
                animation:burst .75s ease-out forwards; }
  .heartburst svg { width:96px; height:96px; fill:#fe2c55;
                    filter:drop-shadow(0 2px 12px rgba(254,44,85,.6)); }
  @keyframes burst { 0%{transform:scale(.3) rotate(-14deg);opacity:0}
                     25%{transform:scale(1.18) rotate(4deg);opacity:1}
                     100%{transform:scale(1) translateY(-56px);opacity:0} }
  .paused-badge { position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);
                  z-index:15; pointer-events:none; opacity:.85; }
  .paused-badge svg { width:74px; height:74px; fill:#fff;
                      filter:drop-shadow(0 2px 12px #000); }

  .navbar { position:absolute; left:0; right:0; bottom:0; height:62px; background:#000;
            border-top:.5px solid #ffffff1c; display:flex; align-items:center;
            justify-content:space-around; z-index:45; }
  .nav { display:flex; flex-direction:column; align-items:center; gap:3px; color:#ffffff8c;
         font-size:10px; font-weight:600; cursor:pointer; width:56px; }
  .nav svg { width:23px; height:23px; fill:#ffffff8c; }
  .nav.on { color:#fff; } .nav.on svg { fill:#fff; }
  .navplus { width:46px; height:30px; border-radius:9px; background:#fff; position:relative;
             display:flex; align-items:center; justify-content:center; cursor:pointer; }
  .navplus::before { content:''; position:absolute; left:-4px; top:0; bottom:0; width:46px;
                     border-radius:9px; background:#25f4ee; z-index:-1; }
  .navplus::after { content:''; position:absolute; right:-4px; top:0; bottom:0; width:46px;
                    border-radius:9px; background:#fe2c55; z-index:-1; }
  .navplus svg { width:20px; height:20px; fill:#000; }

  .drawer { position:absolute; left:0; right:0; bottom:-64%; height:64%; background:#16161c;
            border-radius:18px 18px 0 0; z-index:50; transition:bottom .28s cubic-bezier(.2,.8,.3,1);
            color:#eee; display:flex; flex-direction:column; }
  .drawer.open { bottom:0; }
  .drawer .head { padding:14px; text-align:center; font-size:14px; font-weight:700;
                  border-bottom:.5px solid #26262e; position:relative; }
  .drawer .close { position:absolute; right:16px; top:12px; cursor:pointer;
                   color:#aaa; font-size:16px; }
  .drawer .list { flex:1; overflow-y:auto; padding:12px 16px; font-size:14px; }
  .cmt { display:flex; gap:10px; margin-bottom:14px; }
  .cmt .pfp { width:32px; height:32px; border-radius:50%; background:#2b2b34; flex:none;
              display:flex; align-items:center; justify-content:center; font-size:15px; }
  .cmt .who { font-weight:700; font-size:12.5px; color:#ffffffa8; margin-bottom:2px; }
  .drawer .compose { display:flex; gap:8px; padding:12px; border-top:.5px solid #26262e;
                     background:#111116; }
  .drawer input { flex:1; background:#26262e; border:none; border-radius:20px; color:#fff;
                  padding:10px 16px; font-size:14px; outline:none; }
  .drawer button { background:#fe2c55; color:#fff; border:none; border-radius:20px;
                   padding:0 18px; font-weight:700; cursor:pointer; }

  .toast { position:absolute; bottom:110px; left:50%; transform:translateX(-50%);
           background:#000d; color:#fff; padding:9px 18px; border-radius:20px;
           font-size:13px; z-index:55; opacity:0; transition:opacity .25s;
           pointer-events:none; white-space:nowrap; }
  .toast.show { opacity:1; }
</style>
</head>
<body>
<div class="phone">
  <div class="notch"></div>
  <div class="topbar">
    <span class="dim">Following</span><span class="active">For You</span>
  </div>
  <div class="sound" id="soundbtn" title="Toggle sound"></div>
  <div class="feed" id="feed"></div>

  <div class="navbar">
    <div class="nav on"><svg viewBox="0 0 24 24"><path d="M12 3l9 8h-3v9h-5v-6h-2v6H6v-9H3z"/></svg>Home</div>
    <div class="nav" onclick="toast('Discover — coming soon')"><svg viewBox="0 0 24 24"><path d="M10 2a8 8 0 105.3 14l4.4 4.4 1.4-1.4-4.4-4.4A8 8 0 0010 2zm0 2a6 6 0 110 12 6 6 0 010-12z"/></svg>Discover</div>
    <div class="navplus" onclick="document.getElementById('upl').click()">
      <svg viewBox="0 0 24 24"><path d="M11 5h2v6h6v2h-6v6h-2v-6H5v-2h6z"/></svg></div>
    <div class="nav" onclick="toast('Inbox — coming soon')"><svg viewBox="0 0 24 24"><path d="M4 4h16a1 1 0 011 1v14a1 1 0 01-1 1H4a1 1 0 01-1-1V5a1 1 0 011-1zm8 8L5 7v11h14V7l-7 5z"/></svg>Inbox</div>
    <div class="nav" onclick="toast('Profile — coming soon')"><svg viewBox="0 0 24 24"><path d="M12 12a4.5 4.5 0 100-9 4.5 4.5 0 000 9zm0 2c-4 0-8 2-8 5v2h16v-2c0-3-4-5-8-5z"/></svg>Me</div>
  </div>
  <input id="upl" type="file" accept="video/*" style="display:none">

  <div class="drawer" id="drawer">
    <div class="head"><span id="cmtcount">Comments</span>
      <span class="close" onclick="closeDrawer()">✕</span></div>
    <div class="list" id="cmtlist"></div>
    <div class="compose">
      <input id="cmtinput" placeholder="Add comment..."
             onkeydown="if(event.key==='Enter')postComment()">
      <button onclick="postComment()">Post</button>
    </div>
  </div>
  <div class="toast" id="toast"></div>
</div>

<script>
const VIDEOS = __VIDEOS__;
const FALLBACKS = __FALLBACKS__;   // embedded offline clips (data URIs)

const ICONS = {
  heart: '<svg viewBox="0 0 24 24"><path d="M12 21s-7.5-4.9-10-9.2C.3 8.9 1.6 5 5 4.2c2-.5 4 .3 5.2 1.9L12 8l1.8-1.9C15 4.5 17 3.7 19 4.2c3.4.8 4.7 4.7 3 7.6C19.5 16.1 12 21 12 21z"/></svg>',
  cmt: '<svg viewBox="0 0 24 24"><path d="M12 2C6.5 2 2 5.9 2 10.8c0 2.8 1.5 5.3 3.9 6.9-.2 1-.7 2.4-1.9 3.6 2.1-.1 3.8-.9 4.9-1.7 1 .3 2 .4 3.1.4 5.5 0 10-3.9 10-8.8S17.5 2 12 2z"/></svg>',
  save: '<svg viewBox="0 0 24 24"><path d="M6 2h12a1 1 0 011 1v19l-7-4.5L5 22V3a1 1 0 011-1z"/></svg>',
  share: '<svg viewBox="0 0 24 24"><path d="M13 4l9 7-9 7v-4.5C7 13.5 4 15.5 2 19c0-6 3.5-10.4 11-10.9V4z"/></svg>',
  note: '<svg viewBox="0 0 24 24"><path d="M9 3v10.6A3.5 3.5 0 1011 17V7h6v6.6A3.5 3.5 0 1019 17V3H9z"/></svg>',
  play: '<svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>',
  volOn: '<svg viewBox="0 0 24 24"><path d="M4 9v6h4l5 4V5L8 9H4zm12.5 3a3.5 3.5 0 00-2-3.2v6.3a3.5 3.5 0 002-3.1zM14.5 4v2.1a6 6 0 010 11.7V20a8 8 0 000-16z"/></svg>',
  volOff: '<svg viewBox="0 0 24 24"><path d="M4 9v6h4l5 4V5L8 9H4zm14.6 3l2.7-2.7-1.4-1.4-2.7 2.7-2.7-2.7-1.4 1.4 2.7 2.7-2.7 2.7 1.4 1.4 2.7-2.7 2.7 2.7 1.4-1.4-2.7-2.7z"/></svg>',
};

const feed = document.getElementById('feed');
const store = {
  get likes()    { return JSON.parse(localStorage.getItem('pp_likes')    || '{}'); },
  get saves()    { return JSON.parse(localStorage.getItem('pp_saves')    || '{}'); },
  get follows()  { return JSON.parse(localStorage.getItem('pp_follows')  || '{}'); },
  get comments() { return JSON.parse(localStorage.getItem('pp_comments') || '{}'); },
  set(key, val)  { localStorage.setItem('pp_' + key, JSON.stringify(val)); },
};
let drawerIdx = null;
let muted = true;

function fmt(n) {
  if (n >= 1e6) return (n/1e6).toFixed(1).replace(/\.0$/,'') + 'M';
  if (n >= 1e3) return (n/1e3).toFixed(1).replace(/\.0$/,'') + 'K';
  return n;
}
function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 1500);
}
function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;'); }

function captionHtml(cap) {
  return esc(cap).replace(/#\w+/g, m => `<span class="tag">${m}</span>`);
}

function buildSlide(v, i) {
  const el = document.createElement('div');
  el.className = 'slide'; el.dataset.idx = i;
  const liked = !!store.likes[i];
  const saved = !!store.saves[i];
  const followed = !!store.follows[v.user];
  const nCmts = (v.cmts || 0) + (store.comments[i] || []).length;
  el.innerHTML = `
    <video src="${v.src}" loop muted playsinline preload="metadata"></video>
    <div class="spinner"></div>
    <div class="progress"><div class="bar"></div></div>
    <div class="meta">
      <div class="user">${esc(v.user)}</div>
      <div class="cap">${captionHtml(v.caption)}</div>
      <div class="music">${ICONS.note}
        <div class="marquee"><span>${esc(v.song)} &nbsp;&nbsp;•&nbsp;&nbsp; ${esc(v.song)}</span></div>
      </div>
    </div>
    <div class="rail">
      <div class="avatar" onclick="toggleFollow(${i})"><div class="inner">${v.avatar}</div>
        <div class="plus ${followed ? 'followed' : ''}" id="plus${i}">${followed ? '✓' : '+'}</div></div>
      <div class="act ${liked ? 'liked' : ''}" id="like${i}" onclick="toggleLike(${i})">
        ${ICONS.heart}<div class="n" id="likeN${i}">${fmt(v.likes + (liked ? 1 : 0))}</div></div>
      <div class="act" onclick="openDrawer(${i})">${ICONS.cmt}
        <div class="n" id="cmtN${i}">${fmt(nCmts)}</div></div>
      <div class="act ${saved ? 'saved' : ''}" id="save${i}" onclick="toggleSave(${i})">
        ${ICONS.save}<div class="n" id="saveN${i}">${fmt((v.saves||0) + (saved ? 1 : 0))}</div></div>
      <div class="act" onclick="share(${i})">${ICONS.share}
        <div class="n">${fmt(v.shares || 0)}</div></div>
      <div class="disc">🎵</div>
    </div>`;

  const vid = el.querySelector('video');
  const spinner = el.querySelector('.spinner');
  const bar = el.querySelector('.progress .bar');

  vid.addEventListener('canplay', () => spinner.remove());
  vid.addEventListener('error', () => swapToFallback(el, vid, i));
  vid.addEventListener('timeupdate', () => {
    if (vid.duration) bar.style.width = (vid.currentTime / vid.duration * 100) + '%';
  });

  let lastTap = 0;
  vid.addEventListener('click', (e) => {
    const now = Date.now();
    if (now - lastTap < 300) { doubleTapLike(el, i, e); }
    else { setTimeout(() => { if (Date.now() - lastTap >= 300) togglePlay(el, vid); }, 310); }
    lastTap = now;
  });
  return el;
}

function swapToFallback(slide, vid, i) {
  if (!FALLBACKS.length || vid.dataset.fbk) {
    // fallback also failed (or none available) — show retry UI
    const sp = slide.querySelector('.spinner'); if (sp) sp.remove();
    if (slide.querySelector('.viderr')) return;
    const err = document.createElement('div');
    err.className = 'viderr';
    err.innerHTML = '<div>⚠️ Video failed to load</div><button>Retry</button>';
    err.querySelector('button').onclick = () => { err.remove();
      delete vid.dataset.fbk; vid.src = VIDEOS[i].src; vid.load(); vid.play(); };
    slide.appendChild(err);
    return;
  }
  vid.dataset.fbk = '1';
  vid.src = FALLBACKS[i % FALLBACKS.length];
  vid.load();
  vid.play().catch(() => {});
}

function watchdog(slide, vid, i) {
  // If the remote video hasn't produced data shortly after becoming
  // visible (blocked network, hung CDN), switch to an embedded clip.
  clearTimeout(vid._wd);
  if (vid.dataset.fbk) return;
  vid._wd = setTimeout(() => {
    if (vid.readyState < 2 && !vid.dataset.fbk) swapToFallback(slide, vid, i);
  }, 6000);
}

function togglePlay(slide, vid) {
  const badge = slide.querySelector('.paused-badge');
  if (vid.paused) { vid.play(); if (badge) badge.remove(); }
  else { vid.pause(); const b = document.createElement('div');
         b.className = 'paused-badge'; b.innerHTML = ICONS.play; slide.appendChild(b); }
}

function doubleTapLike(slide, i, e) {
  if (!store.likes[i]) toggleLike(i);
  const h = document.createElement('div');
  h.className = 'heartburst'; h.innerHTML = ICONS.heart;
  const r = slide.getBoundingClientRect();
  h.style.left = ((e ? e.clientX - r.left : 150) - 48) + 'px';
  h.style.top  = ((e ? e.clientY - r.top  : 300) - 48) + 'px';
  slide.appendChild(h); setTimeout(() => h.remove(), 750);
}

function toggleLike(i) {
  const likes = store.likes; likes[i] = !likes[i]; store.set('likes', likes);
  const btn = document.getElementById('like' + i);
  btn.classList.toggle('liked', likes[i]);
  document.getElementById('likeN' + i).textContent =
    fmt((VIDEOS[i].likes || 0) + (likes[i] ? 1 : 0));
}

function toggleSave(i) {
  const saves = store.saves; saves[i] = !saves[i]; store.set('saves', saves);
  const btn = document.getElementById('save' + i);
  btn.classList.toggle('saved', saves[i]);
  document.getElementById('saveN' + i).textContent =
    fmt((VIDEOS[i].saves || 0) + (saves[i] ? 1 : 0));
  toast(saves[i] ? 'Added to Favorites' : 'Removed from Favorites');
}

function toggleFollow(i) {
  const user = VIDEOS[i].user, follows = store.follows;
  follows[user] = !follows[user]; store.set('follows', follows);
  document.querySelectorAll('.slide').forEach(s => {
    const j = +s.dataset.idx;
    if (VIDEOS[j] && VIDEOS[j].user === user) {
      const p = document.getElementById('plus' + j);
      if (p) { p.textContent = follows[user] ? '✓' : '+';
               p.classList.toggle('followed', follows[user]); }
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
  const total = (VIDEOS[drawerIdx].cmts || 0) + cmts.length;
  document.getElementById('cmtcount').textContent = fmt(total) + ' comments';
  list.innerHTML = cmts.length
    ? cmts.map(c => `<div class="cmt"><div class="pfp">👤</div>
        <div><div class="who">${esc(c.who)}</div><div>${esc(c.text)}</div></div></div>`).join('')
    : '<div style="color:#888;text-align:center;margin-top:34px">Be the first to comment 💬</div>';
  list.scrollTop = list.scrollHeight;
}
function postComment() {
  const inp = document.getElementById('cmtinput');
  const text = inp.value.trim(); if (!text) return;
  const all = store.comments;
  (all[drawerIdx] = all[drawerIdx] || []).push({ who: '@you', text });
  store.set('comments', all); inp.value = '';
  renderComments();
  document.getElementById('cmtN' + drawerIdx).textContent =
    fmt((VIDEOS[drawerIdx].cmts || 0) + all[drawerIdx].length);
}

function share(i) {
  if (navigator.clipboard) navigator.clipboard.writeText(VIDEOS[i].src).catch(() => {});
  toast('Link copied to clipboard');
}

// ---- sound toggle (videos must start muted for autoplay) ----
const soundBtn = document.getElementById('soundbtn');
function renderSound() { soundBtn.innerHTML = muted ? ICONS.volOff : ICONS.volOn; }
soundBtn.onclick = () => {
  muted = !muted;
  document.querySelectorAll('video').forEach(v => { v.muted = muted; });
  renderSound(); toast(muted ? 'Muted' : 'Sound on');
};
renderSound();

// ---- upload ----
document.getElementById('upl').addEventListener('change', e => {
  const f = e.target.files[0]; if (!f) return;
  const idx = VIDEOS.length;
  VIDEOS.push({ src: URL.createObjectURL(f), user: '@you',
                caption: f.name + ' — uploaded by you 🎬 #mine',
                song: 'your original sound', likes: 0, cmts: 0, saves: 0,
                shares: 0, avatar: '🫵' });
  const slide = buildSlide(VIDEOS[idx], idx);
  feed.insertBefore(slide, feed.firstChild);
  observer.observe(slide);
  feed.scrollTo({ top: 0, behavior: 'smooth' });
  toast('Added to your feed 🎬');
});

// ---- autoplay only the visible slide ----
const observer = new IntersectionObserver(entries => {
  entries.forEach(en => {
    const vid = en.target.querySelector('video');
    if (!vid) return;
    if (en.isIntersecting && en.intersectionRatio > 0.6) {
      vid.muted = muted;
      vid.play().catch(() => {});
      watchdog(en.target, vid, +en.target.dataset.idx);
      const b = en.target.querySelector('.paused-badge'); if (b) b.remove();
    } else { vid.pause(); clearTimeout(vid._wd); }
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
"""


def feed_html():
    html = FEED_TEMPLATE.replace('__VIDEOS__', json.dumps(FEED_VIDEOS))
    return html.replace('__FALLBACKS__', json.dumps(_fallback_data_uris()))


# ---------------------------------------------------------------------------
# Global CSS for the Streamlit shell
# ---------------------------------------------------------------------------

APP_CSS = """
<style>
  .stApp { background: radial-gradient(1100px 600px at 20% -10%, #191926 0%, #0a0a0e 55%); }
  [data-testid="stSidebar"] {
    background: linear-gradient(180deg, #131318 0%, #0e0e13 100%);
    border-right: 1px solid #ffffff12;
  }
  [data-testid="stSidebar"] .stButton button {
    border-radius: 12px; border: 1px solid #ffffff14; background: #ffffff08;
    text-align: left; transition: all .15s;
  }
  [data-testid="stSidebar"] .stButton button:hover {
    border-color: #fe2c5580; background: #fe2c5514; color: #fff;
  }
  .pp-logo {
    font-size: 26px; font-weight: 800; letter-spacing: -.5px;
    background: linear-gradient(90deg, #25f4ee, #fe2c55);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    padding: 2px 0;
  }
  [data-testid="stChatMessage"] {
    background: #ffffff07; border: 1px solid #ffffff0d;
    border-radius: 16px; padding: 14px 16px; margin-bottom: 4px;
  }
  [data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background: #1d2a4a33; border-color: #4f7cff33;
  }
  [data-testid="stChatInput"] {
    border-radius: 18px; border: 1px solid #ffffff1a;
  }
  [data-testid="stChatInput"]:focus-within { border-color: #fe2c55aa; }
  div[data-testid="stExpander"] {
    border: 1px solid #ffffff12; border-radius: 12px; background: #ffffff05;
  }
  .stRadio [role="radiogroup"] label { font-size: 15px; }
</style>
"""


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def page_feed():
    feed_file = DATA_DIR / 'feed.html'
    feed_file.write_text(feed_html())
    left, mid, right = st.columns([1, 2.1, 1.1])
    with mid:
        if hasattr(st, 'iframe'):
            st.iframe(feed_file, height=790)
        else:
            components.html(feed_html(), height=790, scrolling=False)
    with right:
        st.markdown('#### 🎬 For You')
        st.markdown(
            '- **Scroll** to snap between videos — the visible one autoplays\n'
            '- **🔊 top-left** turns sound on (videos start muted so autoplay works)\n'
            '- **Tap** to pause · **double-tap** to like ❤️\n'
            '- **💬** comments · **🔖** favorites · **↗** share\n'
            '- **The white ＋** in the bottom bar uploads your own video\n'
            '- **+ on an avatar** follows the creator'
        )
        st.caption('All clips are real MP4 videos — openly licensed Blender '
                   'Foundation shorts and Google sample clips. Likes, '
                   'favorites and comments persist in your browser.')


def page_chat():
    store = load_chats()

    with st.sidebar:
        st.markdown('### Assistant')
        provider = st.radio(
            'Model', ['Claude', 'GPT'], horizontal=True,
            label_visibility='collapsed',
            captions=None,
        )
        if provider == 'Claude':
            effort_label = st.select_slider(
                'Power', options=list(EFFORT_LEVELS), value='⚖️ Balanced')
            effort = EFFORT_LEVELS[effort_label]
            web_search = st.toggle('🌐 Web search', value=True,
                                   help='Let Claude search the live web')
            show_thinking = st.toggle('💭 Show thinking', value=False,
                                      help="Stream Claude's reasoning summary")
        else:
            effort, web_search, show_thinking = 'high', False, False

        with st.expander('🔑 API keys', expanded=False):
            anthropic_key = st.text_input(
                'Anthropic API key', type='password',
                value=get_secret('ANTHROPIC_API_KEY'))
            openai_key = st.text_input(
                'OpenAI API key', type='password',
                value=get_secret('OPENAI_API_KEY'))
            st.caption('No key? A demo assistant replies instead.')

        st.divider()
        if st.button('✚ &nbsp;New chat', use_container_width=True):
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

    if 'chat_id' not in st.session_state or st.session_state.chat_id not in store['chats']:
        if store['order']:
            st.session_state.chat_id = store['order'][0]
        else:
            st.session_state.chat_id = new_chat(store)
    chat = store['chats'][st.session_state.chat_id]

    model_badge = (f'`{CLAUDE_MODEL}` · web search · {effort} effort'
                   if provider == 'Claude' else f'`{OPENAI_MODEL}`')
    st.markdown(f"### {chat['title']}")
    st.caption(f'Talking to **{provider}** — {model_badge}')

    for msg in chat['messages']:
        avatar = AVATAR_USER if msg['role'] == 'user' else AVATARS.get(msg.get('by'), AVATAR_DEMO)
        with st.chat_message(msg['role'], avatar=avatar):
            for img in msg.get('images', []):
                st.image(base64.b64decode(img['data']), width=260)
            st.markdown(msg['content'])

    submitted = st.chat_input(
        f'Message {provider}…  (you can attach images)',
        accept_file='multiple', file_type=['png', 'jpg', 'jpeg', 'gif', 'webp'],
    )
    if not submitted:
        return

    prompt = submitted.text if hasattr(submitted, 'text') else str(submitted)
    files = getattr(submitted, 'files', []) or []
    images = []
    for f in files[:4]:
        raw = f.read()
        if len(raw) <= 4_500_000:
            images.append({
                'mime': f.type or 'image/png',
                'data': base64.b64encode(raw).decode(),
            })
    if not prompt and not images:
        return

    user_msg = {'role': 'user', 'content': prompt}
    if images:
        user_msg['images'] = images
    chat['messages'].append(user_msg)
    if chat['title'] == 'New chat':
        chat['title'] = (prompt or 'Image chat')[:40]
    save_chats(store)

    with st.chat_message('user', avatar=AVATAR_USER):
        for img in images:
            st.image(base64.b64decode(img['data']), width=260)
        if prompt:
            st.markdown(prompt)

    key = anthropic_key if provider == 'Claude' else openai_key
    with st.chat_message('assistant', avatar=AVATARS[provider] if key else AVATAR_DEMO):
        thinking_slot = None
        if key and provider == 'Claude' and show_thinking:
            with st.expander('💭 Thinking…', expanded=False):
                thinking_slot = st.empty()
        try:
            if not key:
                reply = st.write_stream(stream_demo(chat['messages']))
                by = 'Demo'
            elif provider == 'Claude':
                reply = st.write_stream(stream_claude(
                    key, chat['messages'], effort, web_search,
                    show_thinking, thinking_slot))
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

st.markdown(APP_CSS, unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div class="pp-logo">⚡ PulsePlay</div>', unsafe_allow_html=True)
    page = st.radio('Go to', ['🎬 For You', '💬 AI Chat'], label_visibility='collapsed')
    st.divider()

if page == '🎬 For You':
    page_feed()
else:
    page_chat()
