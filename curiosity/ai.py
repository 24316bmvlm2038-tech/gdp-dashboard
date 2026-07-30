"""The AI layer.

Two interchangeable engines sit behind one interface:

* **OpenAI** — used automatically when ``OPENAI_API_KEY`` is present in
  ``st.secrets`` or the environment. Calls go over plain ``urllib`` so no extra
  dependency is required.
* **On-device fallback** — a deterministic engine built on the app's own corpus
  and the user's profile. It is what runs with no key configured, so the
  assistant, card generation and moderation all still work offline.

``engine_name()`` tells the UI which one is live; the app never pretends a
model answered when it did not.
"""

from __future__ import annotations

import json
import os
import random
import re
import textwrap
from datetime import date

import streamlit as st

from .content import compose, make_card
from .models import CARD_TYPES, CATEGORIES
from .store import content, log_event, save

MODEL = 'gpt-4o-mini'
FREE_DAILY_MESSAGES = 20


# ---------------------------------------------------------------- transport

def api_key() -> str:
    key = ''
    try:
        key = st.secrets.get('OPENAI_API_KEY', '')   # type: ignore[union-attr]
    except Exception:
        pass
    return key or os.environ.get('OPENAI_API_KEY', '')


def engine_name() -> str:
    return 'OpenAI' if api_key() else 'On-device'


