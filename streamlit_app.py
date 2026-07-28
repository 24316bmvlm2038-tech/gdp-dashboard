"""PhotoShare — a photo sharing gallery app with a TikTok/Instagram feel.

Areas:
  * For You: TikTok-style one-photo-at-a-time pager with an action rail.
  * Feed: Instagram-style scrolling feed with stories, likes and comments.
  * My Gallery (private): profile header + photo grid. Like, mark, keep,
    remove and publish your photos — every action is persisted, so your
    gallery really changes.

All state is stored in ``data/photoshare.json``; images live under
``data/`` so everything survives reloads and restarts.
"""

import base64
import colorsys
import hashlib
import json
import math
import random
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st
from PIL import Image, ImageDraw, ImageFont

st.set_page_config(
    page_title='PhotoShare',
    page_icon='📸',
    layout='centered',
    initial_sidebar_state='expanded',
)

DATA_DIR = Path(__file__).parent / 'data'
UPLOAD_DIR = DATA_DIR / 'uploads'
DEMO_DIR = DATA_DIR / 'demo'
AVATAR_DIR = DATA_DIR / 'avatars'
STORE_FILE = DATA_DIR / 'photoshare.json'

for d in (UPLOAD_DIR, DEMO_DIR, AVATAR_DIR):
    d.mkdir(parents=True, exist_ok=True)

ME = 'you'

IG_RING = ('conic-gradient(from 210deg,#f09433,#e6683c,#dc2743,'
           '#cc2366,#bc1888,#f09433)')


# -----------------------------------------------------------------------------
# Generated images (procedural photos + avatars)

def _hsv(h, s, v):
    return tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h % 1.0, s, v))


def _vgrad(draw, w, h, c1, c2):
    for y in range(h):
        t = y / (h - 1)
        draw.line([(0, y), (w, y)],
                  fill=tuple(round(c1[i] + (c2[i] - c1[i]) * t) for i in range(3)))


def _hills(draw, w, h, rng, base_color, layers=3, start=0.6):
    for layer in range(layers):
        base = start + (0.98 - start) * layer / max(1, layers - 1)
        amp = rng.uniform(30, 80)
        freq = rng.uniform(70, 140)
        phase = rng.uniform(0, 10)
        v = max(0.06, 0.5 - 0.16 * layer)
        shade = tuple(round(c * v) for c in base_color)
        pts = [(x, h * base + amp * math.sin(x / freq + phase))
               for x in range(0, w + 1, 6)]
        draw.polygon(pts + [(w, h), (0, h)], fill=shade)


