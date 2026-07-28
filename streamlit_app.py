"""PhotoShare — a photo sharing gallery app.

Two areas:
  * Community Feed: browse photos people publish online. Like, dislike,
    comment on photos and follow/unfollow their authors.
  * My Gallery (private): upload and view all of your own photos. Like,
    mark, keep, remove and publish them — every action is persisted, so
    your gallery really changes.

All state is stored in ``data/photoshare.json`` and uploaded images in
``data/uploads/`` so everything survives reloads and restarts.
"""

import json
import math
import uuid
from datetime import datetime
from pathlib import Path

import streamlit as st
from PIL import Image, ImageDraw

st.set_page_config(
    page_title='PhotoShare',
    page_icon='📸',
    layout='wide',
)

DATA_DIR = Path(__file__).parent / 'data'
UPLOAD_DIR = DATA_DIR / 'uploads'
DEMO_DIR = DATA_DIR / 'demo'
STORE_FILE = DATA_DIR / 'photoshare.json'

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DEMO_DIR.mkdir(parents=True, exist_ok=True)

ME = 'you'


def _make_demo_image(path, top, bottom, accent):
    """Draw a small scenic placeholder (gradient sky, sun, hills) locally,
    so the demo feed never depends on an internet image service."""
    w, h = 720, 480
    img = Image.new('RGB', (w, h))
    draw = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        color = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (w, y)], fill=color)
    # sun / moon
    sun = tuple(min(255, c + 70) for c in accent)
    draw.ellipse([w * 0.68, h * 0.14, w * 0.68 + 90, h * 0.14 + 90], fill=sun)
    # rolling hills
    for layer, (amp, base) in enumerate([(40, 0.68), (55, 0.8), (70, 0.92)]):
        shade = tuple(max(0, round(c * (0.85 - 0.22 * layer))) for c in accent)
        points = [(x, h * base + amp * math.sin(x / 90 + layer * 2))
                  for x in range(0, w + 1, 8)]
        draw.polygon(points + [(w, h), (0, h)], fill=shade)
    img.save(path, 'JPEG', quality=88)


# -----------------------------------------------------------------------------
# Persistence

def _seed_store():
    """Initial data: a few demo people who already published photos online."""

    palettes = [
        ((255, 183, 94), (255, 94, 98), (120, 60, 90)),    # sunset
        ((160, 196, 255), (222, 235, 255), (70, 110, 140)),  # misty morning
        ((60, 70, 120), (20, 24, 50), (90, 80, 140)),      # night
        ((190, 230, 195), (245, 250, 220), (60, 130, 90)),  # spring
        ((250, 214, 165), (240, 150, 120), (150, 100, 70)),  # desert
        ((140, 200, 220), (230, 245, 250), (60, 120, 150)),  # lake
        ((255, 210, 130), (180, 120, 160), (110, 70, 110)),  # dusk
        ((205, 220, 240), (150, 170, 200), (80, 100, 130)),  # overcast
    ]
    seeded = iter(palettes)

    def feed_photo(author, caption, likes, dislikes, comments):
        photo_id = uuid.uuid4().hex
        filename = f'demo/{photo_id}.jpg'
        top, bottom, accent = next(seeded)
        _make_demo_image(DATA_DIR / filename, top, bottom, accent)
        return {
            'id': photo_id,
            'author': author,
            'file': filename,         # path relative to data/
            'caption': caption,
            'likes': likes,
            'dislikes': dislikes,
            'my_vote': None,          # None | 'like' | 'dislike'
            'comments': comments,     # [{author, text, time}]
            'posted_at': datetime.now().isoformat(timespec='seconds'),
        }

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
        else:
            st.session_state.store = _seed_store()
            save_store()
    return st.session_state.store


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
            'my_vote': None,
            'comments': [],
            'posted_at': datetime.now().isoformat(timespec='seconds'),
        })
        photo['published'] = True
    save_store()


# -----------------------------------------------------------------------------
# UI helpers

def show_photo(photo):
    """Render a feed or gallery photo image from the data directory."""
    path = DATA_DIR / photo['file']
    if path.exists():
        st.image(str(path), use_container_width=True)
    else:
        st.caption('_(image file missing)_')


def author_label(username):
    if username == ME:
        return 'You'
    user = store['users'].get(username)
    return f"{user['name']} (@{username})" if user else f'@{username}'


# -----------------------------------------------------------------------------
# Pages

