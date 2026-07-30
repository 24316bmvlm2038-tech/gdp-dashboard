"""Collections: folders, shared folders and private notes on saved cards."""

from __future__ import annotations

import streamlit as st

from ..models import now_iso
from ..store import (card as get_card, collections, db, interaction, save,
                     users)
from ..theme import haptic
from .components import card_preview, empty_state, esc, go, render_card, section

SUGGESTED = [('Space', '🪐'), ('Business', '📈'), ('AI', '🤖'), ('Psychology', '🧠'),
             ('History', '🏛️'), ('Favorites', '⭐'), ('Study Later', '📚')]


def _create_row(user: dict) -> None:
    cols = st.columns([0.42, 0.16, 0.22, 0.20])
    name = cols[0].text_input('New collection', key='col_new_name',
                              placeholder='Name a new folder…', label_visibility='collapsed')
    emoji = cols[1].text_input('Emoji', key='col_new_emoji', value='📁', max_chars=2,
                               label_visibility='collapsed')
    if cols[2].button('Create', key='col_create', use_container_width=True, type='primary'):
        clean = name.strip()[:32]
        if not clean:
            st.warning('Give the folder a name first.')
        elif clean in collections(user['id']):
            st.warning('You already have a folder with that name.')
        else:
            collections(user['id'])[clean] = {'emoji': emoji or '📁', 'items': [],
                                              'shared_with': [], 'notes': {},
                                              'created_at': now_iso()}
            save()
            haptic('light')
            st.rerun()
    if cols[3].button('Add suggested', key='col_suggest', use_container_width=True):
        for label, icon in SUGGESTED:
            collections(user['id']).setdefault(label, {'emoji': icon, 'items': [],
                                                       'shared_with': [], 'notes': {},
                                                       'created_at': now_iso()})
        save()
        st.rerun()


def _folder_card(user: dict, name: str, folder: dict) -> None:
    active = st.session_state.get('open_collection') == name
    shared = len(folder.get('shared_with', []))
    if st.button(f'{folder.get("emoji", "📁")}  {name}\n{len(folder.get("items", []))} saved'
                 + (f' · shared with {shared}' if shared else ''),
                 key=f'colbtn_{name}', use_container_width=True,
                 type='primary' if active else 'secondary'):
        st.session_state['open_collection'] = None if active else name
        haptic('light')
        st.rerun()


def _share_controls(user: dict, name: str, folder: dict) -> None:
    others = [u for u in users().values() if u['id'] != user['id']]
    if not others:
        st.caption('Invite someone to the app to share a folder with them.')
        return
    labels = {f'{u["name"]} (@{u["handle"]})': u['id'] for u in others}
    picked = st.multiselect(
        'Shared with', list(labels), key=f'share_{name}',
        default=[label for label, uid in labels.items() if uid in folder.get('shared_with', [])])
    if st.button('Update sharing', key=f'shareapply_{name}', use_container_width=True):
        folder['shared_with'] = [labels[label] for label in picked]
        for uid in folder['shared_with']:
            from ..store import notify
            notify(uid, 'share', f'{user["name"]} shared the collection “{name}” with you.', '🗂️')
        save()
        st.toast('Sharing updated.', icon='🗂️')
        st.rerun()


def render(user: dict) -> None:
    section('Collections', 'Folders, shared spaces and private notes.', 'Saved')
    _create_row(user)

    cols_data = collections(user['id'])
    shared_with_me = [(uid, name, folder)
                      for uid, folders in db()['collections'].items() if uid != user['id']
                      for name, folder in folders.items()
                      if user['id'] in folder.get('shared_with', [])]

    if not cols_data and not shared_with_me:
        empty_state('🔖', 'Nothing saved yet',
                    'Tap Save on any card and it lands here. Folders keep it tidy.')
        return

    grid = st.columns(3)
    for i, (name, folder) in enumerate(sorted(cols_data.items())):
        with grid[i % 3]:
            _folder_card(user, name, folder)

    if shared_with_me:
        st.markdown('<div class="cf-eyebrow" style="margin:.9rem 0 .4rem">Shared with you</div>',
                    unsafe_allow_html=True)
        sgrid = st.columns(3)
        for i, (uid, name, folder) in enumerate(shared_with_me):
            owner = users().get(uid, {})
            with sgrid[i % 3]:
                st.markdown(f'<div class="cf-panel cf-flat">{folder.get("emoji", "📁")} '
                            f'<b>{esc(name)}</b><div class="cf-meta">from '
                            f'{esc(owner.get("name", "someone"))} · '
                            f'{len(folder.get("items", []))} cards</div></div>',
                            unsafe_allow_html=True)

    open_name = st.session_state.get('open_collection')
    if not open_name or open_name not in cols_data:
        return

    folder = cols_data[open_name]
    st.markdown('<div class="cf-spacer"></div>', unsafe_allow_html=True)
    section(f'{folder.get("emoji", "📁")}  {open_name}',
            f'{len(folder.get("items", []))} cards in this folder.', 'Collection')

    with st.expander('⚙️  Folder settings'):
        c1, c2 = st.columns(2)
        with c1:
            _share_controls(user, open_name, folder)
        with c2:
            if st.button('🗑  Delete folder', key=f'del_{open_name}', use_container_width=True):
                cols_data.pop(open_name, None)
                st.session_state['open_collection'] = None
                save()
                st.rerun()
            if st.button('📌  Make this my default save target', key=f'def_{open_name}',
                         use_container_width=True):
                st.session_state['default_collection'] = open_name
                st.toast(f'New cards now save to {open_name}.', icon='📌')

    items = [get_card(cid) for cid in folder.get('items', [])]
    items = [c for c in items if c]
    if not items:
        empty_state('📁', 'This folder is empty', 'Save a card into it from the feed.')
        return

    for card in items:
        render_card(user, card, ns=f'col_{open_name}')
        note = folder.setdefault('notes', {}).get(card['id'], '')
        with st.expander('📝  Private note' + (' · saved' if note else '')):
            text = st.text_area('Note', value=note, key=f'note_{open_name}_{card["id"]}',
                                height=90, label_visibility='collapsed',
                                placeholder='Only you can read this.')
            if st.button('Save note', key=f'notesave_{open_name}_{card["id"]}'):
                folder['notes'][card['id']] = text.strip()
                user.setdefault('counters', {})
                user['counters']['notes'] = user['counters'].get('notes', 0) + 1
                save()
                st.toast('Note saved.', icon='📝')
                st.rerun()
