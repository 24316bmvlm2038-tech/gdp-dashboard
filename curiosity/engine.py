"""Personalisation, progression and the interaction pipeline.

This is the part of the app that learns: every answer, bookmark, share, comment
and second of reading time updates a user's topic and card-type affinities,
which then re-rank the feed.
"""

from __future__ import annotations

import math
import random
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from .content import ensure_seeded, next_composed
from .models import (ACHIEVEMENTS, CARD_TYPES, CATEGORIES, LEARNING_STYLES,
                     XP_ACTIONS, level_for_xp, now_iso, parse_iso, today_str)
from .store import (card as get_card, comments, content, db, interaction,
                    interactions, log_event, notify, save, users)

# ---------------------------------------------------------------- progression


def award_xp(user: dict, action: str, amount: int | None = None) -> int:
    gain = amount if amount is not None else XP_ACTIONS.get(action, 5)
    if user.get('premium'):
        gain = int(round(gain * 1.1))
    before = level_for_xp(user.get('xp', 0))[0]
    user['xp'] = user.get('xp', 0) + gain
    after = level_for_xp(user['xp'])[0]
    if after > before:
        notify(user['id'], 'achievement',
               f'Level {after} reached — you are now a {level_for_xp(user["xp"])[3]}.', '⭐')
    return gain


def register_activity(user: dict) -> bool:
    """Roll the daily streak forward. Returns True if today is a new day."""
    streak = user.setdefault('streak', {'current': 0, 'longest': 0, 'last_day': '', 'days': []})
    today = today_str()
    last = streak.get('last_day', '')
    if last == today:
        return False
    if last:
        gap = (date.fromisoformat(today) - date.fromisoformat(last)).days
        streak['current'] = streak.get('current', 0) + 1 if gap == 1 else 1
    else:
        streak['current'] = 1
    streak['last_day'] = today
    streak['longest'] = max(streak.get('longest', 0), streak['current'])
    if today not in streak.setdefault('days', []):
        streak['days'].append(today)
    del streak['days'][:-400]
    if streak['current'] > 1:
        notify(user['id'], 'streak', f'{streak["current"]}-day streak. Keep it alive.', '🔥')
    return True


def _metric(user: dict, name: str) -> int:
    counters = user.get('counters', {})
    if name == 'streak':
        return user.get('streak', {}).get('longest', 0)
    if name == 'topics':
        return len(user.get('topics', {}))
    if name == 'reading_minutes':
        return int(counters.get('reading_seconds', 0) / 60)
    if name == 'assistant_msgs':
        return counters.get('assistant_msgs', 0)
    return counters.get(name, 0)


def check_achievements(user: dict) -> list[dict]:
    unlocked = set(user.setdefault('achievements', []))
    fresh = []
    for ach in ACHIEVEMENTS:
        if ach['id'] in unlocked:
            continue
        if _metric(user, ach['metric']) >= ach['goal']:
            user['achievements'].append(ach['id'])
            fresh.append(ach)
            award_xp(user, 'achievement', 50)
            notify(user['id'], 'achievement',
                   f'Achievement unlocked: {ach["name"]} {ach["emoji"]}', ach['emoji'])
    return fresh


def achievement_progress(user: dict) -> list[tuple[dict, int, bool]]:
    out = []
    for ach in ACHIEVEMENTS:
        have = _metric(user, ach['metric'])
        pct = min(100, int(100 * have / ach['goal'])) if ach['goal'] else 0
        out.append((ach, pct, ach['id'] in user.get('achievements', [])))
    return out


# ---------------------------------------------------------------- affinities

def _bump(mapping: dict, key: str, amount: float) -> None:
    mapping[key] = round(mapping.get(key, 0.0) + amount, 3)


def learn(user: dict, card: dict, weight: float) -> None:
    _bump(user.setdefault('topics', {}), card['category'], weight)
    _bump(user.setdefault('type_affinity', {}), card['type'], weight * 0.8)
    for tag in card.get('tags', [])[:3]:
        _bump(user.setdefault('tag_affinity', {}), tag, weight * 0.4)


# ---------------------------------------------------------------- interactions

