"""Export the trained model for the browser.

Weight matrices are quantised to int8 with a per-output-column scale, which
takes the checkpoint from ~13.9 MB to ~3.5 MB — small enough to embed
directly in a self-contained web page. Biases and layer-norm gains are tiny,
so they stay float32.

    python -m tools.export_web

Writes ``data/clode-web.json``: the config, a tensor manifest, and one
base64 blob holding every tensor back to back.
"""

from __future__ import annotations

import base64
import json
from dataclasses import asdict
from pathlib import Path

import numpy as np

from clode.model import Clode
from clode.tokenizer import Tokenizer

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = ROOT / 'data' / 'clode-mini.npz'
VOCAB = ROOT / 'data' / 'clode-vocab.json'
OUT = ROOT / 'data' / 'clode-web.json'


def quantize(w: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """int8 per-column quantisation of a 2-D weight matrix."""
    scale = np.abs(w).max(axis=0) / 127.0
    scale[scale == 0] = 1e-8
    q = np.clip(np.rint(w / scale), -127, 127).astype(np.int8)
    return q, scale.astype(np.float32)


def main() -> None:
    model = Clode.load(WEIGHTS)
    tok = Tokenizer.load(VOCAB)

    chunks: list[bytes] = []
    manifest: list[dict] = []
    offset = 0
    max_err = 0.0

    for name, w in model.params.items():
        entry = {'name': name, 'shape': list(w.shape), 'offset': offset}
        if w.ndim == 2:
            q, scale = quantize(w)
            recon = q.astype(np.float32) * scale
            denom = float(np.abs(w).max()) or 1.0
            max_err = max(max_err, float(np.abs(recon - w).max()) / denom)
            entry.update(dtype='int8', bytes=q.nbytes, scale_bytes=scale.nbytes)
            chunks.append(q.tobytes())
            chunks.append(scale.tobytes())
            offset += q.nbytes + scale.nbytes
        else:
            data = w.astype(np.float32)
            entry.update(dtype='float32', bytes=data.nbytes, scale_bytes=0)
            chunks.append(data.tobytes())
            offset += data.nbytes
        manifest.append(entry)

    blob = b''.join(chunks)
    payload = {
        'config': asdict(model.cfg),
        'vocab': tok.itos,
        'tensors': manifest,
        'weights_b64': base64.b64encode(blob).decode('ascii'),
    }
    OUT.write_text(json.dumps(payload), encoding='utf-8')

    print(f'{len(manifest)} tensors | blob {len(blob) / 1e6:.2f} MB '
          f'| base64 {len(payload["weights_b64"]) / 1e6:.2f} MB')
    print(f'worst relative quantisation error: {max_err:.4%}')
    print(f'wrote {OUT}')


if __name__ == '__main__':
    main()