def community_feed():
    st.title('📸 Community Feed')
    st.caption('Photos people published online. Like, dislike, comment and follow.')

    only_following = st.toggle(
        f'Only people I follow ({len(store["following"])})',
        value=False,
    )

    photos = store['feed_photos']
    if only_following:
        photos = [p for p in photos if p['author'] in store['following']]
        if not photos:
            st.info('You are not following anyone yet — or the people you follow '
                    'have not published photos. Turn the toggle off to browse everyone.')
            return

    for photo in photos:
        with st.container(border=True):
            img_col, side_col = st.columns([2, 1])

            with img_col:
                show_photo(photo)

            with side_col:
                st.subheader(photo['caption'])
                st.write(f"by **{author_label(photo['author'])}**")

                if photo['author'] != ME:
                    following = photo['author'] in store['following']
                    st.button(
                        '✓ Following' if following else '➕ Follow',
                        key=f"follow_{photo['id']}",
                        type='secondary' if following else 'primary',
                        on_click=toggle_follow, args=(photo['author'],),
                    )

                like_col, dislike_col = st.columns(2)
                liked = photo['my_vote'] == 'like'
                disliked = photo['my_vote'] == 'dislike'
                like_col.button(
                    f"{'❤️' if liked else '🤍'} {photo['likes']}",
                    key=f"like_{photo['id']}",
                    help='Like this photo',
                    on_click=vote_feed, args=(photo, 'like'),
                )
                dislike_col.button(
                    f"{'👎' if disliked else '💔'} {photo['dislikes']}",
                    key=f"dislike_{photo['id']}",
                    help='Dislike this photo',
                    on_click=vote_feed, args=(photo, 'dislike'),
                )

                with st.expander(f"💬 Comments ({len(photo['comments'])})"):
                    for c in photo['comments']:
                        st.markdown(f"**{author_label(c['author'])}**: {c['text']}")
                    comment_key = f"comment_{photo['id']}"
                    st.text_input('Add a comment', key=comment_key,
                                  placeholder='Say something nice…',
                                  label_visibility='collapsed')
                    st.button('Post', key=f"post_{photo['id']}",
                              on_click=add_comment, args=(photo, comment_key))


def my_gallery():
    st.title('🖼️ My Gallery')
    st.caption('Your private space. Only photos you publish appear in the feed.')

    # --- Upload -------------------------------------------------------------
    with st.expander('⬆️ Add photos to your gallery', expanded=not store['my_photos']):
        uploader_key = f"uploader_{st.session_state.get('uploader_round', 0)}"
        files = st.file_uploader(
            'Choose images', type=['png', 'jpg', 'jpeg', 'gif', 'webp'],
            accept_multiple_files=True, key=uploader_key,
        )
        caption = st.text_input('Title (optional, applies to this upload)')
        if st.button('Add to gallery', type='primary', disabled=not files):
            add_my_photos(files, caption)
            # Change the uploader key so the same files aren't re-added on rerun.
            st.session_state['uploader_round'] = st.session_state.get('uploader_round', 0) + 1
            st.rerun()

    if not store['my_photos']:
        st.info('Your gallery is empty — upload your first photos above.')
        return

    # --- Filters ------------------------------------------------------------
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

    # --- Grid ---------------------------------------------------------------
    cols = st.columns(3)
    for i, photo in enumerate(photos):
        with cols[i % 3].container(border=True):
            show_photo(photo)

            badges = []
            if photo['liked']:
                badges.append('❤️ Liked')
            if photo['marked']:
                badges.append('🔖 Marked')
            if photo['kept']:
                badges.append('📌 Kept')
            if photo['published']:
                badges.append('🌍 Published')
            st.markdown(f"**{photo['title']}**" + ('  \n' + ' · '.join(badges) if badges else ''))

            action_cols = st.columns(4)
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

            st.button(
                '🚫 Unpublish' if photo['published'] else '🌍 Publish online',
                key=f"mypublish_{photo['id']}",
                type='secondary' if photo['published'] else 'primary',
                on_click=toggle_publish, args=(photo,),
                use_container_width=True,
            )


def people():
    st.title('👥 People')
    st.caption('Photographers publishing on PhotoShare.')

    for username, user in store['users'].items():
        with st.container(border=True):
            info_col, btn_col = st.columns([3, 1])
            published = [p for p in store['feed_photos'] if p['author'] == username]
            total_likes = sum(p['likes'] for p in published)
            with info_col:
                st.subheader(f"{user['name']} · @{username}")
                st.write(user['bio'])
                st.caption(f'{len(published)} photos · {total_likes} likes')
            with btn_col:
                following = username in store['following']
                st.button(
                    '✓ Following' if following else '➕ Follow',
                    key=f'people_follow_{username}',
                    type='secondary' if following else 'primary',
                    on_click=toggle_follow, args=(username,),
                )


# -----------------------------------------------------------------------------
# Navigation

with st.sidebar:
    st.title('📸 PhotoShare')
    page = st.radio('Go to', ['Community Feed', 'My Gallery', 'People'])
    st.divider()
    st.caption(f"📷 {len(store['my_photos'])} photos in your gallery")
    st.caption(f"🌍 {sum(1 for p in store['my_photos'] if p['published'])} published by you")
    st.caption(f"➕ Following {len(store['following'])} people")

if page == 'Community Feed':
    community_feed()
elif page == 'My Gallery':
    my_gallery()
else:
    people()
