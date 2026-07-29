"""Correctness checks for the from-scratch transformer.

The important one is ``test_gradients_match_finite_differences``: every
gradient in ``Clode.backward`` is derived by hand, so it is verified against
numerically estimated gradients. If a derivation is wrong, training would
still "work" (the loss would just fall slower or plateau) — this is what
catches it.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clode.model import Adam, Clode, Config, gelu, gelu_backward, layernorm, layernorm_backward
from clode.tokenizer import Tokenizer


def _tiny_model(seed=0):
    cfg = Config(vocab_size=17, n_ctx=8, n_embd=16, n_head=2, n_layer=2)
    return Clode(cfg, seed=seed)


def _batch(cfg, rng, B=2, T=6):
    idx = rng.integers(0, cfg.vocab_size, size=(B, T))
    tgt = rng.integers(0, cfg.vocab_size, size=(B, T))
    return idx, tgt


def test_layernorm_backward():
    rng = np.random.default_rng(0)
    x = rng.normal(size=(3, 4, 5)).astype(np.float64)
    g = rng.normal(size=5)
    b = rng.normal(size=5)
    w = rng.normal(size=(3, 4, 5))  # arbitrary loss weights: L = sum(w * y)

    y, cache = layernorm(x, g, b)
    dx, dg, db = layernorm_backward(w, cache)

    eps = 1e-6
    num = np.zeros_like(x)
    for i in np.ndindex(x.shape):
        xp = x.copy(); xp[i] += eps
        xm = x.copy(); xm[i] -= eps
        num[i] = ((w * layernorm(xp, g, b)[0]).sum() - (w * layernorm(xm, g, b)[0]).sum()) / (2 * eps)
    assert np.allclose(dx, num, atol=1e-6), np.abs(dx - num).max()

    num_g = np.zeros_like(g)
    for i in range(g.size):
        gp = g.copy(); gp[i] += eps
        gm = g.copy(); gm[i] -= eps
        num_g[i] = ((w * layernorm(x, gp, b)[0]).sum() - (w * layernorm(x, gm, b)[0]).sum()) / (2 * eps)
    assert np.allclose(dg, num_g, atol=1e-6)
    assert np.allclose(db, w.reshape(-1, 5).sum(0), atol=1e-9)


def test_gelu_backward():
    x = np.linspace(-3, 3, 41)
    eps = 1e-6
    num = (gelu(x + eps) - gelu(x - eps)) / (2 * eps)
    assert np.allclose(gelu_backward(x, np.ones_like(x)), num, atol=1e-6)


def test_gradients_match_finite_differences():
    model = _tiny_model()
    # float64 keeps the finite-difference comparison meaningful.
    model.params = {k: v.astype(np.float64) for k, v in model.params.items()}
    rng = np.random.default_rng(3)
    idx, tgt = _batch(model.cfg, rng)

    loss, grads = model.loss_and_grads(idx, tgt)
    assert np.isfinite(loss)

    eps = 1e-5
    checked = 0
    for name, p in model.params.items():
        # Sample a few coordinates per tensor — checking all of them is slow
        # and adds nothing.
        flat = p.reshape(-1)
        picks = rng.choice(flat.size, size=min(4, flat.size), replace=False)
        for j in picks:
            orig = flat[j]
            flat[j] = orig + eps
            lp = model.forward(idx, tgt)[1]
            flat[j] = orig - eps
            lm = model.forward(idx, tgt)[1]
            flat[j] = orig
            numeric = (lp - lm) / (2 * eps)
            analytic = grads[name].reshape(-1)[j]
            denom = max(1.0, abs(numeric), abs(analytic))
            assert abs(numeric - analytic) / denom < 2e-4, (
                f'{name}[{j}]: analytic={analytic:.3e} numeric={numeric:.3e}')
            checked += 1
    assert checked > 40


def test_causal_masking():
    """Later tokens must not influence earlier positions' logits."""
    model = _tiny_model(seed=5)
    idx = np.array([[1, 2, 3, 4, 5, 6]])
    base = model.forward(idx)[0]
    changed = idx.copy()
    changed[0, -1] = 9
    other = model.forward(changed)[0]
    assert np.allclose(base[0, :-1], other[0, :-1], atol=1e-6)
    assert not np.allclose(base[0, -1], other[0, -1])


