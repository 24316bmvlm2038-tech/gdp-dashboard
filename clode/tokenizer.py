"""Word-level tokenizer for the Clode model.

The corpus is small, so a word-level vocabulary gives far more coherent
samples than characters would at the same parameter count. Words that fall
outside the vocabulary map to ``<|unk|>``.

Text is split into words, numbers and single punctuation marks. The chat
control tokens (``<|user|>``, ``<|assistant|>``, ``<|end|>``) survive
tokenization as single units.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

PAD = '<|pad|>'
UNK = '<|unk|>'
USER = '<|user|>'
ASSISTANT = '<|assistant|>'
END = '<|end|>'
SPECIALS = [PAD, UNK, USER, ASSISTANT, END]

# A control token, a word (letters/digits/underscore, possibly with an
# internal apostrophe or hyphen), or any single non-space character.
_PATTERN = re.compile(r"<\|[a-z]+\|>|[A-Za-z0-9_]+(?:['\-][A-Za-z0-9_]+)*|[^\sA-Za-z0-9_]")

# Punctuation that hugs the previous token when text is rebuilt.
_NO_SPACE_BEFORE = set(",.!?;:%)]}")
_NO_SPACE_AFTER = set("([{$#@")


def split(text: str) -> list[str]:
    """Split raw text into token strings."""
    return _PATTERN.findall(text)


class Tokenizer:
    """Maps token strings to ids and back."""

    def __init__(self, itos: list[str]):
        self.itos = list(itos)
        self.stoi = {t: i for i, t in enumerate(self.itos)}
        self.unk_id = self.stoi[UNK]
        self.pad_id = self.stoi[PAD]
        self.user_id = self.stoi[USER]
        self.assistant_id = self.stoi[ASSISTANT]
        self.end_id = self.stoi[END]

    # -- construction ----------------------------------------------------
    @classmethod
    def train(cls, text: str, max_vocab: int = 8192, min_count: int = 2) -> 'Tokenizer':
        counts = Counter(t for t in split(text) if t not in SPECIALS)
        keep = [t for t, c in counts.most_common() if c >= min_count]
        keep = keep[: max(0, max_vocab - len(SPECIALS))]
        return cls(SPECIALS + keep)

    @classmethod
    def load(cls, path: str | Path) -> 'Tokenizer':
        return cls(json.loads(Path(path).read_text(encoding='utf-8')))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.itos, ensure_ascii=False), encoding='utf-8')

    # -- use -------------------------------------------------------------
    @property
    def vocab_size(self) -> int:
        return len(self.itos)

    def lookup(self, token: str) -> int:
        """Token id, falling back across capitalisation before giving up.

        The corpus writes proper nouns capitalised ("Japan"), but people type
        "japan". Without this fallback those are unrelated tokens, and the
        model has to learn a separate lowercase-to-capitalised association for
        every name instead of simply copying the one it was given.
        """
        for candidate in (token, token.capitalize(), token.lower(), token.title(),
                          token.upper()):
            found = self.stoi.get(candidate)
            if found is not None:
                return found
        return self.unk_id

    def encode(self, text: str) -> list[int]:
        return [self.lookup(t) for t in split(text)]

    def decode(self, ids: list[int]) -> str:
        return self.join([self.itos[i] for i in ids if 0 <= i < len(self.itos)])

    @staticmethod
    def join(tokens: list[str]) -> str:
        """Rebuild readable text from token strings."""
        out: list[str] = []
        for tok in tokens:
            if tok in SPECIALS:
                continue
            if not out:
                out.append(tok)
                continue
            prev = out[-1]
            if tok in _NO_SPACE_BEFORE or prev in _NO_SPACE_AFTER or prev.endswith(('(', '[', '{')):
                out.append(tok)
            else:
                out.append(' ' + tok)
        return ''.join(out).strip()
