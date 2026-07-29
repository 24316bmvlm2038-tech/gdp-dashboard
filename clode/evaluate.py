"""Measure what the trained model actually learned.

    python -m clode.evaluate

Asks a fixed set of questions with known answers and reports how often the
greedy-decoded reply contains the right one, grouped by category. This is the
check that "we trained it" means something: a model that has not learned the
corpus scores near zero here even though it produces fluent-looking text.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np

from clode.model import Clode
from clode.tokenizer import Tokenizer

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = ROOT / 'data' / 'clode-mini.npz'
VOCAB = ROOT / 'data' / 'clode-vocab.json'

# (category, question, accepted answer fragments)
CASES: list[tuple[str, str, tuple[str, ...]]] = [
    ('geography', 'what is the capital of japan', ('Tokyo',)),
    ('geography', 'what is the capital of france', ('Paris',)),
    ('geography', 'capital of italy', ('Rome',)),
    ('geography', 'what is the capital of canada', ('Ottawa',)),
    ('geography', 'whats the capital city of egypt', ('Cairo',)),
    ('geography', 'what is the capital of norway', ('Oslo',)),
    ('geography', 'what language do they speak in brazil', ('Portuguese',)),
    ('geography', 'what language do they speak in japan', ('Japanese',)),

    ('arithmetic', 'what is 12 + 30', ('42',)),
    ('arithmetic', 'what is 7 x 8', ('56',)),
    ('arithmetic', 'what is 9 x 9', ('81',)),
    ('arithmetic', 'what is 20 - 5', ('15',)),
    ('arithmetic', 'what is the square of 7', ('49',)),
    ('arithmetic', 'is 8 even or odd', ('even',)),
    ('arithmetic', 'is 7 even or odd', ('odd',)),

    ('facts', 'how many minutes are in an hour', ('60',)),
    ('facts', 'how many days are in a week', ('7',)),
    ('facts', 'how many planets are in the solar system', ('8',)),
    ('facts', 'what is the boiling point of water', ('100',)),
    ('facts', 'how many sides does a triangle have', ('3',)),

    ('python', 'how do i reverse a list in python', ('reverse', '[::-1]')),
    ('python', 'how do i sort a list in python', ('sorted', 'sort')),
    ('python', 'how do i read a file in python', ('open',)),
    ('python', 'how do i swap two variables in python', ('a, b = b, a', 'one line')),
    ('python', 'how do i reverse a string', ('[::-1]',)),

    ('definitions', 'what is a variable', ('named box', 'value')),
    ('definitions', 'what is recursion', ('itself',)),
    ('definitions', 'what is overfitting', ('memorises', 'training data')),
    ('definitions', 'what is a transformer', ('attention',)),

    ('persona', 'who are you', ('Clode',)),
    ('persona', 'are you claude', ('No',)),
    ('persona', 'can you browse the internet', ('No', 'no network')),
    ('persona', 'are you human', ('No',)),

    ('smalltalk', 'hello', ('Hello', 'Hi', 'Hey')),
    ('smalltalk', 'thanks', ('welcome', 'Happy to help', 'Any time')),
]


def answer(model: Clode, tok: Tokenizer, question: str, max_new_tokens: int = 40) -> str:
    ids = tok.encode(f'<|user|> {question} <|assistant|>')
    out = list(model.generate(
        ids, max_new_tokens=max_new_tokens, temperature=0.0,
        repetition_penalty=1.0,
        stop_ids=(tok.end_id, tok.user_id, tok.assistant_id),
    ))
    return tok.decode(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--weights', default=str(WEIGHTS))
    ap.add_argument('--vocab', default=str(VOCAB))
    ap.add_argument('--show', action='store_true', help='print every answer')
    args = ap.parse_args()

    model = Clode.load(args.weights)
    tok = Tokenizer.load(args.vocab)
    print(f'{model.n_params:,} parameters | vocab {tok.vocab_size}\n')

    hits: dict[str, int] = defaultdict(int)
    totals: dict[str, int] = defaultdict(int)
    for category, question, accepted in CASES:
        reply = answer(model, tok, question)
        ok = any(a.lower() in reply.lower() for a in accepted)
        hits[category] += ok
        totals[category] += 1
        if args.show or not ok:
            print(f'{"✓" if ok else "✗"} {question}\n    {reply}')

    print('\n{:<14}{:>10}'.format('category', 'accuracy'))
    for category in totals:
        print('{:<14}{:>6}/{:<3} {:>4.0f}%'.format(
            category, hits[category], totals[category],
            100 * hits[category] / totals[category]))
    total_hits, total = sum(hits.values()), sum(totals.values())
    print('{:<14}{:>6}/{:<3} {:>4.0f}%'.format(
        'OVERALL', total_hits, total, 100 * total_hits / total))


if __name__ == '__main__':
    main()