def test_overfits_a_single_batch():
    """A working forward+backward+optimizer loop can memorize one batch."""
    model = _tiny_model(seed=7)
    rng = np.random.default_rng(11)
    idx, tgt = _batch(model.cfg, rng, B=2, T=6)
    opt = Adam(model.params, lr=3e-3, weight_decay=0.0)
    first = model.forward(idx, tgt)[1]
    for _ in range(300):
        loss, grads = model.loss_and_grads(idx, tgt)
        opt.step(grads)
    assert loss < first * 0.1, (first, loss)
    assert loss < 0.1


def test_save_load_roundtrip(tmp_path):
    model = _tiny_model(seed=2)
    path = tmp_path / 'm.npz'
    model.save(path)
    back = Clode.load(path)
    assert back.cfg == model.cfg
    idx = np.array([[1, 2, 3]])
    assert np.allclose(model.forward(idx)[0], back.forward(idx)[0])


def _roomy_model(seed=9):
    """Same tiny model but with context to spare, so generation never wraps."""
    return Clode(Config(vocab_size=17, n_ctx=32, n_embd=16, n_head=2, n_layer=2),
                 seed=seed)


def test_decode_step_logits_equal_full_forward():
    """One cached step must produce the same logits as re-reading everything."""
    model = _roomy_model()
    prompt = [3, 1, 4, 1, 5]
    kv, _ = model._prefill(prompt)
    stepped = model._decode_step(7, len(prompt), kv)
    full = model.forward(np.array([prompt + [7]]))[0][0, -1]
    assert np.abs(stepped - full).max() < 1e-6


def test_kv_cache_matches_naive_decoding():
    """Incremental decoding is an optimisation, not a behaviour change."""
    model = _roomy_model()
    prompt = [3, 1, 4, 1, 5]
    cached = list(model.generate(prompt, max_new_tokens=20, temperature=0.0,
                                 repetition_penalty=1.1, use_cache=True))
    naive = list(model.generate(prompt, max_new_tokens=20, temperature=0.0,
                                repetition_penalty=1.1, use_cache=False))
    assert cached == naive, (cached, naive)

    # And with sampling, given the same random stream.
    a = list(model.generate(prompt, max_new_tokens=20, temperature=0.9,
                            rng=np.random.default_rng(4), use_cache=True))
    b = list(model.generate(prompt, max_new_tokens=20, temperature=0.9,
                            rng=np.random.default_rng(4), use_cache=False))
    assert a == b, (a, b)


def test_generation_past_the_context_window_keeps_going():
    """Past n_ctx the cache is rebuilt from recent tokens; output stays valid.

    The two paths deliberately diverge here — the cached path keeps the recent
    half of the window rather than re-reading a full context every step — so
    this checks liveness, not equality.
    """
    model = _tiny_model(seed=6)
    prompt = list(range(model.cfg.n_ctx - 2))
    out = list(model.generate(prompt, max_new_tokens=20, temperature=0.7,
                              rng=np.random.default_rng(1)))
    assert len(out) == 20
    assert all(0 <= t < model.cfg.vocab_size for t in out)


def test_generate_respects_stop_and_length():
    model = _tiny_model(seed=4)
    out = list(model.generate([1, 2], max_new_tokens=5, temperature=0.8,
                              rng=np.random.default_rng(0)))
    assert len(out) <= 5
    greedy = list(model.generate([1, 2], max_new_tokens=3, temperature=0.0))
    assert greedy == list(model.generate([1, 2], max_new_tokens=3, temperature=0.0))


def test_tokenizer_roundtrip():
    text = "<|user|> What's 2 + 2? <|assistant|> It's 4. <|end|>"
    tok = Tokenizer.train(text + ' ' + text, min_count=1)
    ids = tok.encode(text)
    assert tok.stoi["<|user|>"] in ids and tok.stoi['<|end|>'] in ids
    assert tok.decode(ids) == "What's 2 + 2? It's 4."


def test_unknown_words_map_to_unk():
    tok = Tokenizer.train('hello world hello world', min_count=1)
    ids = tok.encode('hello zzzz')
    assert ids[1] == tok.unk_id
