"""Clode — a Claude-style chat assistant.

Two pieces live here:

* :mod:`clode.model` / :mod:`clode.tokenizer` / :mod:`clode.train` — a small
  decoder-only transformer implemented from scratch in NumPy, including the
  backward pass, so it can genuinely be trained on this machine.
* :mod:`clode.backends` — the chat backends the Streamlit UI talks to: the
  real Anthropic API when a key is configured, and the locally trained model
  otherwise.
"""

from clode.tokenizer import Tokenizer
from clode.model import Clode, Config

__all__ = ['Tokenizer', 'Clode', 'Config']
