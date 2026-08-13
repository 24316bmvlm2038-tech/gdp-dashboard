/* Clode-mini inference in plain JavaScript.
 *
 * A port of clode/model.py's forward pass — the same transformer, the same
 * weights, running one token at a time against a KV cache. No dependencies,
 * no WebGL: the model is small enough that plain Float32Array maths is fast
 * enough to stream a reply.
 *
 * Loads in Node (module.exports) and in the browser (globalThis.Clode).
 */
(function (root) {
  'use strict';

  const SQRT_2_OVER_PI = 0.7978845608028654;
  const GELU_C = 0.044715;

  const SPECIALS = ['<|pad|>', '<|unk|>', '<|user|>', '<|assistant|>', '<|end|>'];
  const TOKEN_RE = /<\|[a-z]+\|>|[A-Za-z0-9_]+(?:['\-][A-Za-z0-9_]+)*|[^\sA-Za-z0-9_]/g;
  const NO_SPACE_BEFORE = new Set([',', '.', '!', '?', ';', ':', '%', ')', ']', '}']);
  const NO_SPACE_AFTER = new Set(['(', '[', '{', '$', '#', '@']);

  function b64ToBytes(b64) {
    if (typeof Buffer !== 'undefined') return new Uint8Array(Buffer.from(b64, 'base64'));
    const bin = atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  /** out[j] = bias[j] + sum_i x[i] * W[i * M + j]   (W is row-major [D, M]) */
  function matvec(out, x, W, bias, D, M) {
    if (bias) out.set(bias);
    else out.fill(0);
    for (let i = 0; i < D; i++) {
      const xi = x[i];
      if (xi === 0) continue;
      const base = i * M;
      for (let j = 0; j < M; j++) out[j] += xi * W[base + j];
    }
    return out;
  }

  function layernorm(out, x, g, b, D) {
    let mean = 0;
    for (let i = 0; i < D; i++) mean += x[i];
    mean /= D;
    let variance = 0;
    for (let i = 0; i < D; i++) { const d = x[i] - mean; variance += d * d; }
    variance /= D;
    const inv = 1 / Math.sqrt(variance + 1e-5);
    for (let i = 0; i < D; i++) out[i] = (x[i] - mean) * inv * g[i] + b[i];
    return out;
  }

  function gelu(v, n) {
    for (let i = 0; i < n; i++) {
      const x = v[i];
      v[i] = 0.5 * x * (1 + Math.tanh(SQRT_2_OVER_PI * (x + GELU_C * x * x * x)));
    }
    return v;
  }

  function softmaxInPlace(v, n) {
    let max = -Infinity;
    for (let i = 0; i < n; i++) if (v[i] > max) max = v[i];
    let sum = 0;
    for (let i = 0; i < n; i++) { v[i] = Math.exp(v[i] - max); sum += v[i]; }
    for (let i = 0; i < n; i++) v[i] /= sum;
    return v;
  }

  // ---- tokenizer --------------------------------------------------------

  class Tokenizer {
    constructor(itos) {
      this.itos = itos;
      this.stoi = new Map(itos.map((t, i) => [t, i]));
      this.unk = this.stoi.get('<|unk|>');
      this.user = this.stoi.get('<|user|>');
      this.assistant = this.stoi.get('<|assistant|>');
      this.end = this.stoi.get('<|end|>');
    }
    static split(text) { return text.match(TOKEN_RE) || []; }

    /** Token id, falling back across capitalisation before giving up.
     *
     * Must match Tokenizer.lookup in clode/tokenizer.py: the corpus writes
     * proper nouns capitalised ("Japan") and people type "japan", so without
     * this the name arrives as <|unk|> and the model has nothing to copy.
     */
    lookup(token) {
      const cap = token.charAt(0).toUpperCase() + token.slice(1).toLowerCase();
      const title = token.replace(/\w\S*/g, (w) =>
        w.charAt(0).toUpperCase() + w.slice(1).toLowerCase());
      for (const candidate of [token, cap, token.toLowerCase(), title, token.toUpperCase()]) {
        const id = this.stoi.get(candidate);
        if (id !== undefined) return id;
      }
      return this.unk;
    }

    encode(text) {
      return Tokenizer.split(text).map((t) => this.lookup(t));
    }
    join(tokens) {
      const out = [];
      for (const tok of tokens) {
        if (SPECIALS.includes(tok)) continue;
        if (!out.length) { out.push(tok); continue; }
        const prev = out[out.length - 1];
        if (NO_SPACE_BEFORE.has(tok) || NO_SPACE_AFTER.has(prev)) out.push(tok);
        else out.push(' ' + tok);
      }
      return out.join('').trim();
    }
    decode(ids) { return this.join(ids.map((i) => this.itos[i])); }
  }

  // ---- model ------------------------------------------------------------

  class Model {
    constructor(payload) {
      this.cfg = payload.config;
      this.tok = new Tokenizer(payload.vocab);
      this.params = {};

      const bytes = b64ToBytes(payload.weights_b64);
      for (const t of payload.tensors) {
        if (t.dtype === 'float32') {
          this.params[t.name] = new Float32Array(
            bytes.buffer.slice(bytes.byteOffset + t.offset,
                               bytes.byteOffset + t.offset + t.bytes));
        } else {
          // int8 values followed by one float32 scale per output column.
          const n = t.bytes;
          const q = new Int8Array(bytes.buffer, bytes.byteOffset + t.offset, n);
          const scales = new Float32Array(
            bytes.buffer.slice(bytes.byteOffset + t.offset + n,
                               bytes.byteOffset + t.offset + n + t.scale_bytes));
          const cols = t.shape[1];
          const w = new Float32Array(n);
          for (let i = 0; i < n; i++) w[i] = q[i] * scales[i % cols];
          this.params[t.name] = w;
        }
      }

      const D = this.cfg.n_embd;
      this.scratch = {
        x: new Float32Array(D),
        h: new Float32Array(D),
        qkv: new Float32Array(3 * D),
        att: new Float32Array(D),
        hidden: new Float32Array(4 * D),
        scores: new Float32Array(this.cfg.n_ctx),
        logits: new Float32Array(this.cfg.vocab_size),
      };
    }

    get nParams() {
      return Object.values(this.params).reduce((a, v) => a + v.length, 0);
    }

    newCache() {
      const { n_layer, n_ctx, n_embd } = this.cfg;
      const kv = [];
      for (let i = 0; i < n_layer; i++) {
        kv.push({ k: new Float32Array(n_ctx * n_embd),
                  v: new Float32Array(n_ctx * n_embd) });
      }
      return { kv, length: 0 };
    }

    /** One token through the network; returns logits (reused buffer). */
    step(token, pos, cache) {
      const p = this.params;
      const { n_embd: D, n_head: nh, n_layer: L, vocab_size: V } = this.cfg;
      const hd = D / nh;
      const scale = 1 / Math.sqrt(hd);
      const s = this.scratch;
      const t = cache.length;              // index this token will occupy

      for (let i = 0; i < D; i++) s.x[i] = p.wte[token * D + i] + p.wpe[pos * D + i];

      for (let l = 0; l < L; l++) {
        const layer = cache.kv[l];
        layernorm(s.h, s.x, p[`h${l}.ln1_g`], p[`h${l}.ln1_b`], D);
        matvec(s.qkv, s.h, p[`h${l}.w_qkv`], p[`h${l}.b_qkv`], D, 3 * D);

        for (let i = 0; i < D; i++) {
          layer.k[t * D + i] = s.qkv[D + i];
          layer.v[t * D + i] = s.qkv[2 * D + i];
        }

        for (let head = 0; head < nh; head++) {
          const off = head * hd;
          for (let u = 0; u <= t; u++) {
            let dot = 0;
            for (let d = 0; d < hd; d++) dot += s.qkv[off + d] * layer.k[u * D + off + d];
            s.scores[u] = dot * scale;
          }
          softmaxInPlace(s.scores, t + 1);
          for (let d = 0; d < hd; d++) {
            let acc = 0;
            for (let u = 0; u <= t; u++) acc += s.scores[u] * layer.v[u * D + off + d];
            s.att[off + d] = acc;
          }
        }

        matvec(s.h, s.att, p[`h${l}.w_attn_proj`], p[`h${l}.b_attn_proj`], D, D);
        for (let i = 0; i < D; i++) s.x[i] += s.h[i];

        layernorm(s.h, s.x, p[`h${l}.ln2_g`], p[`h${l}.ln2_b`], D);
        matvec(s.hidden, s.h, p[`h${l}.w_fc`], p[`h${l}.b_fc`], D, 4 * D);
        gelu(s.hidden, 4 * D);
        matvec(s.h, s.hidden, p[`h${l}.w_mlp_proj`], p[`h${l}.b_mlp_proj`], 4 * D, D);
        for (let i = 0; i < D; i++) s.x[i] += s.h[i];
      }

      layernorm(s.h, s.x, p.lnf_g, p.lnf_b, D);
      for (let v = 0; v < V; v++) {           // weight-tied output projection
        let acc = 0;
        const base = v * D;
        for (let i = 0; i < D; i++) acc += s.h[i] * p.wte[base + i];
        s.logits[v] = acc;
      }
      cache.length = t + 1;
      return s.logits;
    }

    prefill(ids) {
      const cache = this.newCache();
      let logits = null;
      for (let i = 0; i < ids.length; i++) logits = this.step(ids[i], i, cache);
      return { cache, logits };
    }

    sample(logits, recent, { temperature = 0.8, topP = 0.9, repetitionPenalty = 1.15 }) {
      const V = this.cfg.vocab_size;
      const row = Float64Array.from(logits.subarray(0, V));
      if (repetitionPenalty !== 1) {
        const penalty = Math.log(repetitionPenalty);
        for (const id of new Set(recent.slice(-48))) row[id] -= penalty;
      }
      if (temperature <= 0) {
        let best = 0;
        for (let i = 1; i < V; i++) if (row[i] > row[best]) best = i;
        return best;
      }
      for (let i = 0; i < V; i++) row[i] /= temperature;
      softmaxInPlace(row, V);

      const order = Array.from({ length: V }, (_, i) => i).sort((a, b) => row[b] - row[a]);
      let cum = 0, cut = V;
      for (let i = 0; i < V; i++) {
        cum += row[order[i]];
        if (cum >= topP) { cut = i + 1; break; }
      }
      let total = 0;
      for (let i = 0; i < cut; i++) total += row[order[i]];
      let r = Math.random() * total;
      for (let i = 0; i < cut; i++) {
        r -= row[order[i]];
        if (r <= 0) return order[i];
      }
      return order[0];
    }

    /** Yield reply token ids for a chat history of {role, content}. */
    *generate(history, options = {}) {
      const maxNew = options.maxNewTokens || 72;
      const ids = this.buildPrompt(history);
      let { cache, logits } = this.prefill(ids);
      const produced = [];
      for (let n = 0; n < maxNew; n++) {
        const next = this.sample(logits, ids.concat(produced), options);
        if (next === this.tok.end || next === this.tok.user || next === this.tok.assistant) return;
        produced.push(next);
        yield next;
        if (cache.length >= this.cfg.n_ctx) {
          const keep = ids.concat(produced).slice(-(this.cfg.n_ctx >> 1));
          ({ cache, logits } = this.prefill(keep));
        } else {
          logits = this.step(next, cache.length, cache);
        }
      }
    }

    buildPrompt(history) {
      const turns = history.map((m) => {
        const marker = m.role === 'user' ? this.tok.user : this.tok.assistant;
        const ids = [marker, ...this.tok.encode(m.content)];
        if (m.role === 'assistant') ids.push(this.tok.end);
        return ids;
      });
      let kept = [];
      const budget = this.cfg.n_ctx - 1;
      for (let i = turns.length - 1; i >= 0; i--) {
        if (kept.length + turns[i].length > budget) break;
        kept = turns[i].concat(kept);
      }
      return kept.concat([this.tok.assistant]).slice(-this.cfg.n_ctx);
    }
  }

  const api = { Model, Tokenizer };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  root.Clode = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