def record_answer(user: dict, card: dict, choice: int | str, text: str = '') -> dict:
    """Store an answer, update aggregate votes, award XP and learn from it."""
    inter = interaction(user['id'], card['id'])
    first_time = 'answer' not in inter
    inter['answer'] = choice
    inter['answer_text'] = text
    inter['answered_at'] = now_iso()

    counters = user.setdefault('counters', {})
    result = {'xp': 0, 'correct': None, 'new_achievements': []}

    if isinstance(choice, int) and card.get('options'):
        votes = db()['votes'].setdefault(card['id'], {})
        if first_time:
            votes[str(choice)] = votes.get(str(choice), 0) + 1

    if card.get('kind') == 'quiz' and card.get('answer') is not None:
        correct = (choice == card['answer'])
        inter['correct'] = correct
        result['correct'] = correct
        if first_time:
            counters['quiz_total'] = counters.get('quiz_total', 0) + 1
            if correct:
                counters['quiz_correct'] = counters.get('quiz_correct', 0) + 1
        result['xp'] = award_xp(user, 'quiz_correct' if correct else 'quiz_wrong')
    else:
        result['xp'] = award_xp(user, 'answer')

    if first_time:
        counters['answers'] = counters.get('answers', 0) + 1
        if card['type'] in ('Debate', 'AI Prediction', 'Philosophy Question'):
            counters['debates'] = counters.get('debates', 0) + 1
        if datetime.now().hour < 5:
            counters['night_answers'] = counters.get('night_answers', 0) + 1

    learn(user, card, 1.0)
    register_activity(user)
    result['new_achievements'] = check_achievements(user)
    log_event('answer', user['id'], card=card['id'], type=card['type'])
    save()
    return result


def toggle_like(user: dict, card: dict) -> bool:
    inter = interaction(user['id'], card['id'])
    inter['liked'] = not inter.get('liked', False)
    if inter['liked']:
        award_xp(user, 'bookmark', 3)
        learn(user, card, 0.6)
        if card.get('author') not in (None, 'curiosity', user['id']):
            author = users().get(card['author'])
            if author and author.get('settings', {}).get('notifications', {}).get('likes', True):
                notify(card['author'], 'like', f'{user["name"]} liked “{card["title"][:48]}”', '❤️')
    save()
    return inter['liked']


def toggle_bookmark(user: dict, card: dict, collection: str = 'Favorites') -> bool:
    from .store import collections as user_collections
    inter = interaction(user['id'], card['id'])
    inter['bookmarked'] = not inter.get('bookmarked', False)
    cols = user_collections(user['id'])
    folder = cols.setdefault(collection, {'emoji': '⭐', 'items': [], 'shared_with': [],
                                          'notes': {}, 'created_at': now_iso()})
    if inter['bookmarked']:
        if card['id'] not in folder['items']:
            folder['items'].append(card['id'])
        user.setdefault('counters', {})
        user['counters']['bookmarks'] = user['counters'].get('bookmarks', 0) + 1
        award_xp(user, 'bookmark')
        learn(user, card, 1.4)
        check_achievements(user)
    else:
        for f in cols.values():
            if card['id'] in f['items']:
                f['items'].remove(card['id'])
    save()
    return inter['bookmarked']


def add_comment(user: dict, card: dict, text: str, parent: str | None = None) -> dict:
    from .store import new_id
    comment = {
        'id': new_id('cm'), 'uid': user['id'], 'text': text.strip()[:1200],
        'at': now_iso(), 'likes': [], 'parent': parent, 'hidden': False,
    }
    comments(card['id']).append(comment)
    user.setdefault('counters', {})
    user['counters']['comments'] = user['counters'].get('comments', 0) + 1
    award_xp(user, 'comment')
    learn(user, card, 1.2)
    register_activity(user)
    check_achievements(user)
    if parent:
        for existing in comments(card['id']):
            if existing['id'] == parent and existing['uid'] != user['id']:
                notify(existing['uid'], 'reply',
                       f'{user["name"]} replied to your comment.', '💬', card['id'])
    log_event('comment', user['id'], card=card['id'])
    save()
    return comment


def record_share(user: dict, card: dict, target: str) -> None:
    inter = interaction(user['id'], card['id'])
    inter['shared'] = inter.get('shared', 0) + 1
    user.setdefault('counters', {})
    user['counters']['shares'] = user['counters'].get('shares', 0) + 1
    award_xp(user, 'share')
    check_achievements(user)
    log_event('share', user['id'], card=card['id'], target=target)
    save()


def record_reading(user: dict, card: dict, seconds: int) -> None:
    inter = interaction(user['id'], card['id'])
    inter['read_seconds'] = inter.get('read_seconds', 0) + seconds
    user.setdefault('counters', {})
    user['counters']['reading_seconds'] = user['counters'].get('reading_seconds', 0) + seconds
    learn(user, card, min(1.0, seconds / 45))
    check_achievements(user)


def reveal(user: dict, card: dict) -> None:
    inter = interaction(user['id'], card['id'])
    if not inter.get('revealed'):
        inter['revealed'] = True
        award_xp(user, 'reveal')
        learn(user, card, 0.9)
        record_reading(user, card, card.get('read_time', 20))
        register_activity(user)
        save()


