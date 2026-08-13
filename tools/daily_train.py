"""One day's worth of training, safe to run unattended.

Designed to be fired on a schedule. Each run:

1. rebuilds the corpus (so any change to ``clode/corpus.py`` takes effect),
2. warm-starts from the released model — the vocabulary may have grown, and
   embeddings for words that survive are carried across by name,
3. trains for a bounded number of steps,
4. scores the result against the released model on the held-out questions,
5. **promotes only if it actually got better.**

Step 5 is the important one. Training is not monotonic, and a scheduled job
that always overwrites the released model will eventually publish a worse one
while nobody is watching. A run that fails to beat what is already there
leaves it alone and says so.

    python -m tools.daily_train --steps 600
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
WEIGHTS = DATA / 'clode-mini.npz'
VOCAB = DATA / 'clode-vocab.json'
CHECKPOINTS = DATA / 'checkpoints'
HISTORY = DATA / 'daily-training.json'


def run(*args: str) -> None:
    print(f'$ {" ".join(args)}', flush=True)
    subprocess.run([sys.executable, '-m', *args], check=True, cwd=ROOT)


def score(weights: Path, vocab: Path) -> tuple[int, int]:
    """Held-out accuracy of a checkpoint, as (correct, total)."""
    from clode.checkpoint import load_pair
    from clode.evaluate import CASES, answer

    model, tok = load_pair(weights, vocab)
    correct = 0
    for _, question, accepted in CASES:
        reply = answer(model, tok, question)
        correct += any(a.lower() in reply.lower() for a in accepted)
    return correct, len(CASES)


def record(entry: dict) -> None:
    history = []
    if HISTORY.exists():
        try:
            history = json.loads(HISTORY.read_text(encoding='utf-8'))
        except json.JSONDecodeError:
            pass
    history.append(entry)
    HISTORY.write_text(json.dumps(history, indent=1), encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--steps', type=int, default=600,
                    help='training steps for this run (a few hundred fits in an hour)')
    ap.add_argument('--max-vocab', type=int, default=8192)
    ap.add_argument('--skip-corpus', action='store_true')
    args = ap.parse_args()

    started = time.time()
    sys.path.insert(0, str(ROOT))
    CHECKPOINTS.mkdir(parents=True, exist_ok=True)

    if not args.skip_corpus:
        run('clode.corpus')

    base_weights = CHECKPOINTS / 'daily-base.npz'
    base_vocab = CHECKPOINTS / 'daily-base-vocab.json'
    have_base = WEIGHTS.exists() and VOCAB.exists()
    if have_base:
        shutil.copyfile(WEIGHTS, base_weights)
        shutil.copyfile(VOCAB, base_vocab)
        before = score(base_weights, base_vocab)
        print(f'released model scores {before[0]}/{before[1]}', flush=True)
    else:
        before = (0, 0)
        print('no released model yet — training from scratch', flush=True)

    train_args = ['clode.train', '--steps', str(args.steps),
                  '--max-vocab', str(args.max_vocab),
                  '--eval-every', '100', '--save-every', '200', '--no-promote']
    if have_base:
        train_args += ['--warm-start', str(base_weights), '--warm-vocab', str(base_vocab)]
    run(*train_args)

    trained = CHECKPOINTS / 'clode-training.npz'
    trained_vocab = CHECKPOINTS / 'clode-training-vocab.json'
    after = score(trained, trained_vocab)
    print(f'trained model scores {after[0]}/{after[1]}', flush=True)

    improved = after[0] > before[0] or not have_base
    if improved:
        shutil.copyfile(trained, WEIGHTS)
        shutil.copyfile(trained_vocab, VOCAB)
        print(f'promoted: {before[0]} -> {after[0]} of {after[1]}', flush=True)
    else:
        print(f'not promoted: {after[0]} did not beat {before[0]} of {after[1]}; '
              f'the released model is unchanged', flush=True)

    record({
        'when': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'steps': args.steps,
        'before': before[0],
        'after': after[0],
        'total': after[1],
        'promoted': improved,
        'minutes': round((time.time() - started) / 60, 1),
    })
    return 0 if improved else 1


if __name__ == '__main__':
    raise SystemExit(main())
