"""Tests for the chat backends that don't need network access or weights."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clode.backends import LocalBackend, Message
from clode.model import Clode, Config
from clode.tokenizer import Tokenizer


@pytest.fixture
def backend(tmp_path):
    """A LocalBackend around a tiny untrained model."""
    text = ('<|user|> hello there <|assistant|> Hi. How can I help? <|end|> '
            '<|user|> what is two plus two <|assistant|> It is 4. <|end|>')
    tok = Tokenizer.train(text, min_count=1)
    vocab_path = tmp_path / 'vocab.json'
    tok.save(vocab_path)

    model = Clode(Config(vocab_size=tok.vocab_size, n_ctx=32, n_embd=16,
                         n_head=2, n_layer=2))
    weights = tmp_path / 'm.npz'
    model.save(weights)
    return LocalBackend(weights=weights, vocab=vocab_path)


def test_prompt_ends_ready_for_the_assistant(backend):
    ids = backend._prompt_ids([Message('user', 'hello there')])
    assert ids[-1] == backend.tok.assistant_id
    assert backend.tok.user_id in ids


def test_prompt_never_exceeds_context(backend):
    long_history = [Message('user', 'hello there hello there hello there')
                    for _ in range(50)]
    ids = backend._prompt_ids(long_history)
    assert len(ids) <= backend.model.cfg.n_ctx


def test_prompt_keeps_the_most_recent_turns(backend):
    """When history overflows, the newest turns are the ones retained."""
    history = [Message('user', 'hello there'), Message('assistant', 'Hi.'),
               Message('user', 'what is two plus two')]
    ids = backend._prompt_ids(history)
    tail = backend.tok.encode('what is two plus two') + [backend.tok.assistant_id]
    assert ids[-len(tail):] == tail


def test_stream_yields_text_and_terminates(backend):
    chunks = list(backend.stream([Message('user', 'hello there')], max_new_tokens=8))
    assert chunks, 'backend produced nothing at all'
    assert all(isinstance(c, str) for c in chunks)
    assert ''.join(chunks).strip()


def test_availability_reflects_missing_files(tmp_path):
    assert not LocalBackend.available(tmp_path / 'nope.npz', tmp_path / 'nope.json')