def complete_challenge(user: dict, card: dict) -> None:
    inter = interaction(user['id'], card['id'])
    if inter.get('done'):
        return
    inter['done'] = True
    inter['done_at'] = now_iso()
    user.setdefault('counters', {})
    user['counters']['challenges'] = user['counters'].get('challenges', 0) + 1
    award_xp(user, 'challenge_done')
    register_activity(user)
    check_achievements(user)
    save()


def vote_totals(cid: str, options: list[str]) -> list[int]:
    votes = db()['votes'].get(cid, {})
    return [int(votes.get(str(i), 0)) for i in range(len(options))]


def vote_percentages(cid: str, options: list[str]) -> list[int]:
    totals = vote_totals(cid, options)
    total = sum(totals)
    if not total:
        return [0] * len(options)
    return [int(round(100 * n / total)) for n in totals]


# ---------------------------------------------------------------- feed

def _recency_boost(card: dict) -> float:
    age_h = (datetime.now(timezone.utc) - parse_iso(card['created_at'])).total_seconds() / 3600
    return math.exp(-age_h / (24 * 21))


def score_card(user: dict, card: dict, seen: dict) -> float:
    topics = user.get('topics', {})
    types = user.get('type_affinity', {})
    tags = user.get('tag_affinity', {})
    interests = user.get('interests', []) or list(CATEGORIES)
    style = LEARNING_STYLES.get(user.get('learning_style', ''), {}).get('favours', [])

    score = 1.0
    if card['category'] in interests:
        score += 2.6
    score += 0.55 * math.log1p(max(0.0, topics.get(card['category'], 0.0)))
    score += 0.45 * math.log1p(max(0.0, types.get(card['type'], 0.0)))
    score += 0.30 * sum(math.log1p(max(0.0, tags.get(t, 0.0))) for t in card.get('tags', [])[:3])
    if card['type'] in style:
        score += 1.5

    target = user.get('difficulty', 3)
    score -= 0.42 * abs(card.get('difficulty', 3) - target)

    inter = seen.get(card['id'], {})
    if inter.get('answer') is not None or inter.get('revealed') or inter.get('done'):
        score -= 6.0
    if inter.get('skipped'):
        score -= 3.5
    if inter.get('bookmarked'):
        score += 0.8

    votes = sum(db()['votes'].get(card['id'], {}).values())
    score += 0.25 * math.log1p(votes)
    score += 0.9 * _recency_boost(card)
    if card.get('featured'):
        score += 1.2

    # A deterministic jitter keeps the feed from feeling like a ranked list.
    score += random.Random(f'{user["id"]}-{card["id"]}').random() * 0.7
    return score


def build_feed(user: dict, limit: int = 12, exclude: set[str] | None = None) -> list[dict]:
    ensure_seeded()
    seen = interactions(user['id'])
    exclude = exclude or set()
    pool = [c for c in content().values() if c['id'] not in exclude]

    unanswered = [c for c in pool if not (
        seen.get(c['id'], {}).get('answer') is not None
        or seen.get(c['id'], {}).get('revealed')
        or seen.get(c['id'], {}).get('done'))]
    if len(unanswered) < limit:
        interests = user.get('interests') or list(CATEGORIES)
        unanswered += next_composed({c['id'] for c in pool}, limit * 2, interests)

    ranked = sorted(unanswered, key=lambda c: score_card(user, c, seen), reverse=True)

    # Diversity pass: never show three cards of the same type in a row.
    out: list[dict] = []
    recent_types: list[str] = []
    leftovers: list[dict] = []
    for card in ranked:
        if len(out) >= limit:
            break
        if recent_types[-2:].count(card['type']) == 2:
            leftovers.append(card)
            continue
        out.append(card)
        recent_types.append(card['type'])
    for card in leftovers:
        if len(out) >= limit:
            break
        out.append(card)
    return out


def trending(limit: int = 8) -> list[dict]:
    scored = []
    for cid, card in content().items():
        votes = sum(db()['votes'].get(cid, {}).values())
        chatter = len(db()['comments'].get(cid, []))
        scored.append((votes * 1.0 + chatter * 2.5 + _recency_boost(card) * 3, card))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [card for score, card in scored[:limit] if score > 0]


def trending_topics(limit: int = 8) -> list[tuple[str, int]]:
    counter: Counter = Counter()
    for cid, card in content().items():
        weight = sum(db()['votes'].get(cid, {}).values()) + 2 * len(db()['comments'].get(cid, []))
        if weight:
            counter[card['category']] += weight
    if not counter:
        counter.update({c: 1 for c in list(CATEGORIES)[:limit]})
    return counter.most_common(limit)


# ---------------------------------------------------------------- statistics

