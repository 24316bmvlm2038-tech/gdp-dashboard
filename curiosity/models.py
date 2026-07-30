"""Domain constants for Curiosity Feed: categories, card types, XP curve,
achievements and the shape of a user record.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

# ---------------------------------------------------------------- categories

CATEGORIES: dict[str, dict] = {
    'Technology': {'emoji': '💻', 'grad': 'ocean'},
    'Business': {'emoji': '📈', 'grad': 'gold'},
    'Science': {'emoji': '🔬', 'grad': 'aurora'},
    'Space': {'emoji': '🪐', 'grad': 'indigo'},
    'History': {'emoji': '🏛️', 'grad': 'slate'},
    'Psychology': {'emoji': '🧠', 'grad': 'plum'},
    'Finance': {'emoji': '💰', 'grad': 'forest'},
    'Movies': {'emoji': '🎬', 'grad': 'sunset'},
    'Gaming': {'emoji': '🎮', 'grad': 'plum'},
    'Politics': {'emoji': '🗳️', 'grad': 'slate'},
    'Sports': {'emoji': '🏅', 'grad': 'forest'},
    'Books': {'emoji': '📚', 'grad': 'gold'},
    'AI': {'emoji': '🤖', 'grad': 'aurora'},
    'Nature': {'emoji': '🌿', 'grad': 'forest'},
    'Health': {'emoji': '🫀', 'grad': 'sunset'},
    'Music': {'emoji': '🎧', 'grad': 'plum'},
    'Cooking': {'emoji': '🍳', 'grad': 'gold'},
    'Languages': {'emoji': '🗣️', 'grad': 'ocean'},
    'Travel': {'emoji': '✈️', 'grad': 'aurora'},
}

LEARNING_STYLES = {
    'Reading': {'emoji': '📖', 'favours': ['Scientific Fact', 'AI Generated Story',
                                           'Life Advice', 'Space Discovery',
                                           'Future Technology']},
    'Visual': {'emoji': '👁️', 'favours': ['Visual Puzzle', 'Daily Mystery',
                                          'Space Discovery', 'Scientific Fact']},
    'Debates': {'emoji': '⚖️', 'favours': ['Debate', 'Philosophy Question',
                                           'Impossible Question', 'Historical What If']},
    'Quizzes': {'emoji': '🧩', 'favours': ['Mini Quiz', 'Brain Teaser', 'Visual Puzzle']},
    'Videos': {'emoji': '🎞️', 'favours': ['AI Generated Story', 'Space Discovery',
                                          'Future Technology', 'AI Prediction']},
    'Interactive': {'emoji': '✋', 'favours': ['Would You Rather', 'Poll', 'Money Scenario',
                                              'Productivity Challenge', 'Business Challenge']},
}

# ---------------------------------------------------------------- card types

CARD_TYPES: dict[str, dict] = {
    'Would You Rather': {'emoji': '🔀', 'grad': 'plum', 'kind': 'choice', 'xp': 12},
    'Daily Mystery': {'emoji': '🕯️', 'grad': 'slate', 'kind': 'reveal', 'xp': 14},
    'AI Prediction': {'emoji': '🔮', 'grad': 'aurora', 'kind': 'stance', 'xp': 12},
    'Historical What If': {'emoji': '⏳', 'grad': 'gold', 'kind': 'choice', 'xp': 14},
    'Scientific Fact': {'emoji': '🔬', 'grad': 'ocean', 'kind': 'reveal', 'xp': 8},
    'Brain Teaser': {'emoji': '🧠', 'grad': 'indigo', 'kind': 'quiz', 'xp': 20},
    'Philosophy Question': {'emoji': '🏛️', 'grad': 'slate', 'kind': 'open', 'xp': 16},
    'Debate': {'emoji': '⚔️', 'grad': 'sunset', 'kind': 'stance', 'xp': 18},
    'Poll': {'emoji': '📊', 'grad': 'ocean', 'kind': 'choice', 'xp': 8},
    'Mini Quiz': {'emoji': '🧩', 'grad': 'forest', 'kind': 'quiz', 'xp': 20},
    'Business Challenge': {'emoji': '💼', 'grad': 'gold', 'kind': 'open', 'xp': 22},
    'Startup Idea': {'emoji': '🚀', 'grad': 'indigo', 'kind': 'stance', 'xp': 16},
    'Impossible Question': {'emoji': '♾️', 'grad': 'plum', 'kind': 'open', 'xp': 18},
    'Visual Puzzle': {'emoji': '🎨', 'grad': 'aurora', 'kind': 'quiz', 'xp': 20},
    'AI Generated Story': {'emoji': '📜', 'grad': 'sunset', 'kind': 'reveal', 'xp': 10},
    'Life Advice': {'emoji': '🌱', 'grad': 'forest', 'kind': 'reveal', 'xp': 8},
    'Productivity Challenge': {'emoji': '⚡', 'grad': 'gold', 'kind': 'task', 'xp': 24},
    'Space Discovery': {'emoji': '🛰️', 'grad': 'indigo', 'kind': 'reveal', 'xp': 10},
    'Future Technology': {'emoji': '🧬', 'grad': 'aurora', 'kind': 'stance', 'xp': 12},
    'Money Scenario': {'emoji': '💸', 'grad': 'forest', 'kind': 'choice', 'xp': 14},
}

# Interaction kinds:
#   choice  – pick one of N options, results shown as percentages
#   stance  – agree / unsure / disagree
#   quiz    – one correct answer, scored
#   open    – free text reflection
#   reveal  – tap to reveal the answer / the rest of the story
#   task    – accept a challenge and mark it done

DIFFICULTIES = {1: 'Gentle', 2: 'Easy', 3: 'Balanced', 4: 'Deep', 5: 'Expert'}

# ---------------------------------------------------------------- daily slots

DAILY_SLOTS = [
    ('Daily Curiosity', 'Would You Rather', '🌅'),
    ('Daily Fact', 'Scientific Fact', '💡'),
    ('Daily Challenge', 'Productivity Challenge', '⚡'),
    ('Daily Debate', 'Debate', '⚔️'),
    ('Daily Mystery', 'Daily Mystery', '🕯️'),
    ('Daily Quiz', 'Mini Quiz', '🧩'),
    ('Daily AI Prediction', 'AI Prediction', '🔮'),
    ('Daily Goal', 'Productivity Challenge', '🎯'),
    ('Daily Inspiration', 'Life Advice', '🌱'),
    ('Daily Journal Prompt', 'Philosophy Question', '📓'),
]

# ---------------------------------------------------------------- progression

XP_ACTIONS = {
    'answer': 12, 'quiz_correct': 25, 'quiz_wrong': 6, 'reveal': 8,
    'comment': 10, 'bookmark': 4, 'share': 15, 'challenge_done': 30,
    'daily_complete': 60, 'note': 6, 'follow': 3, 'assistant': 5,
}


def level_for_xp(xp: int) -> tuple[int, int, int, str]:
    """Return ``(level, xp_into_level, xp_needed_for_next, title)``.

    The curve is quadratic-ish: level n starts at 60 * n * (n - 1) / 2 XP, so
    early levels arrive quickly and later ones take real curiosity.
    """
    level = 1
    while xp >= _level_floor(level + 1):
        level += 1
        if level > 200:
            break
    floor = _level_floor(level)
    nxt = _level_floor(level + 1)
    return level, xp - floor, max(1, nxt - floor), level_title(level)


def _level_floor(level: int) -> int:
    return int(60 * level * (level - 1) / 2)


LEVEL_TITLES = [
    (1, 'Curious'), (3, 'Wanderer'), (5, 'Questioner'), (8, 'Explorer'),
    (12, 'Thinker'), (17, 'Analyst'), (23, 'Polymath'), (30, 'Sage'),
    (40, 'Luminary'), (55, 'Mastermind'),
]


def level_title(level: int) -> str:
    title = 'Curious'
    for threshold, name in LEVEL_TITLES:
        if level >= threshold:
            title = name
    return title


# ---------------------------------------------------------------- achievements

ACHIEVEMENTS: list[dict] = [
    {'id': 'first_spark', 'name': 'First Spark', 'emoji': '✨', 'tier': 'bronze',
     'desc': 'Answer your very first card.', 'metric': 'answers', 'goal': 1},
    {'id': 'warmed_up', 'name': 'Warmed Up', 'emoji': '🔥', 'tier': 'bronze',
     'desc': 'Answer 25 cards.', 'metric': 'answers', 'goal': 25},
    {'id': 'hundred_club', 'name': 'Hundred Club', 'emoji': '💯', 'tier': 'silver',
     'desc': 'Answer 100 cards.', 'metric': 'answers', 'goal': 100},
    {'id': 'thousand_thoughts', 'name': 'Thousand Thoughts', 'emoji': '🌌', 'tier': 'gold',
     'desc': 'Answer 1000 cards.', 'metric': 'answers', 'goal': 1000},
    {'id': 'thinker_7', 'name': '7-Day Thinker', 'emoji': '🧠', 'tier': 'bronze',
     'desc': 'Keep a 7-day streak.', 'metric': 'streak', 'goal': 7},
    {'id': 'explorer_30', 'name': '30-Day Explorer', 'emoji': '🧭', 'tier': 'silver',
     'desc': 'Keep a 30-day streak.', 'metric': 'streak', 'goal': 30},
    {'id': 'genius_100', 'name': '100-Day Genius', 'emoji': '🎓', 'tier': 'gold',
     'desc': 'Keep a 100-day streak.', 'metric': 'streak', 'goal': 100},
    {'id': 'mastermind_365', 'name': '365-Day Mastermind', 'emoji': '👑', 'tier': 'legend',
     'desc': 'Keep a 365-day streak.', 'metric': 'streak', 'goal': 365},
    {'id': 'quiz_sharp', 'name': 'Sharp Mind', 'emoji': '🎯', 'tier': 'silver',
     'desc': 'Get 50 quiz answers right.', 'metric': 'quiz_correct', 'goal': 50},
    {'id': 'debater', 'name': 'Devil’s Advocate', 'emoji': '⚔️', 'tier': 'silver',
     'desc': 'Take a stance in 40 debates.', 'metric': 'debates', 'goal': 40},
    {'id': 'librarian', 'name': 'Librarian', 'emoji': '🗂️', 'tier': 'bronze',
     'desc': 'Save 20 cards to collections.', 'metric': 'bookmarks', 'goal': 20},
    {'id': 'conversationalist', 'name': 'Conversationalist', 'emoji': '💬', 'tier': 'bronze',
     'desc': 'Leave 15 comments.', 'metric': 'comments', 'goal': 15},
    {'id': 'signal_boost', 'name': 'Signal Boost', 'emoji': '📣', 'tier': 'silver',
     'desc': 'Share 10 answer cards.', 'metric': 'shares', 'goal': 10},
    {'id': 'polymath', 'name': 'Polymath', 'emoji': '🌈', 'tier': 'gold',
     'desc': 'Explore 12 different categories.', 'metric': 'topics', 'goal': 12},
    {'id': 'night_owl', 'name': 'Night Owl', 'emoji': '🦉', 'tier': 'bronze',
     'desc': 'Answer a card after midnight.', 'metric': 'night_answers', 'goal': 1},
    {'id': 'deep_diver', 'name': 'Deep Diver', 'emoji': '🌊', 'tier': 'silver',
     'desc': 'Spend 5 hours reading in the app.', 'metric': 'reading_minutes', 'goal': 300},
    {'id': 'ai_companion', 'name': 'AI Companion', 'emoji': '🤝', 'tier': 'bronze',
     'desc': 'Have 25 exchanges with the assistant.', 'metric': 'assistant_msgs', 'goal': 25},
    {'id': 'challenger', 'name': 'Challenger', 'emoji': '🏋️', 'tier': 'silver',
     'desc': 'Complete 20 daily challenges.', 'metric': 'challenges', 'goal': 20},
]

TIER_COLORS = {'bronze': '#B45309', 'silver': '#64748B', 'gold': '#F59E0B', 'legend': '#7C3AED'}

AVATAR_COLORS = ['#2563EB', '#7C3AED', '#22C55E', '#F59E0B', '#EF4444', '#0EA5E9',
                 '#EC4899', '#14B8A6', '#8B5CF6', '#F97316']

COUNTRIES = ['Germany', 'United States', 'United Kingdom', 'France', 'Spain', 'Italy',
             'Netherlands', 'Poland', 'Sweden', 'Canada', 'Brazil', 'India', 'Japan',
             'Australia', 'Nigeria', 'Kenya', 'Mexico', 'Türkiye', 'Portugal', 'Other']

LANGUAGES = ['English', 'Deutsch', 'Español', 'Français', 'Italiano', 'Português',
             'Nederlands', 'Polski', 'Türkçe', '日本語']

SHARE_TARGETS = [
    ('Instagram Stories', '📸', None),
    ('TikTok', '🎵', None),
    ('X', '𝕏', 'https://twitter.com/intent/tweet?text={text}'),
    ('Threads', '@', 'https://www.threads.net/intent/post?text={text}'),
    ('Facebook', '📘', 'https://www.facebook.com/sharer/sharer.php?u={url}&quote={text}'),
    ('WhatsApp', '💬', 'https://wa.me/?text={text}'),
    ('Snapchat', '👻', None),
    ('Pinterest', '📌', 'https://pinterest.com/pin/create/button/?url={url}&description={text}'),
    ('LinkedIn', '💼', 'https://www.linkedin.com/sharing/share-offsite/?url={url}'),
]

PREMIUM_PERKS = [
    ('Unlimited AI', 'No daily cap on assistant messages or generated cards.'),
    ('Exclusive content', 'Expert-tier decks and long-form deep dives.'),
    ('Advanced analytics', 'Full history, accuracy breakdowns, topic drift.'),
    ('Voice AI', 'Talk to the assistant hands-free.'),
    ('Priority generation', 'Your feed regenerates first, always fresh.'),
    ('Custom themes', 'Extra gradients and card skins.'),
    ('Profile customization', 'Banners, badges and a custom handle colour.'),
    ('Early access', 'New card types before anyone else.'),
    ('No advertisements', 'Nothing between you and the next idea.'),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def today_str() -> str:
    return date.today().isoformat()


def parse_iso(value: str) -> datetime:
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def ago(value: str) -> str:
    delta = datetime.now(timezone.utc) - parse_iso(value)
    secs = int(delta.total_seconds())
    if secs < 60:
        return 'just now'
    if secs < 3600:
        return f'{secs // 60}m ago'
    if secs < 86400:
        return f'{secs // 3600}h ago'
    if secs < 604800:
        return f'{secs // 86400}d ago'
    return parse_iso(value).strftime('%d %b')
