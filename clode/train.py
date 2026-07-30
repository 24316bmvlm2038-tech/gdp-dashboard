"""Train the Clode model on ``data/corpus.txt``.

    python -m clode.train --steps 3000

Checkpoints go to ``data/checkpoints/`` every ``--save-every`` steps, and the
finished run is promoted to ``data/clode-mini.npz`` — the model the app and
the web build load. Keeping the two apart means a long run does not rewrite
the released weights every few minutes; pass ``--no-promote`` to leave them
untouched, or ``--out`` to checkpoint somewhere else.
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import time
from pathlib import Path

import numpy as np

from clode.model import Adam, Clode, Config
from clode.tokenizer import Tokenizer

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
CORPUS = DATA / 'corpus.txt'
WEIGHTS = DATA / 'clode-mini.npz'          # the released model the app loads
CHECKPOINTS = DATA / 'checkpoints'         # in-progress checkpoints (not tracked)
VOCAB = DATA / 'clode-vocab.json'
LOG = DATA / 'training-log.json'


def get_batch(tokens: np.ndarray, batch_size: int, n_ctx: int, rng: np.random.Generator):
    ix = rng.integers(0, len(tokens) - n_ctx - 1, size=batch_size)
    x = np.stack([tokens[i:i + n_ctx] for i in ix])
    y = np.stack([tokens[i + 1:i + 1 + n_ctx] for i in ix])
    return x, y


def evaluate(model: Clode, tokens: np.ndarray, batch_size: int, batches: int, seed: int = 0) -> float:
    rng = np.random.default_rng(seed)
    total = 0.0
    for _ in range(batches):
        x, y = get_batch(tokens, batch_size, model.cfg.n_ctx, rng)
        total += model.forward(x, y)[1]
    return total / batches


def lr_at(step: int, steps: int, base_lr: float, warmup: int, min_ratio: float = 0.1) -> float:
    if step < warmup:
        return base_lr * (step + 1) / warmup
    progress = (step - warmup) / max(1, steps - warmup)
    cosine = 0.5 * (1 + math.cos(math.pi * min(1.0, progress)))
    return base_lr * (min_ratio + (1 - min_ratio) * cosine)


def warm_start(old_weights: Path, old_vocab: Path, tok: Tokenizer, cfg: Config) -> Clode:
    """Carry a previous run's learning into a new, larger vocabulary.

    Growing the corpus grows the vocabulary, which changes the shape of the
    token embedding and would normally mean starting from scratch. Everything
    except that embedding is shape-compatible, though, and embeddings for
    words that survive into the new vocabulary can be copied across by name —
    so only genuinely new words start from random.
    """
    old = Clode.load(old_weights)
    old_tok = Tokenizer.load(old_vocab)
    model = Clode(cfg)

    carried = 0
    for name, value in old.params.items():
        if name == 'wte':
            continue
        if name in model.params and model.params[name].shape == value.shape:
            model.params[name] = value.copy()
            carried += 1

    rows = 0
    for token, new_id in tok.stoi.items():
        old_id = old_tok.stoi.get(token)
        if old_id is not None:
            model.params['wte'][new_id] = old.params['wte'][old_id]
            rows += 1

    print(f'warm start: carried {carried} tensors, {rows}/{tok.vocab_size} '
          f'embedding rows ({rows / tok.vocab_size:.0%} of the new vocabulary)')
    return model


def sample(model: Clode, tok: Tokenizer, prompt: str, max_new_tokens: int = 48) -> str:
    ids = tok.encode(f'<|user|> {prompt} <|assistant|>')
    out = list(model.generate(ids, max_new_tokens=max_new_tokens, temperature=0.7,
                              top_p=0.9, stop_ids=(tok.end_id, tok.user_id),
                              rng=np.random.default_rng(0)))
    return tok.decode(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--steps', type=int, default=3000)
    ap.add_argument('--batch-size', type=int, default=32)
    ap.add_argument('--n-ctx', type=int, default=128)
    ap.add_argument('--n-embd', type=int, default=256)
    ap.add_argument('--n-head', type=int, default=4)
    ap.add_argument('--n-layer', type=int, default=4)
    ap.add_argument('--lr', type=float, default=6e-4)
    ap.add_argument('--warmup', type=int, default=100)
    ap.add_argument('--eval-every', type=int, default=100)
    ap.add_argument('--save-every', type=int, default=200)
    ap.add_argument('--max-vocab', type=int, default=4096)
    ap.add_argument('--out', type=str, default=None,
                    help='where to write checkpoints during the run '
                         '(default: data/checkpoints/clode-training.npz)')
    ap.add_argument('--no-promote', action='store_true',
                    help='leave the released model alone when the run finishes')
    ap.add_argument('--resume', action='store_true')
    ap.add_argument('--warm-start', type=str, default=None,
                    help='checkpoint to carry into the new vocabulary')
    ap.add_argument('--warm-vocab', type=str, default=None,
                    help='vocabulary that checkpoint was trained with')
    args = ap.parse_args()

    CHECKPOINTS.mkdir(parents=True, exist_ok=True)
    # Training writes here, not over the model the app is serving: a long run
    # would otherwise rewrite the released weights every few minutes.
    out = Path(args.out) if args.out else CHECKPOINTS / 'clode-training.npz'
    # The vocabulary is part of the checkpoint: weights trained on one
    # vocabulary are meaningless with another, so they are written together
    # and promoted together.
    out_vocab = out.with_name(out.stem + '-vocab.json')

    text = CORPUS.read_text(encoding='utf-8')
    if out_vocab.exists() and args.resume:
        tok = Tokenizer.load(out_vocab)
    else:
        tok = Tokenizer.train(text, max_vocab=args.max_vocab)
    tok.save(out_vocab)
    ids = np.array(tok.encode(text), dtype=np.int64)
    split_at = int(len(ids) * 0.98)
    train_ids, val_ids = ids[:split_at], ids[split_at:]
    print(f'vocab {tok.vocab_size} | train {len(train_ids):,} tokens | val {len(val_ids):,}')

    cfg = Config(vocab_size=tok.vocab_size, n_ctx=args.n_ctx, n_embd=args.n_embd,
                 n_head=args.n_head, n_layer=args.n_layer)
    if args.resume and WEIGHTS.exists():
        model = Clode.load(WEIGHTS)
        print('resumed from checkpoint')
    elif args.warm_start:
        model = warm_start(Path(args.warm_start), Path(args.warm_vocab), tok, cfg)
    else:
        model = Clode(cfg)
    print(f'parameters: {model.n_params:,}')

    # Write the checkpoint immediately, so the weights and the vocabulary on
    # disk always describe the same model. Otherwise anything reading the
    # checkpoint before the first save interval pairs this run's vocabulary
    # with the previous run's weights, and mismatched ids generate confident
    # nonsense instead of raising.
    model.save(out)

    opt = Adam(model.params, lr=args.lr, weight_decay=0.01)
    rng = np.random.default_rng(0)
    history: list[dict] = []
    started = time.time()
    best_val = float('inf')

    for step in range(args.steps):
        lr = lr_at(step, args.steps, args.lr, args.warmup)
        x, y = get_batch(train_ids, args.batch_size, model.cfg.n_ctx, rng)
        loss, grads = model.loss_and_grads(x, y)
        gnorm = opt.step(grads, lr=lr)

        if step % args.eval_every == 0 or step == args.steps - 1:
            val = evaluate(model, val_ids, args.batch_size, batches=6)
            best_val = min(best_val, val)
            elapsed = time.time() - started
            print(f'step {step:5d}/{args.steps} | loss {loss:.3f} | val {val:.3f} '
                  f'| ppl {math.exp(min(val, 20)):7.2f} | lr {lr:.2e} | gnorm {gnorm:5.2f} '
                  f'| {elapsed / 60:.1f} min', flush=True)
            history.append({'step': step, 'train_loss': loss, 'val_loss': val,
                            'lr': lr, 'elapsed_s': round(elapsed, 1)})
            LOG.write_text(json.dumps(history, indent=1), encoding='utf-8')

        if step and step % args.save_every == 0:
            model.save(out)

    model.save(out)
    print(f'\nsaved {out} after {(time.time() - started) / 60:.1f} min '
          f'(best val {best_val:.3f})')
    if not args.no_promote:
        # The finished run becomes the released model in one step, so the
        # tracked file changes once per run rather than once per checkpoint.
        shutil.copyfile(out, WEIGHTS)
        shutil.copyfile(out_vocab, VOCAB)
        print(f'promoted to {WEIGHTS} (with its vocabulary)')
    for prompt in ['who are you', 'what is the capital of japan', 'what is 12 + 30',
                   'how do i reverse a list in python', 'hello']:
        print(f'\n> {prompt}\n{sample(model, tok, prompt)}')


if __name__ == '__main__':
    main()
