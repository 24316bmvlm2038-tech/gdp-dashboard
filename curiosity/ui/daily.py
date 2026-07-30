"""The daily ritual: ten slots that reset every morning."""

from __future__ import annotations

from datetime import date

import streamlit as st

from .. import engine
from ..content import pick_daily
from ..models import DAILY_SLOTS, today_str
from ..store import interaction, save
from ..theme import haptic
from .components import empty_state, esc, render_card, section


def _ring(done: int, total: int) -> str:
    pct = int(100 * done / total) if total else 0
    return f"""
      <div class="cf-card cf-in" style="margin-bottom:1rem">
        <div class="cf-aura" style="background:linear-gradient(135deg,#F59E0B,#EF4444)"></div>
        <div class="cf-row" style="justify-content:space-between;align-items:center">
          <div>
            <div class="cf-eyebrow">{date.today().strftime('%A · %d %B')}</div>
            <div class="cf-display" style="font-size:1.9rem;margin:.2rem 0 .3rem">
              Today’s curiosity</div>
            <div class="cf-body">Ten small rituals. Finish five to bank the daily bonus.</div>
          </div>
          <div style="text-align:center;min-width:118px">
            <div style="font-size:2.5rem;font-weight:820;letter-spacing:-.03em;color:var(--text)">
              {done}<span style="color:var(--text-3);font-size:1.2rem">/{total}</span></div>
            <div class="cf-meta">complete</div>
          </div>
        </div>
        <div style="height:9px;border-radius:99px;background:var(--surface-2);overflow:hidden;
             margin-top:.9rem">
          <div style="height:100%;width:{pct}%;border-radius:99px;
            background:linear-gradient(90deg,#F59E0B,#EF4444)"></div>
        </div>
      </div>"""


def _slot_done(user: dict, slot: str, card: dict | None) -> bool:
    if slot in user.get('daily_done', {}).get(today_str(), []):
        return True
    if not card:
        return False
    inter = interaction(user['id'], card['id'])
    return bool(inter.get('answer') is not None or inter.get('revealed') or inter.get('done'))


def render(user: dict) -> None:
    today = today_str()
    slots = []
    for name, ctype, icon in DAILY_SLOTS:
        card = pick_daily(name, ctype, today)
        slots.append((name, ctype, icon, card))

    done_count = sum(1 for name, _, _, card in slots if _slot_done(user, name, card))
    st.markdown(_ring(done_count, len(slots)), unsafe_allow_html=True)

    active = st.session_state.get('daily_slot', DAILY_SLOTS[0][0])
    cols = st.columns(5)
    for i, (name, ctype, icon, card) in enumerate(slots):
        with cols[i % 5]:
            complete = _slot_done(user, name, card)
            label = f'{"✓" if complete else icon}\n{name.replace("Daily ", "")}'
            if st.button(label, key=f'daily_{i}', use_container_width=True,
                         type='primary' if name == active else 'secondary'):
                st.session_state['daily_slot'] = name
                haptic('light')
                st.rerun()

    st.markdown('<div class="cf-spacer"></div>', unsafe_allow_html=True)
    chosen = next((s for s in slots if s[0] == active), slots[0])
    name, ctype, icon, card = chosen
    section(name, f'{icon}  Refreshes at midnight, the same for everyone.', 'Daily')
    if not card:
        empty_state('🌙', 'Nothing scheduled', 'Come back tomorrow for a new one.')
        return

    render_card(user, card, ns=f'daily_{name.replace(" ", "")}')

    if _slot_done(user, name, card) and name not in user.get('daily_done', {}).get(today, []):
        engine.mark_daily_done(user, name)
        save()

    if done_count + 1 >= 5:
        st.markdown(
            '<div class="cf-panel cf-flat cf-in" style="text-align:center;margin-top:.8rem">'
            '<div class="cf-eyebrow">Daily bonus</div>'
            '<div class="cf-body">Five slots done — +60 XP banked and your streak is safe.</div>'
            '</div>', unsafe_allow_html=True)
