"""Loading a model and its vocabulary as one unit.

Weights and vocabulary are only meaningful together: token 412 means whatever
the vocabulary says it means. Load a mismatched pair and nothing raises — the
model happily generates from misaligned ids and produces confident nonsense
("The a of Denmark is lowercase Beirut"), which reads like a training failure
and sends you looking in the wrong place. It cost me a wrong diagnosis once.

So there is exactly one way to load a pair, and it refuses when the two do not
agree.
"""

from __future__ import annotations

from pathlib import Path

from clode.model import Clode
from clode.tokenizer import Tokenizer


class CheckpointMismatch(RuntimeError):
    """Weights and vocabulary describe different vocabularies."""


def load_pair(weights: str | Path, vocab: str | Path) -> tuple[Clode, Tokenizer]:
    """Load weights and vocabulary, or fail loudly explaining why not."""
    weights, vocab = Path(weights), Path(vocab)
    model = Clode.load(weights)
    tok = Tokenizer.load(vocab)
    if model.cfg.vocab_size != tok.vocab_size:
        raise CheckpointMismatch(
            f'{weights.name} was trained with a vocabulary of '
            f'{model.cfg.vocab_size:,} tokens, but {vocab.name} holds '
            f'{tok.vocab_size:,}. These do not belong together — a checkpoint '
            f'and its vocabulary are written as a pair, so this usually means '
            f'one of them is from a different (or still running) training run.'
        )
    return model, tok
