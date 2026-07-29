"""Assemble the self-contained web build of Clode-mini.

Inlines the JavaScript model, the exported weights and the training history
into one HTML file with no external requests — which is what lets it be
published as an artifact and run offline.

    python -m tools.export_web && python -m tools.build_web
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / 'web' / 'index.template.html'
MODEL_JS = ROOT / 'web' / 'clode.js'
EXPORT = ROOT / 'data' / 'clode-web.json'
HISTORY = ROOT / 'data' / 'training-log.json'
OUT = ROOT / 'web' / 'clode-mini.html'


def main(out: Path = OUT) -> Path:
    html = TEMPLATE.read_text(encoding='utf-8')
    payload = EXPORT.read_text(encoding='utf-8')
    history = json.loads(HISTORY.read_text(encoding='utf-8')) if HISTORY.exists() else []
    trimmed = [{'step': h['step'], 'val_loss': round(h['val_loss'], 4)} for h in history]

    html = html.replace('/*__CLODE_JS__*/', MODEL_JS.read_text(encoding='utf-8'))
    html = html.replace('/*__PAYLOAD__*/', payload)
    html = html.replace('/*__HISTORY__*/', json.dumps(trimmed))

    for marker in ('/*__CLODE_JS__*/', '/*__PAYLOAD__*/', '/*__HISTORY__*/'):
        assert marker not in html, f'placeholder {marker} was not filled'

    out.write_text(html, encoding='utf-8')
    print(f'wrote {out} — {out.stat().st_size / 1e6:.2f} MB '
          f'({len(trimmed)} training points)')
    return out


if __name__ == '__main__':
    main()
