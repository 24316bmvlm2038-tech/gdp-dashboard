"""Chat backends for the Clode app.

Two implementations behind one streaming interface:

* :class:`AnthropicBackend` — the real Claude API. Used when an API key is
  configured; this is the "as powerful as possible" path.
* :class:`LocalBackend` — the transformer in :mod:`clode.model`, trained from
  scratch by ``clode.train``. Always available offline, and much smaller.

Both expose ``stream(messages, system) -> Iterator[str]`` yielding text chunks.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = ROOT / 'data' / 'clode-mini.npz'
VOCAB = ROOT / 'data' / 'clode-vocab.json'

# The Claude models the app can talk to, best first.
API_MODELS = [
    ('claude-opus-5', 'Claude Opus 5'),
    ('claude-fable-5', 'Claude Fable 5'),
    ('claude-sonnet-5', 'Claude Sonnet 5'),
    ('claude-haiku-4-5', 'Claude Haiku 4.5'),
]

DEFAULT_SYSTEM = (
    'You are Clode, a helpful, direct assistant. Answer clearly and get to '
    'the point. Say plainly when you are unsure of something.'
)


@dataclass
class Message:
    role: str            # 'user' | 'assistant'
    content: str


# --------------------------------------------------------------------------
# Anthropic API
# --------------------------------------------------------------------------

class AnthropicBackend:
    """Streams from the real Claude API."""

    kind = 'api'

    def __init__(self, model: str = 'claude-opus-5', api_key: str | None = None):
        import anthropic  # imported lazily so the app runs without the SDK

        self.model = model
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    @property
    def label(self) -> str:
        return dict(API_MODELS).get(self.model, self.model)

    @staticmethod
    def key_available() -> bool:
        return bool(os.environ.get('ANTHROPIC_API_KEY'))

    def stream(self, messages: Iterable[Message], system: str = DEFAULT_SYSTEM,
               effort: str = 'high', web_search: bool = False) -> Iterator[str]:
        payload = [{'role': m.role, 'content': m.content} for m in messages]
        kwargs = dict(
            model=self.model,
            max_tokens=8000,
            system=system,
            messages=payload,
            output_config={'effort': effort},
        )
        if web_search:
            # Anthropic runs the search server-side: Claude decides when to
            # search, and the results never pass through this process.
            kwargs['tools'] = [{'type': 'web_search_20260209', 'name': 'web_search',
                                'max_uses': 5}]
        try:
            # Server-side fallbacks keep a policy refusal from dead-ending the
            # conversation: the API retries on the recommended model instead.
            with self._client.beta.messages.stream(
                betas=['server-side-fallback-2026-07-01'],
                fallbacks='default',
                **kwargs,
            ) as stream:
                yield from stream.text_stream
                return
        except (TypeError, self._anthropic.BadRequestError, self._anthropic.NotFoundError):
            pass  # older SDK or beta unavailable — fall through to the plain call
        with self._client.messages.stream(**kwargs) as stream:
            yield from stream.text_stream


# --------------------------------------------------------------------------
# Local from-scratch model
# --------------------------------------------------------------------------

class LocalBackend:
    """Streams from the NumPy transformer trained by ``clode.train``."""

    kind = 'local'
    label = 'Clode-mini (trained here)'

    def __init__(self, weights: Path = WEIGHTS, vocab: Path = VOCAB):
        import numpy as np

        from clode.checkpoint import load_pair

        self._np = np
        self.model, self.tok = load_pair(weights, vocab)

    @staticmethod
    def available(weights: Path = WEIGHTS, vocab: Path = VOCAB) -> bool:
        return weights.exists() and vocab.exists()

    @property
    def n_params(self) -> int:
        return self.model.n_params

    def _prompt_ids(self, messages: Iterable[Message]) -> list[int]:
        """Encode as much recent conversation as the context window allows."""
        turns: list[list[int]] = []
        for m in messages:
            marker = self.tok.user_id if m.role == 'user' else self.tok.assistant_id
            ids = [marker] + self.tok.encode(m.content)
            if m.role == 'assistant':
                ids.append(self.tok.end_id)
            turns.append(ids)

        prompt = [self.tok.assistant_id]
        budget = self.model.cfg.n_ctx - 1
        kept: list[int] = []
        for ids in reversed(turns):
            if len(kept) + len(ids) > budget:
                break
            kept = ids + kept
        return (kept + prompt)[-self.model.cfg.n_ctx:]

    def stream(self, messages: Iterable[Message], system: str = '',
               temperature: float = 0.75, max_new_tokens: int = 80,
               grounding: str = '') -> Iterator[str]:
        """Generate a reply.

        ``grounding`` is accepted so the caller can pass retrieved web text,
        but it is deliberately *not* fed to the model: with a 1,700 word
        vocabulary and a 128 token context, web prose arrives as almost all
        unknown tokens and derails the reply. The app shows the retrieved text
        itself, attributed, instead of laundering it through the model.
        """
        ids = self._prompt_ids(messages)
        emitted: list[str] = []
        text = ''
        for tid in self.model.generate(
            ids,
            max_new_tokens=max_new_tokens,
            temperature=temperature,
            top_p=0.9,
            repetition_penalty=1.15,
            stop_ids=(self.tok.end_id, self.tok.user_id, self.tok.assistant_id),
            rng=self._np.random.default_rng(),
        ):
            emitted.append(self.tok.itos[tid])
            new_text = self.tok.join(emitted)
            if new_text != text:
                yield new_text[len(text):]
                text = new_text
        if not text:
            yield "I don't have an answer for that one."


def describe_status() -> dict:
    """What the UI shows in the sidebar."""
    return {
        'api_key': AnthropicBackend.key_available(),
        'sdk': _sdk_installed(),
        'local_weights': LocalBackend.available(),
    }


def _sdk_installed() -> bool:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True