def user_stats(user: dict) -> dict:
    counters = user.get('counters', {})
    inters = interactions(user['id'])
    quiz_total = counters.get('quiz_total', 0)
    accuracy = int(round(100 * counters.get('quiz_correct', 0) / quiz_total)) if quiz_total else 0
    level, into, need, title = level_for_xp(user.get('xp', 0))
    return {
        'answers': counters.get('answers', 0),
        'days_active': len(set(user.get('streak', {}).get('days', []))),
        'reading_minutes': int(counters.get('reading_seconds', 0) / 60),
        'topics': len(user.get('topics', {})),
        'accuracy': accuracy,
        'quiz_total': quiz_total,
        'quiz_correct': counters.get('quiz_correct', 0),
        'debates': counters.get('debates', 0),
        'comments': counters.get('comments', 0),
        'shares': counters.get('shares', 0),
        'bookmarks': sum(1 for i in inters.values() if i.get('bookmarked')),
        'challenges': counters.get('challenges', 0),
        'streak': user.get('streak', {}).get('current', 0),
        'longest': user.get('streak', {}).get('longest', 0),
        'level': level, 'level_into': into, 'level_need': need, 'title': title,
        'xp': user.get('xp', 0),
    }


def heatmap_days(user: dict, weeks: int = 26) -> list[tuple[str, int]]:
    """Return ``(iso_date, intensity 0-4)`` for the last N weeks."""
    active = set(user.get('streak', {}).get('days', []))
    per_day: Counter = Counter()
    for inter in interactions(user['id']).values():
        stamp = inter.get('answered_at') or inter.get('done_at')
        if stamp:
            per_day[parse_iso(stamp).date().isoformat()] += 1
    out = []
    today = date.today()
    start = today - timedelta(days=weeks * 7 - 1)
    for offset in range(weeks * 7):
        day = (start + timedelta(days=offset)).isoformat()
        count = per_day.get(day, 0)
        if not count and day in active:
            count = 1
        out.append((day, min(4, count)))
    return out


def monthly_progress(user: dict) -> list[tuple[str, int]]:
    per_month: Counter = Counter()
    for inter in interactions(user['id']).values():
        stamp = inter.get('answered_at')
        if stamp:
            per_month[parse_iso(stamp).strftime('%Y-%m')] += 1
    months = sorted(per_month)[-6:]
    return [(m, per_month[m]) for m in months]


# ---------------------------------------------------------------- leaderboards

def leaderboard(scope: str, user: dict, period: str = 'All time') -> list[dict]:
    everyone = [u for u in users().values()
                if u.get('settings', {}).get('privacy', {}).get('show_in_leaderboards', True)]
    if scope == 'Friends':
        allowed = set(db()['friends'].get(user['id'], [])) | set(db()['follows'].get(user['id'], []))
        allowed.add(user['id'])
        everyone = [u for u in everyone if u['id'] in allowed]
    elif scope == 'Country':
        everyone = [u for u in everyone if u.get('country') == user.get('country')]

    if period == 'All time':
        key = lambda u: u.get('xp', 0)  # noqa: E731
    else:
        days = 7 if period == 'This week' else 30
        cutoff = (date.today() - timedelta(days=days)).isoformat()

        def key(u, cutoff=cutoff):  # XP proxy: recent answers
            recent = [i for i in db()['interactions'].get(u['id'], {}).values()
                      if (i.get('answered_at') or '')[:10] >= cutoff]
            return len(recent) * 12
    ranked = sorted(everyone, key=key, reverse=True)
    return [{'user': u, 'score': key(u), 'rank': i + 1} for i, u in enumerate(ranked)]


def rank_of(board: list[dict], uid: str) -> int | None:
    for row in board:
        if row['user']['id'] == uid:
            return row['rank']
    return None


# ---------------------------------------------------------------- daily

def daily_state(user: dict) -> dict:
    today = today_str()
    done = user.setdefault('daily_done', {}).setdefault(today, [])
    return {'date': today, 'done': done}


def mark_daily_done(user: dict, slot: str) -> bool:
    today = today_str()
    done = user.setdefault('daily_done', {}).setdefault(today, [])
    if slot in done:
        return False
    done.append(slot)
    register_activity(user)
    if len(done) >= 5:
        award_xp(user, 'daily_complete')
        notify(user['id'], 'daily', 'Daily set complete — +60 XP.', '🎯')
    check_achievements(user)
    save()
    return True


def suggested_difficulty(user: dict) -> int:
    """Nudge difficulty toward the level where the user is ~70% accurate."""
    counters = user.get('counters', {})
    total, correct = counters.get('quiz_total', 0), counters.get('quiz_correct', 0)
    if total < 8:
        return user.get('difficulty', 3)
    acc = correct / total
    current = user.get('difficulty', 3)
    if acc > 0.85:
        return min(5, current + 1)
    if acc < 0.45:
        return max(1, current - 1)
    return current