def generate_photo(path, seed):
    """Paint a vivid procedural 'photo' (portrait, feed-ready) from a seed.

    Six scene types with randomized palettes give the feed endless variety
    without depending on any internet image service.
    """
    rng = random.Random(seed)
    w, h = 720, 900
    img = Image.new('RGB', (w, h))
    draw = ImageDraw.Draw(img, 'RGBA')
    hue = rng.random()
    scene = rng.choice(['ridge', 'ocean', 'night', 'city', 'dunes', 'bokeh'])

    if scene == 'ridge':
        _vgrad(draw, w, h, _hsv(hue, 0.5, 0.98), _hsv(hue + 0.09, 0.85, 0.75))
        r = rng.uniform(50, 90)
        cx, cy = rng.uniform(0.2, 0.8) * w, rng.uniform(0.12, 0.3) * h
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_hsv(hue + 0.04, 0.25, 1.0))
        _hills(draw, w, h, rng, _hsv(hue + 0.5, 0.6, 1.0), layers=4, start=0.55)

    elif scene == 'ocean':
        horizon = h * rng.uniform(0.45, 0.6)
        _vgrad(draw, w, int(horizon), _hsv(hue, 0.45, 1.0), _hsv(hue + 0.06, 0.7, 0.85))
        sea = Image.new('RGB', (w, h - int(horizon)))
        _vgrad(ImageDraw.Draw(sea), w, h - int(horizon),
               _hsv(hue + 0.55, 0.65, 0.55), _hsv(hue + 0.6, 0.7, 0.2))
        img.paste(sea, (0, int(horizon)))
        r = rng.uniform(45, 75)
        cx = rng.uniform(0.25, 0.75) * w
        draw.ellipse([cx - r, horizon - r * 2.2, cx + r, horizon - r * 0.2],
                     fill=_hsv(hue + 0.02, 0.2, 1.0))
        for i in range(26):  # shimmering reflection
            y = horizon + 8 + i * rng.uniform(8, 14)
            if y > h - 4:
                break
            half = rng.uniform(20, 90) * (1 + i / 8)
            draw.line([(cx - half, y), (cx + half, y)],
                      fill=(255, 255, 235, rng.randint(40, 110)), width=3)

    elif scene == 'night':
        _vgrad(draw, w, h, _hsv(0.62 + rng.uniform(-0.05, 0.05), 0.85, 0.25),
               _hsv(0.7, 0.9, 0.06))
        for _ in range(rng.randint(160, 260)):  # stars
            x, y = rng.uniform(0, w), rng.uniform(0, h * 0.85)
            s = rng.uniform(0.6, 2.2)
            draw.ellipse([x - s, y - s, x + s, y + s],
                         fill=(255, 255, 255, rng.randint(90, 220)))
        if rng.random() < 0.7:  # aurora bands
            ah = rng.choice([0.33, 0.45, 0.78])
            for band in range(3):
                pts = [(x, h * (0.25 + 0.1 * band)
                        + 60 * math.sin(x / rng.uniform(90, 150) + band))
                       for x in range(0, w + 1, 8)]
                draw.line(pts, fill=_hsv(ah + band * 0.05, 0.8, 0.9) + (60,), width=44)
        r = rng.uniform(35, 60)
        cx, cy = rng.uniform(0.15, 0.85) * w, rng.uniform(0.1, 0.3) * h
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(240, 240, 225, 235))
        _hills(draw, w, h, rng, _hsv(0.65, 0.5, 1.0), layers=2, start=0.82)

    elif scene == 'city':
        _vgrad(draw, w, h, _hsv(hue, 0.6, 0.95), _hsv(hue + 0.1, 0.85, 0.4))
        x = 0
        while x < w:
            bw = rng.randint(50, 110)
            bh = rng.randint(int(h * 0.25), int(h * 0.62))
            top = h - bh
            draw.rectangle([x, top, x + bw, h], fill=_hsv(hue + 0.5, 0.3, rng.uniform(0.04, 0.1)))
            for wy in range(top + 14, h - 10, 26):  # lit windows
                for wx in range(x + 8, x + bw - 10, 20):
                    if rng.random() < 0.45:
                        draw.rectangle([wx, wy, wx + 8, wy + 12],
                                       fill=_hsv(0.12, 0.5, 1.0) + (rng.randint(150, 255),))
            x += bw + rng.randint(6, 24)

    elif scene == 'dunes':
        warm = 0.06 + rng.uniform(-0.03, 0.05)
        _vgrad(draw, w, h, _hsv(warm, 0.45, 1.0), _hsv(warm + 0.05, 0.8, 0.85))
        r = rng.uniform(50, 80)
        cx, cy = rng.uniform(0.2, 0.8) * w, rng.uniform(0.1, 0.25) * h
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_hsv(warm, 0.15, 1.0))
        for layer in range(4):
            base = 0.5 + 0.13 * layer
            amp = rng.uniform(40, 90)
            freq = rng.uniform(120, 220)
            phase = rng.uniform(0, 10)
            col = _hsv(warm + 0.02 * layer, 0.75, 0.9 - 0.18 * layer)
            pts = [(x, h * base + amp * math.sin(x / freq + phase))
                   for x in range(0, w + 1, 6)]
            draw.polygon(pts + [(w, h), (0, h)], fill=col)

    else:  # bokeh
        _vgrad(draw, w, h, _hsv(hue, 0.7, 0.35), _hsv(hue + 0.15, 0.8, 0.12))
        for _ in range(rng.randint(22, 34)):
            r = rng.uniform(18, 110)
            x, y = rng.uniform(-40, w + 40), rng.uniform(-40, h + 40)
            draw.ellipse([x - r, y - r, x + r, y + r],
                         fill=_hsv(hue + rng.uniform(-0.12, 0.2), 0.75, 1.0)
                         + (rng.randint(30, 90),))

    img.save(path, 'JPEG', quality=88)


