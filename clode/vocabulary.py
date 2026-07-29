"""Vocabulary expansion from a real English frequency list.

A word the model never sees in a sentence is useless to it — its embedding
stays at its random initialisation. So the vocabulary cannot be grown by
pasting in a word list; every new word has to appear in text that is *true*,
or the model learns nonsense.

What is true about a word without any semantic resource is its spelling: how
many letters it has, what it starts and ends with, how it is spelled out, and
where it sorts against another word. Those facts are computable, verifiable,
and put thousands of real English words into real sentences.

The word list comes from ``wordfreq`` (ordered by frequency, so the words the
model learns first are the ones people actually use). If that package is not
installed the module degrades to a small built-in list rather than failing —
the corpus is still buildable, just with a smaller vocabulary.
"""

from __future__ import annotations

import random

FALLBACK_WORDS = """
time people water house world school family number letter market picture
mountain machine morning evening country garden window teacher student animal
history science music paper street summer winter number reason answer question
""".split()


def english_words(limit: int = 6000, min_length: int = 3) -> list[str]:
    """Most frequent English words, longest-tail first filtered for sanity."""
    try:
        from wordfreq import top_n_list
        candidates = top_n_list('en', limit * 2)
    except ImportError:
        candidates = FALLBACK_WORDS

    words = []
    seen = set()
    for word in candidates:
        if not word.isalpha() or not word.isascii():
            continue
        if len(word) < min_length or len(word) > 12:
            continue
        lower = word.lower()
        if lower in seen:
            continue
        seen.add(lower)
        words.append(lower)
        if len(words) >= limit:
            break
    return words


def ordinal(n: int) -> str:
    return {1: 'first', 2: 'second', 3: 'third', 4: 'fourth', 5: 'fifth',
            6: 'sixth', 7: 'seventh', 8: 'eighth'}.get(n, f'{n}th')


def spelling_pairs(words: list[str], rng: random.Random) -> list[tuple[str, str]]:
    """Question and answer pairs about how words are spelled.

    Every answer here is computed from the word itself, so all of it is true
    by construction — there is no source to be wrong about.
    """
    out: list[tuple[str, str]] = []
    for word in words:
        letters = ' '.join(word)
        out.append((f'how do you spell {word}', f'It is spelled {letters}.'))
        out.append((f'spell the word {word}', f'{word} is spelled {letters}.'))
        out.append((f'how many letters are in {word}',
                    f'The word {word} has {len(word)} letters.'))
        out.append((f'how many letters does {word} have',
                    f'It has {len(word)} letters.'))
        out.append((f'what letter does {word} start with',
                    f'{word} starts with {word[0]}.'))
        out.append((f'what letter does {word} end with',
                    f'{word} ends with {word[-1]}.'))
        out.append((f'what is the first letter of {word}', f'The first letter is {word[0]}.'))
        out.append((f'what is the last letter of {word}', f'The last letter is {word[-1]}.'))

    # Alphabetical comparisons, drawn between words that differ early enough
    # for the answer to be obvious from the first letter or two.
    for _ in range(len(words)):
        a, b = rng.sample(words, 2)
        if a[0] == b[0]:
            continue
        first, second = (a, b) if a < b else (b, a)
        out.append((f'which comes first alphabetically, {a} or {b}',
                    f'{first} comes before {second}.'))
        out.append((f'does {a} come before {b} alphabetically',
                    f'{"Yes" if a < b else "No"}, {first} comes first.'))
    return out


def letter_pairs() -> list[tuple[str, str]]:
    """The alphabet itself, so single letters are grounded too."""
    alphabet = 'abcdefghijklmnopqrstuvwxyz'
    out = []
    for i, letter in enumerate(alphabet):
        if i + 1 < len(alphabet):
            out.append((f'what letter comes after {letter}',
                        f'{alphabet[i + 1]} comes after {letter}.'))
        if i:
            out.append((f'what letter comes before {letter}',
                        f'{alphabet[i - 1]} comes before {letter}.'))
        if i < 8:
            out.append((f'what is the {ordinal(i + 1)} letter of the alphabet',
                        f'The {ordinal(i + 1)} letter is {letter}.'))
        out.append((f'is {letter} a vowel',
                    f'{"Yes" if letter in "aeiou" else "No"}, {letter} is a '
                    f'{"vowel" if letter in "aeiou" else "consonant"}.'))
    out.append(('how many letters are in the alphabet',
                'There are 26 letters in the English alphabet.'))
    out.append(('what are the vowels', 'The vowels are a, e, i, o and u.'))
    return out
