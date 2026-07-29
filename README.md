# ✳️ Clode

A Claude-style chat assistant, built with [Streamlit](https://streamlit.io) — with a
language model written and trained from scratch behind it.

## What this actually is

An exact copy of Claude is not something that can be built: the weights are private,
and training a model of that scale takes thousands of GPUs and months of compute.
So this project does the two honest halves of the request instead.

**1. The app is a faithful Claude-style chat client** — saved conversations, streaming
replies, model picker, effort control — that talks to the *real* Claude API when an
API key is present. That is the "as powerful as possible" path, and it is as powerful
as Claude because it *is* Claude.

**2. The model is real and really trained.** `Clode-mini` is a 3.5M-parameter
decoder-only transformer implemented from scratch in NumPy — embeddings, causal
multi-head self-attention, layer norm, GELU MLP, weight-tied output projection,
cross-entropy loss, **and the entire backward pass derived by hand**. No PyTorch, no
autograd. It was trained on this machine with AdamW, gradient clipping, and a cosine
schedule with warmup, and it answers in the app when no API key is configured.

| | Clode-mini (this repo) | A frontier model |
|---|---|---|
| Parameters | ~3.5 million | hundreds of billions |
| Training tokens | ~6 million | trillions |
| Training hardware | 4 CPU cores | large GPU clusters |
| Context window | 128 tokens | 1,000,000 tokens |

Clode-mini is a study model, not a competitor. It reliably learns the chat format,
its own persona, and the facts in its corpus; it is wrong about everything else, and
it says so when asked.

## Run it

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

Set `ANTHROPIC_API_KEY` to enable the Claude API backend. Without it, the app falls
back to the locally trained model, which needs no network access at all.

## Train the model yourself

```bash
python -m clode.corpus        # regenerate data/corpus.txt  (~430k tokens)
python -m clode.train --steps 2000
```

Training prints train/val loss and perplexity, writes a checkpoint to
`data/clode-mini.npz` every 200 steps, logs history to `data/training-log.json`,
and samples a few answers when it finishes. Roughly 2.5 s/step on 4 CPU cores.

## Is the maths right?

`tests/test_model.py` checks every hand-derived gradient against finite differences,
plus causal masking, save/load, and that the training loop can drive a batch to
near-zero loss:

```bash
python -m pytest tests -q
```

## Layout

| Path | What it is |
|---|---|
| `streamlit_app.py` | The chat UI |
| `clode/model.py` | The transformer: forward pass, hand-derived backward pass, AdamW, sampling |
| `clode/tokenizer.py` | Word-level tokenizer with chat control tokens |
| `clode/corpus.py` | Generates the training corpus from structured facts and templates |
| `clode/train.py` | Training loop — batching, cosine LR schedule, eval, checkpointing |
| `clode/backends.py` | The two chat backends (Claude API / local model) behind one interface |
| `tests/test_model.py` | Gradient checks and correctness tests |
