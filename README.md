# :camera_with_flash: PhotoShare

A photo sharing gallery app built with [Streamlit](https://streamlit.io).

## Features

**Community Feed** — browse photos that people publish online:
- ❤️ Like and 💔 dislike photos (vote again to withdraw, or switch your vote)
- 💬 Comment on any photo
- ➕ Follow / unfollow photographers, and filter the feed to only people you follow

**My Gallery** — your private area with all of your photos:
- ⬆️ Upload photos (png / jpg / gif / webp)
- ❤️ Like, 🔖 Mark and 📌 Keep photos — kept photos are protected from removal
- 🗑️ Remove photos (deletes the image and takes it off the feed if published)
- 🌍 Publish photos to the Community Feed, or unpublish them again
- Filter your gallery by Liked / Marked / Kept / Published

**People** — see every photographer, their stats, and follow them from one place.

Every action is persisted to `data/photoshare.json` (and uploads to
`data/uploads/`), so your gallery actually changes and survives restarts.

## Run it locally

```
pip install -r requirements.txt
streamlit run streamlit_app.py
```
