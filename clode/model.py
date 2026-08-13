"""A decoder-only transformer written from scratch in NumPy.

Everything is here: embeddings, causal multi-head self-attention, layer
norm, a GELU MLP, weight-tied output projection, the cross-entropy loss and
the full backward pass. No autograd framework is involved — every gradient
below is derived by hand, which is why ``tests/test_model.py`` checks them
against finite differences.

Layout matches a small GPT: for each block,

    x = x + attn(ln1(x))
    x = x + mlp(ln2(x))

with pre-norm residuals and learned positional embeddings.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

import numpy as np

SQRT_2_OVER_PI = 0.7978845608028654
GELU_C = 0.044715


@dataclass
class Config:
    vocab_size: int
    n_ctx: int = 128
    n_embd: int = 256
    n_head: int = 4
    n_layer: int = 4

    @property
    def head_dim(self) -> int:
        return self.n_embd // self.n_head


# --------------------------------------------------------------------------
# primitives (forward + backward)
# --------------------------------------------------------------------------

def gelu(x: np.ndarray) -> np.ndarray:
    """tanh-approximation GELU.

    Written with in-place ufuncs rather than the obvious expression: this runs
    on arrays of several million floats every layer, so temporaries dominate
    the cost. (``x*x*x`` also avoids ``x**3``, whose float32 loop in NumPy is
    ~80x slower than repeated multiplication.)
    """
    t = x * x * x
    t *= GELU_C
    t += x
    t *= SQRT_2_OVER_PI
    np.tanh(t, out=t)
    t += 1.0
    t *= x
    t *= 0.5
    return t


def gelu_backward(x: np.ndarray, dy: np.ndarray) -> np.ndarray:
    x2 = x * x
    inner = x2 * GELU_C
    inner += 1.0
    inner *= x                       # x + C*x^3
    inner *= SQRT_2_OVER_PI
    tanh = np.tanh(inner, out=inner)

    x2 *= 3.0 * GELU_C               # dinner = sqrt(2/pi) * (1 + 3C x^2)
    x2 += 1.0
    x2 *= SQRT_2_OVER_PI

    sech2 = tanh * tanh              # 0.5 * x * (1 - tanh^2) * dinner
    np.subtract(1.0, sech2, out=sech2)
    sech2 *= x
    sech2 *= x2
    sech2 *= 0.5

    tanh += 1.0                      # 0.5 * (1 + tanh)
    tanh *= 0.5
    tanh += sech2
    tanh *= dy
    return tanh


def layernorm(x: np.ndarray, g: np.ndarray, b: np.ndarray, eps: float = 1e-5):
    mu = x.mean(-1, keepdims=True)
    xc = x - mu
    var = (xc * xc).mean(-1, keepdims=True)
    inv = 1.0 / np.sqrt(var + eps)
    xhat = xc * inv
    return g * xhat + b, (xhat, inv, g)


def layernorm_backward(dy: np.ndarray, cache):
    xhat, inv, g = cache
    dg = (dy * xhat).reshape(-1, xhat.shape[-1]).sum(0)
    db = dy.reshape(-1, xhat.shape[-1]).sum(0)
    dxhat = dy * g
    n = xhat.shape[-1]
    dx = inv * (dxhat - dxhat.mean(-1, keepdims=True)
                - xhat * (dxhat * xhat).mean(-1, keepdims=True))
    return dx, dg, db


def softmax(x: np.ndarray) -> np.ndarray:
    z = x - x.max(-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(-1, keepdims=True)


# --------------------------------------------------------------------------
# model
# --------------------------------------------------------------------------

class Clode:
    """The model. Parameters live in ``self.params`` as a flat name -> array dict."""

    def __init__(self, cfg: Config, seed: int = 1337, params: dict | None = None):
        self.cfg = cfg
        self.params = params if params is not None else self._init_params(seed)
        self._mask = np.tril(np.ones((cfg.n_ctx, cfg.n_ctx), dtype=bool))

    # -- parameters ------------------------------------------------------
    def _init_params(self, seed: int) -> dict:
        cfg = self.cfg
        rng = np.random.default_rng(seed)
        d = cfg.n_embd
        std = 0.02
        # Residual projections are scaled down so deep stacks start near identity.
        res_std = std / np.sqrt(2 * cfg.n_layer)

        p: dict[str, np.ndarray] = {
            'wte': rng.normal(0, std, (cfg.vocab_size, d)).astype(np.float32),
            'wpe': rng.normal(0, std, (cfg.n_ctx, d)).astype(np.float32),
        }
        for i in range(cfg.n_layer):
            p[f'h{i}.ln1_g'] = np.ones(d, dtype=np.float32)
            p[f'h{i}.ln1_b'] = np.zeros(d, dtype=np.float32)
            p[f'h{i}.w_qkv'] = rng.normal(0, std, (d, 3 * d)).astype(np.float32)
            p[f'h{i}.b_qkv'] = np.zeros(3 * d, dtype=np.float32)
            p[f'h{i}.w_attn_proj'] = rng.normal(0, res_std, (d, d)).astype(np.float32)
            p[f'h{i}.b_attn_proj'] = np.zeros(d, dtype=np.float32)
            p[f'h{i}.ln2_g'] = np.ones(d, dtype=np.float32)
            p[f'h{i}.ln2_b'] = np.zeros(d, dtype=np.float32)
            p[f'h{i}.w_fc'] = rng.normal(0, std, (d, 4 * d)).astype(np.float32)
            p[f'h{i}.b_fc'] = np.zeros(4 * d, dtype=np.float32)
            p[f'h{i}.w_mlp_proj'] = rng.normal(0, res_std, (4 * d, d)).astype(np.float32)
            p[f'h{i}.b_mlp_proj'] = np.zeros(d, dtype=np.float32)
        p['lnf_g'] = np.ones(d, dtype=np.float32)
        p['lnf_b'] = np.zeros(d, dtype=np.float32)
        return p

    @property
    def n_params(self) -> int:
        return sum(v.size for v in self.params.values())

    # -- forward ---------------------------------------------------------
    def forward(self, idx: np.ndarray, targets: np.ndarray | None = None,
                want_cache: bool = False):
        """``idx`` is ``[B, T]`` of token ids. Returns ``(logits, loss, cache)``."""
        cfg, p = self.cfg, self.params
        B, T = idx.shape
        if T > cfg.n_ctx:
            raise ValueError(f'sequence of {T} exceeds context {cfg.n_ctx}')
        nh, hd = cfg.n_head, cfg.head_dim
        scale = 1.0 / np.sqrt(hd)

        x = p['wte'][idx] + p['wpe'][:T]
        caches = []
        for i in range(cfg.n_layer):
            h, ln1_cache = layernorm(x, p[f'h{i}.ln1_g'], p[f'h{i}.ln1_b'])
            qkv = h @ p[f'h{i}.w_qkv'] + p[f'h{i}.b_qkv']            # [B,T,3D]
            q, k, v = np.split(qkv, 3, axis=-1)
            # [B,T,D] -> [B,nh,T,hd]
            q = q.reshape(B, T, nh, hd).transpose(0, 2, 1, 3)
            k = k.reshape(B, T, nh, hd).transpose(0, 2, 1, 3)
            v = v.reshape(B, T, nh, hd).transpose(0, 2, 1, 3)

            scores = (q @ k.transpose(0, 1, 3, 2)) * scale           # [B,nh,T,T]
            scores = np.where(self._mask[:T, :T], scores, -np.inf)
            att = softmax(scores)
            o = att @ v                                              # [B,nh,T,hd]
            o = o.transpose(0, 2, 1, 3).reshape(B, T, cfg.n_embd)
            a = o @ p[f'h{i}.w_attn_proj'] + p[f'h{i}.b_attn_proj']
            x_mid = x + a

            h2, ln2_cache = layernorm(x_mid, p[f'h{i}.ln2_g'], p[f'h{i}.ln2_b'])
            pre = h2 @ p[f'h{i}.w_fc'] + p[f'h{i}.b_fc']
            act = gelu(pre)
            m = act @ p[f'h{i}.w_mlp_proj'] + p[f'h{i}.b_mlp_proj']
            x = x_mid + m

            if want_cache:
                caches.append({
                    'ln1': ln1_cache, 'h1': h, 'q': q, 'k': k, 'v': v,
                    'att': att, 'o': o, 'x_mid': x_mid, 'ln2': ln2_cache, 'h2': h2,
                    'pre': pre, 'act': act,
                })

        xf, lnf_cache = layernorm(x, p['lnf_g'], p['lnf_b'])
        logits = xf @ p['wte'].T                                     # weight tying

        loss = None
        probs = None
        if targets is not None:
            probs = softmax(logits)
            flat = probs.reshape(-1, cfg.vocab_size)
            tgt = targets.reshape(-1)
            keep = tgt >= 0
            n = max(int(keep.sum()), 1)
            loss = float(-np.log(np.maximum(flat[np.arange(flat.shape[0]), tgt.clip(min=0)],
                                            1e-12))[keep].sum() / n)

        cache = None
        if want_cache:
            cache = {'idx': idx, 'caches': caches, 'xf': xf, 'lnf': lnf_cache,
                     'logits': logits, 'probs': probs}
        return logits, loss, cache

    # -- backward --------------------------------------------------------
    def backward(self, cache: dict, targets: np.ndarray) -> dict:
        """Gradients of the mean cross-entropy loss w.r.t. every parameter."""
        cfg, p = self.cfg, self.params
        idx = cache['idx']
        B, T = idx.shape
        nh, hd, D = cfg.n_head, cfg.head_dim, cfg.n_embd
        scale = 1.0 / np.sqrt(hd)
        grads = {k: np.zeros_like(v) for k, v in p.items()}

        # cross entropy -> logits
        probs = cache.get('probs')
        if probs is None:
            probs = softmax(cache['logits'])
        tgt = targets.reshape(-1)
        keep = tgt >= 0
        n = max(int(keep.sum()), 1)
        dlogits = probs.reshape(-1, cfg.vocab_size).copy()
        dlogits[np.arange(dlogits.shape[0]), tgt.clip(min=0)] -= 1.0
        dlogits[~keep] = 0.0
        dlogits /= n
        dlogits = dlogits.reshape(B, T, cfg.vocab_size)

        # logits = xf @ wte.T
        xf = cache['xf']
        grads['wte'] += dlogits.reshape(-1, cfg.vocab_size).T @ xf.reshape(-1, D)
        dxf = dlogits @ p['wte']

        dx, dg, db = layernorm_backward(dxf, cache['lnf'])
        grads['lnf_g'] += dg
        grads['lnf_b'] += db

        for i in reversed(range(cfg.n_layer)):
            c = cache['caches'][i]

            # --- MLP branch: x = x_mid + m
            dm = dx
            grads[f'h{i}.w_mlp_proj'] += c['act'].reshape(-1, 4 * D).T @ dm.reshape(-1, D)
            grads[f'h{i}.b_mlp_proj'] += dm.reshape(-1, D).sum(0)
            dact = dm @ p[f'h{i}.w_mlp_proj'].T
            dpre = gelu_backward(c['pre'], dact)
            grads[f'h{i}.w_fc'] += c['h2'].reshape(-1, D).T @ dpre.reshape(-1, 4 * D)
            grads[f'h{i}.b_fc'] += dpre.reshape(-1, 4 * D).sum(0)
            dh2 = dpre @ p[f'h{i}.w_fc'].T
            dln2, dg2, db2 = layernorm_backward(dh2, c['ln2'])
            grads[f'h{i}.ln2_g'] += dg2
            grads[f'h{i}.ln2_b'] += db2
            dx_mid = dx + dln2

            # --- attention branch: x_mid = x + a
            da = dx_mid
            grads[f'h{i}.w_attn_proj'] += c['o'].reshape(-1, D).T @ da.reshape(-1, D)
            grads[f'h{i}.b_attn_proj'] += da.reshape(-1, D).sum(0)
            do = da @ p[f'h{i}.w_attn_proj'].T                        # [B,T,D]
            do = do.reshape(B, T, nh, hd).transpose(0, 2, 1, 3)       # [B,nh,T,hd]

            att, q, k, v = c['att'], c['q'], c['k'], c['v']
            datt = do @ v.transpose(0, 1, 3, 2)                       # [B,nh,T,T]
            dv = att.transpose(0, 1, 3, 2) @ do
            dscores = att * (datt - (datt * att).sum(-1, keepdims=True))
            dscores *= scale
            dq = dscores @ k
            dk = dscores.transpose(0, 1, 3, 2) @ q

            def merge(t):
                return t.transpose(0, 2, 1, 3).reshape(B, T, D)

            dqkv = np.concatenate([merge(dq), merge(dk), merge(dv)], axis=-1)
            grads[f'h{i}.w_qkv'] += c['h1'].reshape(-1, D).T @ dqkv.reshape(-1, 3 * D)
            grads[f'h{i}.b_qkv'] += dqkv.reshape(-1, 3 * D).sum(0)
            dh1 = dqkv @ p[f'h{i}.w_qkv'].T
            dln1, dg1, db1 = layernorm_backward(dh1, c['ln1'])
            grads[f'h{i}.ln1_g'] += dg1
            grads[f'h{i}.ln1_b'] += db1
            dx = dx_mid + dln1

        # embeddings
        grads['wpe'][:T] += dx.sum(0)
        np.add.at(grads['wte'], idx.reshape(-1), dx.reshape(-1, D))
        return grads

    def loss_and_grads(self, idx: np.ndarray, targets: np.ndarray):
        _, loss, cache = self.forward(idx, targets, want_cache=True)
        return loss, self.backward(cache, targets)

    # -- generation ------------------------------------------------------
    def _prefill(self, ids: list[int]):
        """Run the prompt once, keeping each layer's keys and values."""
        _, _, cache = self.forward(np.array([ids], dtype=np.int64), want_cache=True)
        kv = [(c['k'], c['v']) for c in cache['caches']]
        return kv, cache['logits'][0, -1]

    def _decode_step(self, token: int, pos: int, kv: list):
        """One token through the network, attending to the cached past.

        This is the same computation as :meth:`forward` restricted to a single
        position: because the keys and values of every earlier token are
        already cached, no causal mask is needed — the cache only ever holds
        the past and the current step.
        """
        cfg, p = self.cfg, self.params
        nh, hd, D = cfg.n_head, cfg.head_dim, cfg.n_embd
        scale = 1.0 / np.sqrt(hd)

        x = (p['wte'][token] + p['wpe'][pos]).reshape(1, 1, D)
        for i in range(cfg.n_layer):
            h, _ = layernorm(x, p[f'h{i}.ln1_g'], p[f'h{i}.ln1_b'])
            qkv = h @ p[f'h{i}.w_qkv'] + p[f'h{i}.b_qkv']
            q, k, v = np.split(qkv, 3, axis=-1)
            q = q.reshape(1, 1, nh, hd).transpose(0, 2, 1, 3)
            k = k.reshape(1, 1, nh, hd).transpose(0, 2, 1, 3)
            v = v.reshape(1, 1, nh, hd).transpose(0, 2, 1, 3)

            K = np.concatenate([kv[i][0], k], axis=2)
            V = np.concatenate([kv[i][1], v], axis=2)
            kv[i] = (K, V)

            att = softmax((q @ K.transpose(0, 1, 3, 2)) * scale)
            o = (att @ V).transpose(0, 2, 1, 3).reshape(1, 1, D)
            x = x + o @ p[f'h{i}.w_attn_proj'] + p[f'h{i}.b_attn_proj']

            h2, _ = layernorm(x, p[f'h{i}.ln2_g'], p[f'h{i}.ln2_b'])
            act = gelu(h2 @ p[f'h{i}.w_fc'] + p[f'h{i}.b_fc'])
            x = x + act @ p[f'h{i}.w_mlp_proj'] + p[f'h{i}.b_mlp_proj']

        xf, _ = layernorm(x, p['lnf_g'], p['lnf_b'])
        return (xf @ p['wte'].T)[0, 0]

    def _sample(self, row: np.ndarray, ids: list[int], temperature: float,
                top_p: float, repetition_penalty: float,
                rng: np.random.Generator) -> int:
        row = row.astype(np.float64)
        if repetition_penalty and repetition_penalty != 1.0:
            for t in set(ids[-48:]):
                row[t] -= np.log(repetition_penalty)
        if temperature <= 0:
            return int(row.argmax())
        probs = softmax(row / temperature)
        if 0 < top_p < 1:
            order = np.argsort(-probs)
            csum = np.cumsum(probs[order])
            cut = int(np.searchsorted(csum, top_p)) + 1
            mask = np.zeros_like(probs, dtype=bool)
            mask[order[:cut]] = True
            probs = np.where(mask, probs, 0.0)
            probs /= probs.sum()
        return int(rng.choice(len(probs), p=probs))

    def generate(self, prompt_ids: list[int], max_new_tokens: int = 96,
                 temperature: float = 0.9, top_p: float = 0.92,
                 repetition_penalty: float = 1.12, stop_ids: tuple[int, ...] = (),
                 rng: np.random.Generator | None = None,
                 use_cache: bool = True):
        """Yield sampled token ids one at a time.

        With ``use_cache`` (the default) each new token costs one position of
        work instead of a full re-read of the context, which is what makes
        interactive use bearable on a CPU. ``use_cache=False`` is the naive
        recompute-everything path, kept because the two must agree.
        """
        rng = rng or np.random.default_rng()
        ids = list(prompt_ids)[-self.cfg.n_ctx:]

        if use_cache:
            kv, row = self._prefill(ids)
            for _ in range(max_new_tokens):
                nxt = self._sample(row, ids, temperature, top_p, repetition_penalty, rng)
                if nxt in stop_ids:
                    return
                ids.append(nxt)
                yield nxt
                if len(ids) >= self.cfg.n_ctx:
                    # Context is full: keep the recent half and rebuild the cache.
                    ids = ids[-(self.cfg.n_ctx // 2):]
                    kv, row = self._prefill(ids)
                else:
                    row = self._decode_step(nxt, len(ids) - 1, kv)
            return

        for _ in range(max_new_tokens):
            window = ids[-self.cfg.n_ctx:]
            logits, _, _ = self.forward(np.array([window], dtype=np.int64))
            nxt = self._sample(logits[0, -1], ids, temperature, top_p,
                               repetition_penalty, rng)
            if nxt in stop_ids:
                return
            ids.append(nxt)
            yield nxt

    # -- persistence -----------------------------------------------------
    def save(self, path: str | Path) -> None:
        np.savez_compressed(
            path,
            **self.params,
            **{f'__cfg_{k}': np.array(v) for k, v in asdict(self.cfg).items()},
        )

    @classmethod
    def load(cls, path: str | Path) -> 'Clode':
        z = np.load(path, allow_pickle=False)
        cfg = Config(**{k[len('__cfg_'):]: int(z[k]) for k in z.files if k.startswith('__cfg_')})
        params = {k: z[k] for k in z.files if not k.startswith('__cfg_')}
        return cls(cfg, params=params)


# --------------------------------------------------------------------------
# optimizer
# --------------------------------------------------------------------------

class Adam:
    """AdamW with decoupled weight decay and global-norm gradient clipping."""

    def __init__(self, params: dict, lr: float = 3e-4, betas=(0.9, 0.95),
                 eps: float = 1e-8, weight_decay: float = 0.01):
        self.params = params
        self.lr = lr
        self.b1, self.b2 = betas
        self.eps = eps
        self.wd = weight_decay
        self.t = 0
        self.m = {k: np.zeros_like(v) for k, v in params.items()}
        self.v = {k: np.zeros_like(v) for k, v in params.items()}

    def step(self, grads: dict, lr: float | None = None, clip: float = 1.0) -> float:
        lr = self.lr if lr is None else lr
        total = np.sqrt(sum(float((g.astype(np.float64) ** 2).sum()) for g in grads.values()))
        factor = min(1.0, clip / (total + 1e-6)) if clip else 1.0
        self.t += 1
        bc1 = 1 - self.b1 ** self.t
        bc2 = 1 - self.b2 ** self.t
        for k, p in self.params.items():
            g = grads[k] * factor
            self.m[k] = self.b1 * self.m[k] + (1 - self.b1) * g
            self.v[k] = self.b2 * self.v[k] + (1 - self.b2) * (g * g)
            mhat = self.m[k] / bc1
            vhat = self.v[k] / bc2
            update = mhat / (np.sqrt(vhat) + self.eps)
            # Weight decay applies to matrices only, not gains/biases.
            if self.wd and p.ndim > 1:
                update = update + self.wd * p
            p -= (lr * update).astype(p.dtype)
        return total
