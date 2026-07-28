# :zap: PulsePlay

A short-video feed **and** an AI chat assistant in one [Streamlit](https://streamlit.io) app —
a TikTok-style "For You" feed plus a ChatGPT-style chat where you can talk to
**Claude** or **GPT**.

## 🎬 For You feed

A phone-frame vertical video feed:

- **Snap scrolling** between full-screen videos with autoplay (only the visible video plays)
- **Tap** to pause / play, **double-tap** to like with a heart burst ❤️
- **💬 Comments drawer** — post comments, saved in your browser (localStorage)
- **Follow / unfollow** creators from the avatar `+` button
- **↗️ Share** copies the video link
- **＋ Upload** your own video into the feed for the current session

Demo clips are openly licensed sample videos (Blender Foundation shorts via
Google's public sample bucket).

## 💬 AI Chat

A ChatGPT-style chat with a conversation sidebar:

- Switch between **Claude** (`claude-opus-5`, Anthropic API) and **GPT**
  (`gpt-4o`, OpenAI API) — streaming responses for both
- **Multiple conversations** with history, titles, and delete — persisted to
  `data/chats.json`
- **Demo assistant** answers when no API key is set, so the app always works
- Claude requests opt into Anthropic's server-side refusal fallback, and
  refusals are surfaced gracefully

### API keys

Add keys in the sidebar's **🔑 API keys** expander, or set them as environment
variables / Streamlit secrets:

```
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
```

## Run it locally

```
pip install -r requirements.txt
streamlit run streamlit_app.py
```