def avatar_path(username):
    """Profile picture: a gradient disc with the user's initial, generated
    once per user from a hash of their handle."""
    path = AVATAR_DIR / f'{username}.png'
    if not path.exists():
        digest = hashlib.md5(username.encode()).hexdigest()
        hue = int(digest[:4], 16) / 0xFFFF
        c1 = tuple(round(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.65, 0.95))
        c2 = tuple(round(c * 255) for c in colorsys.hsv_to_rgb((hue + 0.12) % 1, 0.75, 0.55))
        size = 128
        img = Image.new('RGB', (size, size))
        draw = ImageDraw.Draw(img)
        for y in range(size):
            t = y / (size - 1)
            color = tuple(round(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
            draw.line([(0, y), (size, y)], fill=color)
        initial = username[0].upper()
        try:
            font = ImageFont.load_default(size=60)
        except TypeError:
            font = ImageFont.load_default()
        box = draw.textbbox((0, 0), initial, font=font)
        draw.text(((size - box[2] - box[0]) / 2, (size - box[3] - box[1]) / 2),
                  initial, font=font, fill='white')
        mask = Image.new('L', (size, size), 0)
        ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
        out = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        out.paste(img, (0, 0), mask)
        out.save(path)
    return path


@st.cache_data
def _b64(path_str):
    return base64.b64encode(Path(path_str).read_bytes()).decode()


def avatar_img(username, px=38):
    return (f'<img src="data:image/png;base64,{_b64(str(avatar_path(username)))}" '
            f'style="width:{px}px;height:{px}px;border-radius:50%;'
            f'object-fit:cover;vertical-align:middle;"/>')


# -----------------------------------------------------------------------------
# Unlimited content

CAPTIONS = [
    'Golden hour hits different', 'No edit, no filter', 'Lost in the moment',
    "Can't stop looking at this", 'From last night 🌙', 'POV: you were there',
    'This view >>> everything', 'Chasing light again', 'Little slice of heaven',
    'Still thinking about this place', 'Main character energy', 'Just wow',
    'Took the long way home', 'The sky said show off', 'Unreal, honestly',
    'Blink and you miss it', 'Saved this one for you', 'Weekend reset',
    'Colors were not real', 'Had to stop the car for this',
]

HANDLE_A = ['wander', 'pixel', 'urban', 'golden', 'misty', 'wild', 'neon',
            'drift', 'lunar', 'salty', 'vivid', 'nomad', 'echo', 'cosmic']
HANDLE_B = ['lens', 'frames', 'shots', 'visuals', 'roam', 'light', 'tales',
            'chaser', 'diary', 'mood', 'gaze', 'wave', 'films', 'story']

COMMENT_POOL = [
    'Insane 😍', 'How is this real', 'Teach me your ways', 'Wallpaper. Now.',
    'This one goes hard', 'Take me there', 'Obsessed with this',
    'The colors!!', 'Stop it, this is too good', 'Instant classic',
]


def _random_handle(rng, taken):
    for _ in range(50):
        handle = rng.choice(HANDLE_A) + rng.choice(['.', '_', '']) + rng.choice(HANDLE_B)
        if handle not in taken and handle != ME:
            return handle
    return f'creator_{rng.randint(100, 999)}'


def make_feed_photo(author, caption=None, likes=None, dislikes=None,
                    comments=None, views=None, rng=None):
    rng = rng or random
    photo_id = uuid.uuid4().hex
    filename = f'demo/{photo_id}.jpg'
    generate_photo(DATA_DIR / filename, photo_id)
    likes = rng.randint(40, 9000) if likes is None else likes
    return {
        'id': photo_id,
        'author': author,
        'file': filename,         # path relative to data/
        'caption': caption or rng.choice(CAPTIONS),
        'likes': likes,
        'dislikes': rng.randint(0, 20) if dislikes is None else dislikes,
        'views': likes * rng.randint(12, 40) if views is None else views,
        'my_vote': None,          # None | 'like' | 'dislike'
        'comments': comments if comments is not None else [
            {'author': a, 'text': rng.choice(COMMENT_POOL),
             'time': datetime.now().isoformat(timespec='seconds')}
            for a in rng.sample(list(store['users']) or ['ava_shoots'],
                                k=min(rng.randint(0, 2), len(store['users'])))
        ] if 'store' in st.session_state else [],
        'posted_at': datetime.now().isoformat(timespec='seconds'),
    }


def extend_feed(count=4):
    """Generate fresh photos (and sometimes fresh creators) so the For You
    feed never runs out."""
    rng = random.Random()
    for _ in range(count):
        if rng.random() < 0.3 or not store['users']:
            handle = _random_handle(rng, store['users'])
            store['users'][handle] = {
                'name': handle.replace('.', ' ').replace('_', ' ').title(),
                'bio': rng.choice(['Shoots on anything', 'Light collector',
                                   'Somewhere new every week', 'Mostly moments',
                                   'Catch me outside', 'Frames over followers']),
            }
        author = rng.choice([u for u in store['users']])
        store['feed_photos'].append(make_feed_photo(author, rng=rng))
    save_store()


# -----------------------------------------------------------------------------
# Persistence

def _seed_store():
    """Initial data: a few demo people who already published photos online."""

    rng = random.Random(44)

    def feed_photo(author, caption, likes, dislikes, comments):
        photo = make_feed_photo(author, caption, likes, dislikes, comments, rng=rng)
        photo['views'] = rng.randint(1500, 42000)
        return photo

    def comment(author, text):
        return {'author': author, 'text': text,
                'time': datetime.now().isoformat(timespec='seconds')}

    return {
        'users': {
            'ava_shoots': {'name': 'Ava Torres', 'bio': 'Landscapes & light chasing'},
            'liam.frames': {'name': 'Liam Chen', 'bio': 'Street photography, mostly rain'},
            'maya_lens': {'name': 'Maya Okafor', 'bio': 'Food, travel and tiny details'},
            'noah_wild': {'name': 'Noah Berg', 'bio': 'Wildlife and the great outdoors'},
        },
        'following': [],
        'my_photos': [],   # photos in your private gallery
        'feed_photos': [
            feed_photo('ava_shoots', 'River bend at golden hour', 42, 1,
                       [comment('liam.frames', 'That light is unreal!')]),
            feed_photo('ava_shoots', 'Fog rolling over the ridge', 31, 0, []),
            feed_photo('liam.frames', 'Quiet night in the city', 27, 2,
                       [comment('maya_lens', 'So peaceful 😍'),
                        comment('noah_wild', 'Where is this?')]),
            feed_photo('liam.frames', 'First green of spring', 18, 3, []),
            feed_photo('maya_lens', 'Dunes going on forever', 55, 2,
                       [comment('ava_shoots', 'The composition here!')]),
            feed_photo('maya_lens', 'Morning at the lake', 23, 0, []),
            feed_photo('noah_wild', 'Dusk over the valley', 68, 1,
                       [comment('ava_shoots', 'Incredible shot'),
                        comment('liam.frames', 'Worth the wait I bet')]),
            feed_photo('noah_wild', 'Storm rolling in', 39, 0, []),
        ],
    }


def load_store():
    if 'store' not in st.session_state:
        if STORE_FILE.exists():
            st.session_state.store = json.loads(STORE_FILE.read_text())
            _migrate(st.session_state.store)
        else:
            st.session_state.store = _seed_store()
            save_store()
    return st.session_state.store


def _migrate(data):
    """Backfill fields added after a store was first created."""
    rng = random.Random(44)
    changed = False
    for photo in data['feed_photos']:
        if 'views' not in photo:
            photo['views'] = 0 if photo['author'] == ME else rng.randint(1500, 42000)
            changed = True
    if changed:
        st.session_state.store = data
        save_store()


def save_store():
    STORE_FILE.write_text(json.dumps(st.session_state.store, indent=2))


store = load_store()


# -----------------------------------------------------------------------------
# Actions (each mutates the store and saves it, so changes are permanent)

def toggle_follow(username):
    if username in store['following']:
        store['following'].remove(username)
    else:
        store['following'].append(username)
    save_store()


def vote_feed(photo, vote):
    """Like/dislike a feed photo. Voting again withdraws it, switching swaps it."""
    prev = photo['my_vote']
    if prev == 'like':
        photo['likes'] -= 1
    elif prev == 'dislike':
        photo['dislikes'] -= 1
    if prev == vote:
        photo['my_vote'] = None
    else:
        photo['my_vote'] = vote
        photo['likes' if vote == 'like' else 'dislikes'] += 1
    save_store()


def add_comment(photo, key):
    text = st.session_state.get(key, '').strip()
    if text:
        photo['comments'].append({
            'author': ME,
            'text': text,
            'time': datetime.now().isoformat(timespec='seconds'),
        })
        st.session_state[key] = ''
        save_store()


def add_my_photos(files, caption):
    for f in files:
        ext = Path(f.name).suffix.lower() or '.jpg'
        photo_id = uuid.uuid4().hex
        (UPLOAD_DIR / f'{photo_id}{ext}').write_bytes(f.getbuffer())
        store['my_photos'].append({
            'id': photo_id,
            'file': f'uploads/{photo_id}{ext}',
            'title': caption.strip() or Path(f.name).stem,
            'liked': False,
            'marked': False,
            'kept': False,
            'published': False,
            'uploaded_at': datetime.now().isoformat(timespec='seconds'),
        })
    save_store()


def toggle_my(photo, flag):
    photo[flag] = not photo[flag]
    save_store()


def remove_my(photo):
    path = DATA_DIR / photo['file']
    if path.exists():
        path.unlink()
    store['my_photos'] = [p for p in store['my_photos'] if p['id'] != photo['id']]
    # Also take it off the public feed if it was published there.
    store['feed_photos'] = [p for p in store['feed_photos']
                            if p.get('gallery_id') != photo['id']]
    save_store()


def toggle_publish(photo):
    if photo['published']:
        store['feed_photos'] = [p for p in store['feed_photos']
                                if p.get('gallery_id') != photo['id']]
        photo['published'] = False
    else:
        store['feed_photos'].insert(0, {
            'id': uuid.uuid4().hex,
            'gallery_id': photo['id'],
            'author': ME,
            'file': photo['file'],
            'caption': photo['title'],
            'likes': 0,
            'dislikes': 0,
            'views': 0,
            'my_vote': None,
            'comments': [],
            'posted_at': datetime.now().isoformat(timespec='seconds'),
        })
        photo['published'] = True
    save_store()


def fy_step(step):
    idx = max(0, st.session_state.get('fy_idx', 0) + step)
    # Generate more content before the viewer reaches the end — the feed
    # is effectively unlimited.
    if idx >= len(store['feed_photos']) - 2:
        extend_feed()
    st.session_state.fy_idx = min(idx, len(store['feed_photos']) - 1)


# -----------------------------------------------------------------------------
# UI helpers

CSS = """
<style>
#MainMenu, footer {visibility: hidden;}
header[data-testid="stHeader"] {background: transparent;}
.block-container {padding-top: 1.2rem; max-width: 680px;}

[data-testid="stImage"] img {border-radius: 14px;}

.stories {display:flex; gap:14px; overflow-x:auto; padding:6px 2px 12px;}
.story {text-align:center; flex:0 0 auto; width:76px;}
.story-ring {width:66px;height:66px;margin:0 auto;border-radius:50%;
  padding:2.5px; background:__RING__;}
.story-ring.seen {background:#3a3a3d;}
.story-ring img {width:100%;height:100%;border-radius:50%;
  border:2.5px solid #0e0e10;object-fit:cover;display:block;}
.story-name {font-size:11px;color:#d0d0d0;margin-top:5px;overflow:hidden;
  text-overflow:ellipsis;white-space:nowrap;}

.handle {font-weight:700; font-size:0.95rem;}
.muted {color:#8e8e93; font-size:0.78rem;}
.likes-line {font-weight:700; margin:0.1rem 0 0.15rem;}
.caption-line {margin:0 0 0.3rem;}
.rail-num {text-align:center; font-size:0.8rem; font-weight:700;
  color:#fafafa; margin:-6px 0 8px;}

div.stButton > button {border-radius: 14px;}
</style>
""".replace('__RING__', IG_RING)


def fmt_count(n):
    if n >= 1_000_000:
        return f'{n / 1_000_000:.1f}M'
    if n >= 1_000:
        return f'{n / 1_000:.1f}K'
    return str(n)


def rel_time(iso):
    try:
        delta = datetime.now() - datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return ''
    s = int(delta.total_seconds())
    if s < 60:
        return 'just now'
    if s < 3600:
        return f'{s // 60}m'
    if s < 86400:
        return f'{s // 3600}h'
    return f'{s // 86400}d'


def show_photo(photo):
    """Render a feed or gallery photo image from the data directory."""
    path = DATA_DIR / photo['file']
    if path.exists():
        st.image(str(path), use_container_width=True)
    else:
        st.caption('_(image file missing)_')


def handle_of(photo_or_user):
    username = photo_or_user if isinstance(photo_or_user, str) else photo_or_user['author']
    return 'you' if username == ME else username


def stories_bar():
    items = []
    for username in [ME] + list(store['users']):
        seen = '' if (username == ME or username not in store['following']) else ' seen'
        label = 'Your story' if username == ME else username
        items.append(
            f'<div class="story"><div class="story-ring{seen}">'
            f'{avatar_img(username, 66)}</div>'
            f'<div class="story-name">{label}</div></div>'
        )
    st.markdown(f'<div class="stories">{"".join(items)}</div>',
                unsafe_allow_html=True)


def follow_button(photo, key_prefix):
    following = photo['author'] in store['following']
    st.button(
        'Following' if following else 'Follow',
        key=f"{key_prefix}_{photo['id']}",
        type='secondary' if following else 'primary',
        on_click=toggle_follow, args=(photo['author'],),
    )


def comments_block(photo, key_prefix):
    n = len(photo['comments'])
    label = f'View all {n} comments' if n else 'Add a comment…'
    with st.expander(label):
        for c in photo['comments']:
            st.markdown(f"**{handle_of(c['author'])}**  {c['text']}  "
                        f"<span class='muted'>{rel_time(c['time'])}</span>",
                        unsafe_allow_html=True)
        comment_key = f"{key_prefix}_comment_{photo['id']}"
        st.text_input('Add a comment', key=comment_key,
                      placeholder='Add a comment…',
                      label_visibility='collapsed')
        st.button('Post', key=f"{key_prefix}_post_{photo['id']}",
                  on_click=add_comment, args=(photo, comment_key))


@st.dialog('Preview', width='large')
def photo_preview(photo, mine=False):
    """Lightbox-style modal preview of a photo."""
    show_photo(photo)
    if mine:
        st.markdown(f"<span class='handle' style='font-size:1.1rem'>"
                    f"{photo['title']}</span>", unsafe_allow_html=True)
        status = []
        if photo['liked']:
            status.append('❤️ Liked')
        if photo['marked']:
            status.append('🔖 Marked')
        if photo['kept']:
            status.append('📌 Kept')
        status.append('🌍 Published' if photo['published'] else '🔒 Private')
        st.caption(' · '.join(status)
                   + f" · added {rel_time(photo['uploaded_at'])} ago")
    else:
        st.markdown(f"{avatar_img(photo['author'], 34)}  <span class='handle'>"
                    f"{handle_of(photo)}</span>  {photo['caption']}",
                    unsafe_allow_html=True)
        st.caption(f"{fmt_count(photo['likes'])} likes · "
                   f"{fmt_count(photo.get('views', 0))} views · "
                   f"{rel_time(photo['posted_at'])}")
        comments_block(photo, 'dlg')


def suggestions_row(context_key):
    """Instagram-style 'Suggested for you' follow cards."""
    candidates = [u for u in store['users'] if u not in store['following']]
    if not candidates:
        return
    st.markdown("<span class='handle'>Suggested for you</span>",
                unsafe_allow_html=True)
    cols = st.columns(min(4, len(candidates)))
    for i, username in enumerate(candidates[:4]):
        with cols[i]:
            st.markdown(
                f"<div style='text-align:center'>"
                f"<div class='story-ring' style='width:56px;height:56px;"
                f"margin:0 auto'>{avatar_img(username, 56)}</div>"
                f"<div class='story-name'>{username}</div></div>",
                unsafe_allow_html=True)
            st.button('Follow', key=f'sugg_{context_key}_{username}',
                      type='primary', use_container_width=True,
                      on_click=toggle_follow, args=(username,))


# -----------------------------------------------------------------------------
# Pages

def ig_post(photo):
    """One Instagram-style post card."""
    with st.container(border=True):
        av_col, name_col, btn_col = st.columns([1, 5, 2])
        av_col.markdown(avatar_img(photo['author'], 40), unsafe_allow_html=True)
        name_col.markdown(
            f"<span class='handle'>{handle_of(photo)}</span><br>"
            f"<span class='muted'>{rel_time(photo['posted_at'])} · "
            f"{fmt_count(photo.get('views', 0))} views</span>",
            unsafe_allow_html=True)
        with btn_col:
            if photo['author'] != ME:
                follow_button(photo, 'feed_follow')

        show_photo(photo)

        liked = photo['my_vote'] == 'like'
        disliked = photo['my_vote'] == 'dislike'
        b1, b2, b3, _sp = st.columns([1, 1, 1, 3])
        b1.button('❤️' if liked else '🤍',
                  key=f"feed_like_{photo['id']}", help='Like',
                  on_click=vote_feed, args=(photo, 'like'))
        b2.button('👎' if disliked else '💔',
                  key=f"feed_dislike_{photo['id']}", help='Dislike',
                  on_click=vote_feed, args=(photo, 'dislike'))
        if b3.button('🔍', key=f"feed_preview_{photo['id']}", help='Preview'):
            photo_preview(photo)

        st.markdown(f"<div class='likes-line'>{fmt_count(photo['likes'])} likes"
                    + (f" · {photo['dislikes']} dislikes" if photo['dislikes'] else '')
                    + '</div>',
                    unsafe_allow_html=True)
        st.markdown(f"<div class='caption-line'><span class='handle'>"
                    f"{handle_of(photo)}</span>  {photo['caption']}</div>",
                    unsafe_allow_html=True)
        comments_block(photo, 'feed')


def page_feed():
    stories_bar()

    mode = st.radio('Feed mode', ['✨ For You', '🏠 Following'],
                    horizontal=True, key='feed_mode',
                    label_visibility='collapsed')

    if mode == '✨ For You':
        photos = store['feed_photos']
        if not photos:
            st.info('Nothing here yet — publish a photo from your gallery!')
            return
        idx = st.session_state.get('fy_idx', 0) % len(photos)
        photo = photos[idx]

        img_col, rail = st.columns([5, 1])
        with img_col:
            show_photo(photo)
            st.markdown(f"<div class='caption-line'><span class='handle'>"
                        f"{handle_of(photo)}</span>  {photo['caption']}<br>"
                        f"<span class='muted'>{fmt_count(photo.get('views', 0))} views · "
                        f"{rel_time(photo['posted_at'])}</span></div>",
                        unsafe_allow_html=True)
        with rail:
            st.markdown(f"<div style='text-align:center'>{avatar_img(photo['author'], 44)}</div>",
                        unsafe_allow_html=True)
            if photo['author'] != ME:
                following = photo['author'] in store['following']
                st.button('✓' if following else '➕',
                          key=f"fy_follow_{photo['id']}",
                          help='Unfollow' if following else 'Follow',
                          on_click=toggle_follow, args=(photo['author'],))
            liked = photo['my_vote'] == 'like'
            disliked = photo['my_vote'] == 'dislike'
            st.button('❤️' if liked else '🤍', key=f"fy_like_{photo['id']}",
                      help='Like', on_click=vote_feed, args=(photo, 'like'))
            st.markdown(f"<div class='rail-num'>{fmt_count(photo['likes'])}</div>",
                        unsafe_allow_html=True)
            st.button('👎' if disliked else '💔', key=f"fy_dislike_{photo['id']}",
                      help='Dislike', on_click=vote_feed, args=(photo, 'dislike'))
            st.markdown(f"<div class='rail-num'>{fmt_count(photo['dislikes'])}</div>",
                        unsafe_allow_html=True)
            st.markdown(f"<div class='rail-num'>💬<br>{len(photo['comments'])}</div>",
                        unsafe_allow_html=True)

        comments_block(photo, 'fy')

        p, pos, n = st.columns([2, 3, 2])
        p.button('⬆️ Previous', key='fy_prev',
                 on_click=fy_step, args=(-1,),
                 use_container_width=True)
        pos.markdown(f"<div style='text-align:center' class='muted'>"
                     f"{idx + 1} / ∞</div>", unsafe_allow_html=True)
        n.button('⬇️ Next', key='fy_next',
                 on_click=fy_step, args=(1,),
                 use_container_width=True, type='primary')

    else:  # Following feed
        photos = [p for p in store['feed_photos']
                  if p['author'] in store['following'] or p['author'] == ME]
        if not photos:
            st.info('Follow some people and their photos will show up here.')
            with st.container(border=True):
                suggestions_row('empty')
            return
        for i, photo in enumerate(photos):
            ig_post(photo)
            # Weave a suggestions card into the feed, Instagram-style.
            if i == 0:
                with st.container(border=True):
                    suggestions_row('feed')


def page_gallery():
    # Instagram-style profile header
    av, stats = st.columns([1, 3])
    av.markdown(f"<div class='story-ring' style='width:86px;height:86px'>"
                f"{avatar_img(ME, 86)}</div>", unsafe_allow_html=True)
    with stats:
        st.markdown("<span class='handle' style='font-size:1.25rem'>@you</span>",
                    unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        c1.metric('Photos', len(store['my_photos']))
        c2.metric('Published', sum(1 for p in store['my_photos'] if p['published']))
        c3.metric('Following', len(store['following']))
    st.caption('Your private gallery. Only photos you publish appear in the feed.')

    with st.expander('➕ New post — add photos to your gallery',
                     expanded=not store['my_photos']):
        uploader_key = f"uploader_{st.session_state.get('uploader_round', 0)}"
        files = st.file_uploader(
            'Choose images', type=['png', 'jpg', 'jpeg', 'gif', 'webp'],
            accept_multiple_files=True, key=uploader_key,
        )
        caption = st.text_input('Caption (optional, applies to this upload)')
        if files:
            st.caption('Preview')
            pcols = st.columns(min(4, len(files)))
            for i, f in enumerate(files):
                pcols[i % len(pcols)].image(f, use_container_width=True)
        if st.button('Add to gallery', type='primary', disabled=not files):
            add_my_photos(files, caption)
            # Change the uploader key so the same files aren't re-added on rerun.
            st.session_state['uploader_round'] = st.session_state.get('uploader_round', 0) + 1
            st.rerun()

    if not store['my_photos']:
        st.info('Your gallery is empty — add your first photos above.')
        return

    view = st.radio(
        'Show', ['All', '❤️ Liked', '🔖 Marked', '📌 Kept', '🌍 Published'],
        horizontal=True, label_visibility='collapsed',
    )
    photos = store['my_photos']
    if view == '❤️ Liked':
        photos = [p for p in photos if p['liked']]
    elif view == '🔖 Marked':
        photos = [p for p in photos if p['marked']]
    elif view == '📌 Kept':
        photos = [p for p in photos if p['kept']]
    elif view == '🌍 Published':
        photos = [p for p in photos if p['published']]

    st.caption(f'{len(photos)} photo(s)')
    if not photos:
        st.info('No photos match this filter.')
        return

    # Square, Instagram-grid-style thumbnails.
    st.markdown("<style>[data-testid='stImage'] img "
                "{aspect-ratio:1/1; object-fit:cover;}</style>",
                unsafe_allow_html=True)

    cols = st.columns(3)
    for i, photo in enumerate(photos):
        with cols[i % 3].container(border=True):
            show_photo(photo)

            badges = []
            if photo['liked']:
                badges.append('❤️')
            if photo['marked']:
                badges.append('🔖')
            if photo['kept']:
                badges.append('📌')
            if photo['published']:
                badges.append('🌍')
            st.markdown(f"**{photo['title']}**"
                        + ('  \n' + ' '.join(badges) if badges else ''))

            action_cols = st.columns(5)
            action_cols[0].button(
                '❤️' if photo['liked'] else '🤍',
                key=f"mylike_{photo['id']}", help='Like',
                on_click=toggle_my, args=(photo, 'liked'),
            )
            action_cols[1].button(
                '🔖' if photo['marked'] else '🏷️',
                key=f"mymark_{photo['id']}", help='Mark',
                on_click=toggle_my, args=(photo, 'marked'),
            )
            action_cols[2].button(
                '📌' if photo['kept'] else '📍',
                key=f"mykeep_{photo['id']}",
                help='Keep — protects the photo from removal',
                on_click=toggle_my, args=(photo, 'kept'),
            )
            action_cols[3].button(
                '🗑️', key=f"myremove_{photo['id']}",
                help='Photo is kept — un-keep it first to remove'
                     if photo['kept'] else 'Remove from gallery',
                disabled=photo['kept'],
                on_click=remove_my, args=(photo,),
            )
            if action_cols[4].button('🔍', key=f"mypreview_{photo['id']}",
                                     help='Preview full size'):
                photo_preview(photo, mine=True)

            st.button(
                'Unpublish' if photo['published'] else 'Publish',
                key=f"mypublish_{photo['id']}",
                type='secondary' if photo['published'] else 'primary',
                on_click=toggle_publish, args=(photo,),
                use_container_width=True,
            )


def page_people():
    st.markdown('### Suggested for you')
    for username, user in store['users'].items():
        with st.container(border=True):
            av, info, btn = st.columns([1, 4, 2])
            av.markdown(f"<div class='story-ring' style='width:56px;height:56px'>"
                        f"{avatar_img(username, 56)}</div>",
                        unsafe_allow_html=True)
            published = [p for p in store['feed_photos'] if p['author'] == username]
            total_likes = sum(p['likes'] for p in published)
            with info:
                st.markdown(f"<span class='handle'>{username}</span><br>"
                            f"<span class='muted'>{user['name']} · {user['bio']}</span><br>"
                            f"<span class='muted'>{len(published)} posts · "
                            f"{fmt_count(total_likes)} likes</span>",
                            unsafe_allow_html=True)
            with btn:
                following = username in store['following']
                st.button(
                    'Following' if following else 'Follow',
                    key=f'people_follow_{username}',
                    type='secondary' if following else 'primary',
                    on_click=toggle_follow, args=(username,),
                )


# -----------------------------------------------------------------------------
# Navigation

st.markdown(CSS, unsafe_allow_html=True)

with st.sidebar:
    st.markdown("<h2 style='margin-bottom:0'>📸 PhotoShare</h2>",
                unsafe_allow_html=True)
    st.caption('Share the moment.')
    page = st.radio('Go to', ['🎬 Feed', '👤 My Gallery', '🧭 Discover people'],
                    key='nav', label_visibility='collapsed')
    st.divider()
    st.markdown(f"{avatar_img(ME, 34)}  <span class='handle'>@you</span>",
                unsafe_allow_html=True)
    st.caption(f"📷 {len(store['my_photos'])} photos · "
               f"🌍 {sum(1 for p in store['my_photos'] if p['published'])} published · "
               f"➕ following {len(store['following'])}")

if page == '🎬 Feed':
    page_feed()
elif page == '👤 My Gallery':
    page_gallery()
else:
    page_people()
