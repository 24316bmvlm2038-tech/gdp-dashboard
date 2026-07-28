# :zap: PulsePlay

A short-video feed **and** an AI chat assistant in one [Streamlit](https://streamlit.io) app —
a TikTok-style "For You" feed plus a modern AI chat where you can talk to
**Claude** or **GPT**.

## 🎬 For You feed

A phone-frame vertical video feed with real MP4 videos:

- **Snap scrolling** between full-screen videos — only the visible one autoplays
- **Sound toggle** (videos start muted so browser autoplay works)
- **Tap** to pause / play, **double-tap** to like with a heart-burst at your tap point
- Right-side action rail with SVG icons: like ❤️, comments 💬, favorites 🔖, share ↗
- **Comments drawer**, follow/unfollow with gradient avatar rings, spinning music
  disc with a marquee song title, per-video **progress bar**
- **Bottom nav bar** with an upload button — add your own video to the feed
- **Loading spinners** while videos buffer, and **automatic offline fallback**:
  if a remote clip can't load (blocked network, offline demo), the slide swaps
  to a locally generated animated clip in `assets/` so the feed never dies
- Likes, favorites, follows and comments persist in your browser (localStorage)

Remote clips are openly licensed sample videos (Blender Foundation shorts via
Google's public sample bucket). Fallback clips are generated in-repo.

## 💬 AI Chat

A polished chat with a conversation sidebar and custom avatars:

- **Claude** (`claude-opus-5`, Anthropic API) with:
  - 🌐 **Live web search** (server-side tool, on by default)
  - 🎚️ **Power slider** — Fast / Balanced / Max reasoning effort
  - 💭 **Show thinking** — stream Claude's reasoning summary live
  - 🖼️ **Image understanding** — attach images in the chat input
  - Server-side refusal fallback, with refusals surfaced gracefully
- **GPT** (`gpt-4o`, OpenAI API) with streaming and image understanding
- **Multiple conversations** with history, auto-titles and delete — persisted
  to `data/chats.json`
- **Smarter demo assistant** when no key is set: offline math (including
  "18% of 260"), time/date, coin flips, dice, jokes

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