def _openai_chat(messages: list[dict], *, temperature: float = 0.8,
                 max_tokens: int = 700, json_mode: bool = False) -> str | None:
    key = api_key()
    if not key:
        return None
    import urllib.error
    import urllib.request

    body: dict = {'model': MODEL, 'messages': messages,
                  'temperature': temperature, 'max_tokens': max_tokens}
    if json_mode:
        body['response_format'] = {'type': 'json_object'}
    req = urllib.request.Request(
        'https://api.openai.com/v1/chat/completions',
        data=json.dumps(body).encode(),
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = json.loads(resp.read())
        return payload['choices'][0]['message']['content']
    except Exception as exc:  # network, quota, model errors
        log_event('ai_error', None, error=str(exc)[:200])
        return None


def _profile_prompt(user: dict) -> str:
    interests = ', '.join(user.get('interests', [])) or 'a broad mix of topics'
    return (
        f'The user is {user.get("name", "someone")} (@{user.get("handle", "")}), '
        f'interested in {interests}. Preferred learning style: '
        f'{user.get("learning_style") or "unspecified"}. '
        f'Difficulty preference: {user.get("difficulty", 3)}/5.'
    )


SYSTEM = (
    'You are the Curiosity Feed assistant. You help people think, not just look things up. '
    'Be precise, concrete and warm. Prefer specifics over generalities, admit uncertainty '
    'plainly, and never invent citations, statistics or sources. Keep answers under 220 words '
    'unless asked for depth.'
)


# ---------------------------------------------------------------- assistant

def ask(user: dict, question: str, history: list[dict] | None = None,
        mode: str = 'Explain') -> str:
    """Answer a user question with whichever engine is available."""
    personalise = user.get('settings', {}).get('privacy', {}).get('personalised_ai', True)
    messages = [{'role': 'system', 'content': SYSTEM + (
        '\n' + _profile_prompt(user) if personalise else '')}]
    if mode == 'Debate':
        messages[0]['content'] += (
            '\nThe user wants to be challenged. Take the strongest opposing position to '
            'whatever they claim, argue it honestly, and concede points that are genuinely good.')
    elif mode == 'Teach':
        messages[0]['content'] += (
            '\nExplain like a great teacher: one clear idea, one vivid analogy, one '
            'check-for-understanding question at the end.')
    for msg in (history or [])[-8:]:
        messages.append({'role': msg['role'], 'content': msg['content']})
    messages.append({'role': 'user', 'content': question})

    reply = _openai_chat(messages)
    if reply:
        return reply.strip()
    return _local_answer(user, question, mode)


# ---------------------------------------------------------------- local engine

_BOOKS = {
    'Science': ['*The Beginning of Infinity* — David Deutsch', '*Seven Brief Lessons on Physics* — Carlo Rovelli'],
    'Psychology': ['*Thinking, Fast and Slow* — Daniel Kahneman', '*The Body Keeps the Score* — Bessel van der Kolk'],
    'Business': ['*The Hard Thing About Hard Things* — Ben Horowitz', '*Zero to One* — Peter Thiel'],
    'History': ['*The Silk Roads* — Peter Frankopan', '*Postwar* — Tony Judt'],
    'Space': ['*Pale Blue Dot* — Carl Sagan', '*Packing for Mars* — Mary Roach'],
    'AI': ['*The Alignment Problem* — Brian Christian', '*Gödel, Escher, Bach* — Douglas Hofstadter'],
    'Finance': ['*The Psychology of Money* — Morgan Housel', '*Against the Gods* — Peter Bernstein'],
    'Nature': ['*Entangled Life* — Merlin Sheldrake', '*The Song of the Dodo* — David Quammen'],
    'Health': ['*Why We Sleep* — Matthew Walker', '*Breath* — James Nestor'],
    'Technology': ['*The Soul of a New Machine* — Tracy Kidder', '*The Dream Machine* — M. Mitchell Waldrop'],
}

_OPENERS = [
    'Here is the short version, then the interesting part.',
    'Two things are going on here.',
    'The honest answer is that it depends on one thing.',
]


def _corpus_hits(query: str, limit: int = 3) -> list[dict]:
    words = {w for w in re.findall(r'\w+', query.lower()) if len(w) > 3}
    scored = []
    for card in content().values():
        haystack = f'{card["title"]} {card["body"]} {card.get("reveal", "")} {" ".join(card.get("tags", []))}'.lower()
        hits = sum(1 for w in words if w in haystack)
        if hits:
            scored.append((hits, card))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [card for _, card in scored[:limit]]


def _local_answer(user: dict, question: str, mode: str) -> str:
    q = question.lower().strip()
    rng = random.Random(question)
    interests = user.get('interests') or ['Science']

    if any(k in q for k in ('book', 'read', 'recommend')):
        picks = []
        for cat in interests[:3]:
            picks += _BOOKS.get(cat, [])
        picks = picks or _BOOKS['Science']
        listed = '\n'.join(f'- {p}' for p in picks[:5])
        return (f'Based on your interests ({", ".join(interests[:3])}), start here:\n\n{listed}\n\n'
                'Pick the one whose first page you cannot put down — that is the only reliable signal.')

    if any(k in q for k in ('study plan', 'learn', 'curriculum', 'plan to')):
        topic = interests[0]
        for cat in CATEGORIES:
            if cat.lower() in q:
                topic = cat
        return _local_study_plan(topic)

    if mode == 'Debate' or q.startswith(('i think', 'i believe', 'debate')):
        return (
            f'Let me argue the other side.\n\n'
            f'You are treating one variable as decisive when at least two are. The strongest '
            f'counter to your position is that the effect you are describing is real but small, '
            f'and the costs you are discounting are concentrated on people who did not choose them.\n\n'
            f'Two questions I would want answered before agreeing with you:\n'
            f'1. What evidence would change your mind?\n'
            f'2. Who pays if you are wrong?\n\n'
            f'_(On-device engine — add an OpenAI key in settings for a sharper opponent.)_')

    hits = _corpus_hits(question)
    if hits:
        card = hits[0]
        detail = card.get('reveal') or card.get('explain') or card['body']
        extra = ''
        if len(hits) > 1:
            extra = '\n\nRelated in your feed: ' + ' · '.join(f'“{c["title"]}”' for c in hits[1:])
        return f'{rng.choice(_OPENERS)}\n\n**{card["title"]}**\n\n{detail}{extra}'

    return (
        f'{rng.choice(_OPENERS)}\n\nI do not have a confident answer to that offline, so here is '
        f'what I would actually do: break the question into the part that is factual and the part '
        f'that is a value judgement. The factual half usually has a source; the other half is where '
        f'the real disagreement lives.\n\n'
        f'_Running on the on-device engine. Add `OPENAI_API_KEY` to `.streamlit/secrets.toml` for '
        f'full model answers._')


def _local_study_plan(topic: str) -> str:
    return textwrap.dedent(f"""
        **A four-week plan for {topic}**

        **Week 1 — Map the territory.** Read one overview and write down the ten terms you cannot
        yet define. Those terms are your syllabus.

        **Week 2 — Go deep on one branch.** Pick the sub-topic that annoyed you most in week 1
        (confusion is a signal) and work through primary material, not summaries.

        **Week 3 — Build or argue.** Make something small, or write 500 words defending a position
        a knowledgeable person would disagree with. Producing exposes gaps that reading hides.

        **Week 4 — Teach it.** Explain the whole thing to someone who knows nothing about it in
        under ten minutes. Whatever you fumble is what you have not learned yet.
    """).strip()


# ---------------------------------------------------------------- generation

def generate_cards(user: dict, count: int = 3) -> list[dict]:
    """Create fresh personalised cards. Falls back to procedural composition."""
    interests = user.get('interests') or list(CATEGORIES)[:5]
    types = list(CARD_TYPES)
    key = api_key()
    if key:
        prompt = (
            f'Create {count} cards for a curiosity app. {_profile_prompt(user)}\n'
            f'Return JSON: {{"cards":[{{"type":..., "category":..., "title":..., "body":..., '
            f'"options":[...], "answer":<index or null>, "explain":..., "reveal":..., '
            f'"difficulty":1-5, "tags":[...]}}]}}\n'
            f'Allowed types: {", ".join(types)}. Allowed categories: {", ".join(CATEGORIES)}.\n'
            f'Prefer the categories {", ".join(interests[:5])}. Titles must be a single striking '
            f'question or claim under 90 characters. Bodies are 1-3 sentences. Quiz cards need '
            f'exactly 4 options with a correct "answer" index and an "explain". Reveal cards need '
            f'a "reveal" of 60-110 words. Never invent statistics you are not confident in.'
        )
        raw = _openai_chat([{'role': 'system', 'content': SYSTEM},
                            {'role': 'user', 'content': prompt}],
                           temperature=1.0, max_tokens=1600, json_mode=True)
        cards = _parse_cards(raw, count)
        if cards:
            store = content()
            for card in cards:
                store[card['id']] = card
            save()
            log_event('ai_generate', user['id'], count=len(cards), engine='openai')
            return cards

    base = random.Random(f'{user["id"]}-{date.today()}').randint(1000, 9000)
    cards = []
    store = content()
    for offset in range(count):
        card = compose(base + offset, interests)
        card['source'] = 'composed'
        store.setdefault(card['id'], card)
        cards.append(store[card['id']])
    save()
    log_event('ai_generate', user['id'], count=len(cards), engine='local')
    return cards


def _parse_cards(raw: str | None, count: int) -> list[dict]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    items = payload.get('cards') if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    out = []
    for item in items[:count]:
        if not isinstance(item, dict) or not item.get('title'):
            continue
        ctype = item.get('type') if item.get('type') in CARD_TYPES else 'Poll'
        cat = item.get('category') if item.get('category') in CATEGORIES else 'Science'
        out.append(make_card(
            type=ctype, category=cat, title=str(item['title'])[:140],
            body=str(item.get('body', ''))[:600],
            options=[str(o)[:120] for o in (item.get('options') or [])][:5],
            answer=item.get('answer') if isinstance(item.get('answer'), int) else None,
            explain=str(item.get('explain', ''))[:900],
            reveal=str(item.get('reveal', ''))[:1400],
            difficulty=int(item.get('difficulty', 3) or 3),
            tags=[str(t)[:24] for t in (item.get('tags') or [])][:5],
            source='ai', author='curiosity'))
    return out


def summarise(text: str) -> str:
    reply = _openai_chat([
        {'role': 'system', 'content': SYSTEM},
        {'role': 'user', 'content': f'Summarise in 3 bullet points, no preamble:\n\n{text[:6000]}'}],
        temperature=0.3, max_tokens=350)
    if reply:
        return reply.strip()
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    ranked = sorted(sentences, key=len, reverse=True)[:3]
    ordered = [s for s in sentences if s in ranked]
    return '\n'.join(f'- {s.strip()}' for s in ordered) or '- Nothing to summarise yet.'


def study_plan(topic: str, weeks: int = 4) -> str:
    reply = _openai_chat([
        {'role': 'system', 'content': SYSTEM},
        {'role': 'user', 'content':
            f'Write a {weeks}-week self-study plan for {topic}. One short paragraph per week, '
            f'each with a concrete deliverable. Markdown, no preamble.'}],
        temperature=0.6, max_tokens=700)
    return (reply or _local_study_plan(topic)).strip()


# ---------------------------------------------------------------- moderation

_BANNED = {
    'slur_placeholder',  # replace with a real list in production
}
_SPAM_PATTERNS = [
    re.compile(r'(https?://\S+){3,}'),
    re.compile(r'\b(free money|crypto giveaway|click here now|buy followers)\b', re.I),
    re.compile(r'(.)\1{12,}'),
    re.compile(r'[A-Z\s!]{40,}'),
]


def moderate(text: str) -> tuple[bool, str]:
    """Return ``(allowed, reason)``. Local rules first, model check if available."""
    stripped = text.strip()
    if not stripped:
        return False, 'Write something first.'
    if len(stripped) > 1200:
        return False, 'That is longer than 1,200 characters.'
    lowered = stripped.lower()
    if any(word in lowered for word in _BANNED):
        return False, 'That language is not allowed here.'
    for pattern in _SPAM_PATTERNS:
        if pattern.search(stripped):
            return False, 'This looks like spam — try again without the links or shouting.'

    key = api_key()
    if key:
        import urllib.request
        try:
            req = urllib.request.Request(
                'https://api.openai.com/v1/moderations',
                data=json.dumps({'model': 'omni-moderation-latest', 'input': stripped[:2000]}).encode(),
                headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
                method='POST')
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read())
            if result['results'][0]['flagged']:
                cats = [k for k, v in result['results'][0]['categories'].items() if v]
                return False, f'Blocked by moderation ({", ".join(cats[:2]) or "policy"}).'
        except Exception:
            pass
    return True, ''


def rate_limited(user: dict, bucket: str, limit: int, window_key: str | None = None) -> bool:
    """Simple per-day rate limit stored on the user record."""
    if user.get('premium'):
        return False
    window = window_key or date.today().isoformat()
    limits = user.setdefault('rate', {})
    entry = limits.setdefault(bucket, {'window': window, 'count': 0})
    if entry['window'] != window:
        entry.update({'window': window, 'count': 0})
    if entry['count'] >= limit:
        return True
    entry['count'] += 1
    return False
