# Curiosity Feed — Deployment Guide

## Live Preview

The Curiosity Feed application is ready to deploy. Choose your preferred deployment method:

### Option 1: Streamlit Cloud (Recommended)

1. **Sign up for Streamlit Cloud** at https://streamlit.io/cloud
2. **Connect your GitHub account** and authorize Streamlit
3. **Deploy the repository**:
   - Click "New app"
   - Select repository: `24316bmvlm2038-tech/gdp-dashboard`
   - Set main file path to: `streamlit_app.py`
   - Choose branch: `claude/curiosity-feed-app-8k01ih`
   - Click "Deploy"

4. **Your live app will be available** at: `https://<your-username>-<project-name>.streamlit.app`

### Option 2: Railway (With Custom Domain)

1. **Sign up for Railway** at https://railway.app
2. **Connect your GitHub account**
3. **Create new project** → Import from GitHub
4. **Select this repository** and branch `claude/curiosity-feed-app-8k01ih`
5. **Configure**:
   - Framework: Python
   - Build command: `pip install -r requirements.txt`
   - Start command: `streamlit run streamlit_app.py`
6. **Deploy** — Railway will provide your live URL

### Option 3: Local Development

```bash
# Clone the repository
git clone https://github.com/24316bmvlm2038-tech/gdp-dashboard
cd gdp-dashboard

# Check out the branch
git checkout claude/curiosity-feed-app-8k01ih

# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run streamlit_app.py
```

The app will be available at `http://localhost:8501`

## Configuration

### Environment Variables

Optional environment variables for enhanced features:

```bash
# OpenAI API key (for AI assistant features)
export OPENAI_API_KEY=sk-...

# For Supabase remote sync (optional)
export SUPABASE_URL=https://your-project.supabase.co
export SUPABASE_KEY=your-anon-key
```

### Data Storage

- **Local**: All user data is stored in `data/curiosity.json` (file-based)
- **Remote**: Optional Supabase integration for backup/sync

## Features Ready to Use

✅ Authentication (email/password with PBKDF2 hashing)
✅ TOTP Two-Factor Authentication
✅ Personalized Question Feed
✅ Gamification (XP, Levels, Achievements)
✅ Daily Rituals (10 daily slots)
✅ Social Features (Follows, Friends, Messaging, Profiles)
✅ Collections & Bookmarks
✅ AI Assistant (Explain, Teach, Debate modes)
✅ Advanced Search
✅ User Stats & Leaderboards
✅ Admin Dashboard
✅ Privacy Controls

## First-Time Setup

When you first deploy:

1. The app will create demo data automatically
2. Visit `/register` to create your first account
3. Complete the onboarding questionnaire
4. Start using the app!

## Troubleshooting

### "Module not found" errors
```bash
pip install -r requirements.txt
```

### Data not persisting
Ensure `data/` directory exists and is writable:
```bash
mkdir -p data
```

### Font rendering issues in share cards
The app will automatically detect and use available TrueType fonts on your system.

## Support

For issues or questions, refer to the codebase:
- `curiosity/` — Core application logic
- `curiosity/ui/` — UI components and pages
- `streamlit_app.py` — Main entry point

---

**Ready to deploy?** Choose your platform above and follow the steps!
