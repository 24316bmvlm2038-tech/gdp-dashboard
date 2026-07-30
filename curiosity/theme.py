"""Design system for Curiosity Feed.

Everything visual lives here: colour tokens, typography, the glass card
language, motion curves and the floating navigation. The CSS is injected once
per rerun by :func:`inject`, and adapts to the user's theme, font size and
reduced-motion preferences.
"""

from __future__ import annotations

import streamlit as st

PRIMARY = '#2563EB'
ACCENT = '#7C3AED'
SUCCESS = '#22C55E'
WARNING = '#F59E0B'
ERROR = '#EF4444'
BG_LIGHT = '#F8FAFC'
BG_DARK = '#09090B'

FONT_SCALE = {'Small': 0.92, 'Default': 1.0, 'Large': 1.1, 'Extra large': 1.22}

# Gradient pairs used by card types and share cards. Keeping them in one place
# means the exported PNG and the on-screen card always agree.
GRADIENTS = {
    'indigo': ('#4F46E5', '#7C3AED'),
    'ocean': ('#0EA5E9', '#2563EB'),
    'sunset': ('#F97316', '#EF4444'),
    'forest': ('#10B981', '#059669'),
    'gold': ('#F59E0B', '#F97316'),
    'plum': ('#A855F7', '#EC4899'),
    'slate': ('#334155', '#0F172A'),
    'aurora': ('#06B6D4', '#8B5CF6'),
}


def gradient_for(name: str) -> tuple[str, str]:
    return GRADIENTS.get(name, GRADIENTS['indigo'])


def _css(dark: bool, scale: float, motion: bool) -> str:
    if dark:
        tokens = """
            --bg: #09090B;
            --bg-2: #0F1117;
            --surface: rgba(255,255,255,.055);
            --surface-2: rgba(255,255,255,.085);
            --border: rgba(255,255,255,.10);
            --border-strong: rgba(255,255,255,.18);
            --text: #F4F4F5;
            --text-2: #A1A1AA;
            --text-3: #71717A;
            --shadow: 0 18px 48px rgba(0,0,0,.55);
            --shadow-sm: 0 6px 18px rgba(0,0,0,.40);
            --glow: 0 0 0 1px rgba(255,255,255,.06);
            --nav-bg: rgba(18,18,22,.72);
        """
        mesh = """
            radial-gradient(1200px 700px at 12% -8%, rgba(37,99,235,.28), transparent 60%),
            radial-gradient(1000px 620px at 92% 4%, rgba(124,58,237,.24), transparent 62%),
            radial-gradient(900px 700px at 50% 108%, rgba(14,165,233,.16), transparent 60%),
            linear-gradient(180deg, #09090B 0%, #0B0B11 55%, #09090B 100%)
        """
    else:
        tokens = """
            --bg: #F8FAFC;
            --bg-2: #FFFFFF;
            --surface: rgba(255,255,255,.72);
            --surface-2: rgba(255,255,255,.92);
            --border: rgba(15,23,42,.08);
            --border-strong: rgba(15,23,42,.14);
            --text: #0F172A;
            --text-2: #475569;
            --text-3: #94A3B8;
            --shadow: 0 20px 50px rgba(15,23,42,.10);
            --shadow-sm: 0 6px 20px rgba(15,23,42,.07);
            --glow: 0 0 0 1px rgba(15,23,42,.03);
            --nav-bg: rgba(255,255,255,.74);
        """
        mesh = """
            radial-gradient(1200px 700px at 10% -10%, rgba(37,99,235,.16), transparent 60%),
            radial-gradient(1000px 620px at 95% 0%, rgba(124,58,237,.14), transparent 62%),
            radial-gradient(900px 700px at 50% 110%, rgba(34,197,94,.10), transparent 60%),
            linear-gradient(180deg, #F8FAFC 0%, #FFFFFF 60%, #F5F7FB 100%)
        """

    anim = '' if motion else """
        *, *::before, *::after {
            animation-duration: .001ms !important;
            transition-duration: .001ms !important;
        }
    """

    return f"""
    <style>
    :root {{
        {tokens}
        --primary: {PRIMARY};
        --accent: {ACCENT};
        --success: {SUCCESS};
        --warning: {WARNING};
        --error: {ERROR};
        --r-sm: 12px;
        --r-md: 18px;
        --r-lg: 26px;
        --r-xl: 34px;
        --ease: cubic-bezier(.22,1,.36,1);
        --ease-soft: cubic-bezier(.4,0,.2,1);
        --fs: {scale};
    }}

    html, body, [class*="st-"], button, input, textarea, select {{
        font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display",
            "SF Pro Text", "Segoe UI", Inter, system-ui, sans-serif !important;
        -webkit-font-smoothing: antialiased;
        -moz-osx-font-smoothing: grayscale;
    }}

    .stApp {{
        background: {mesh};
        background-attachment: fixed;
        color: var(--text);
        font-size: calc(16px * var(--fs));
    }}
    .stAppHeader, header[data-testid="stHeader"] {{ background: transparent; }}
    #MainMenu, footer {{ visibility: hidden; }}
    .block-container {{
        padding-top: 1.1rem !important;
        padding-bottom: 7.5rem !important;
        max-width: 1120px;
    }}

    /* ---------- typography ---------- */
    h1, h2, h3, h4 {{ color: var(--text); letter-spacing: -.022em; }}
    h1 {{ font-size: calc(2.5rem * var(--fs)); font-weight: 800; line-height: 1.06; }}
    h2 {{ font-size: calc(1.55rem * var(--fs)); font-weight: 750; }}
    h3 {{ font-size: calc(1.18rem * var(--fs)); font-weight: 700; }}
    p, li, label, .stMarkdown {{ color: var(--text-2); line-height: 1.62; }}

    .cf-display {{
        font-size: calc(2.9rem * var(--fs));
        font-weight: 820;
        letter-spacing: -.035em;
        line-height: 1.02;
        background: linear-gradient(115deg, var(--text) 25%, var(--primary) 78%, var(--accent) 100%);
        -webkit-background-clip: text; background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: .1rem 0 .35rem;
    }}
    .cf-sub {{ color: var(--text-2); font-size: calc(1.02rem * var(--fs)); margin-bottom: .2rem; }}
    .cf-eyebrow {{
        text-transform: uppercase; letter-spacing: .14em;
        font-size: calc(.68rem * var(--fs)); font-weight: 700; color: var(--text-3);
    }}

    /* ---------- glass surfaces ---------- */
    .cf-card, .cf-panel {{
        position: relative;
        background: var(--surface);
        backdrop-filter: blur(26px) saturate(180%);
        -webkit-backdrop-filter: blur(26px) saturate(180%);
        border: 1px solid var(--border);
        border-radius: var(--r-lg);
        box-shadow: var(--shadow), var(--glow);
        padding: 1.35rem 1.45rem;
        transition: transform .5s var(--ease), box-shadow .5s var(--ease),
                    border-color .5s var(--ease);
        overflow: hidden;
    }}
    .cf-card::before {{
        content: ""; position: absolute; inset: 0 0 auto 0; height: 1px;
        background: linear-gradient(90deg, transparent, rgba(255,255,255,.55), transparent);
        opacity: .7;
    }}
    .cf-card:hover {{
        transform: translateY(-3px);
        border-color: var(--border-strong);
        box-shadow: 0 26px 60px rgba(37,99,235,.16), var(--glow);
    }}
    .cf-panel {{ padding: 1.1rem 1.2rem; border-radius: var(--r-md); }}
    .cf-flat {{ box-shadow: var(--shadow-sm); }}

    .cf-card .cf-aura {{
        position: absolute; width: 320px; height: 320px; border-radius: 50%;
        filter: blur(70px); opacity: .30; top: -150px; right: -110px;
        pointer-events: none;
    }}

    /* ---------- pills, chips, badges ---------- */
    .cf-chip {{
        display: inline-flex; align-items: center; gap: .38rem;
        padding: .3rem .72rem; border-radius: 999px;
        font-size: calc(.74rem * var(--fs)); font-weight: 650;
        background: var(--surface-2); border: 1px solid var(--border);
        color: var(--text-2); white-space: nowrap;
    }}
    .cf-chip-grad {{
        color: #fff; border: none;
        box-shadow: 0 6px 18px rgba(37,99,235,.28);
    }}
    .cf-badge {{
        display:inline-flex; align-items:center; gap:.3rem;
        font-size: calc(.7rem * var(--fs)); font-weight: 700;
        padding: .18rem .5rem; border-radius: 8px;
        background: rgba(37,99,235,.12); color: var(--primary);
    }}
    .cf-dot {{ width:7px; height:7px; border-radius:50%; display:inline-block; }}

    /* ---------- card content ---------- */
    .cf-q {{
        font-size: calc(1.42rem * var(--fs)); font-weight: 760;
        letter-spacing: -.024em; line-height: 1.24; color: var(--text);
        margin: .55rem 0 .5rem;
    }}
    .cf-body {{ color: var(--text-2); font-size: calc(.98rem * var(--fs)); line-height: 1.66; }}
    .cf-meta {{ color: var(--text-3); font-size: calc(.78rem * var(--fs)); }}

    /* ---------- results bars ---------- */
    .cf-bar {{
        position: relative; height: 40px; border-radius: 12px;
        background: var(--surface-2); border: 1px solid var(--border);
        overflow: hidden; margin-bottom: .5rem;
        display: flex; align-items: center;
    }}
    .cf-bar-fill {{
        position: absolute; inset: 0 auto 0 0;
        background: linear-gradient(90deg, rgba(37,99,235,.30), rgba(124,58,237,.30));
        animation: cf-grow .9s var(--ease) both;
    }}
    .cf-bar-mine .cf-bar-fill {{
        background: linear-gradient(90deg, rgba(37,99,235,.62), rgba(124,58,237,.62));
    }}
    .cf-bar-label {{
        position: relative; z-index: 1; display: flex; justify-content: space-between;
        width: 100%; padding: 0 .85rem; font-size: calc(.87rem * var(--fs));
        font-weight: 620; color: var(--text);
    }}
    @keyframes cf-grow {{ from {{ transform: scaleX(0); transform-origin: left; }} }}

    /* ---------- entrance motion ---------- */
    @keyframes cf-in {{
        from {{ opacity: 0; transform: translateY(16px) scale(.985); }}
        to {{ opacity: 1; transform: none; }}
    }}
    .cf-in {{ animation: cf-in .62s var(--ease) both; }}
    .cf-d1 {{ animation-delay: .05s; }} .cf-d2 {{ animation-delay: .10s; }}
    .cf-d3 {{ animation-delay: .15s; }} .cf-d4 {{ animation-delay: .20s; }}
    .cf-d5 {{ animation-delay: .25s; }} .cf-d6 {{ animation-delay: .30s; }}

    /* ---------- streamlit controls ---------- */
    .stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
        border-radius: 14px !important;
        border: 1px solid var(--border) !important;
        background: var(--surface-2) !important;
        color: var(--text) !important;
        font-weight: 620 !important;
        padding: .5rem .95rem !important;
        transition: transform .28s var(--ease), box-shadow .28s var(--ease),
                    background .28s var(--ease), border-color .28s var(--ease) !important;
        backdrop-filter: blur(14px);
    }}
    .stButton > button:hover, .stDownloadButton > button:hover,
    .stFormSubmitButton > button:hover {{
        transform: translateY(-2px);
        border-color: var(--border-strong) !important;
        box-shadow: 0 10px 26px rgba(37,99,235,.18) !important;
        color: var(--text) !important;
    }}
    .stButton > button:active {{ transform: translateY(0) scale(.985); }}
    .stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
        background: linear-gradient(120deg, var(--primary), var(--accent)) !important;
        color: #fff !important; border: none !important;
        box-shadow: 0 12px 30px rgba(37,99,235,.34) !important;
    }}
    .stButton > button[kind="primary"]:hover {{ box-shadow: 0 16px 38px rgba(124,58,237,.42) !important; }}

    .stTextInput input, .stTextArea textarea, .stNumberInput input,
    .stDateInput input, .stChatInput textarea {{
        border-radius: 14px !important;
        background: var(--surface-2) !important;
        border: 1px solid var(--border) !important;
        color: var(--text) !important;
    }}
    .stTextInput input:focus, .stTextArea textarea:focus {{
        border-color: var(--primary) !important;
        box-shadow: 0 0 0 4px rgba(37,99,235,.16) !important;
    }}
    div[data-baseweb="select"] > div {{
        border-radius: 14px !important; background: var(--surface-2) !important;
        border-color: var(--border) !important;
    }}
    .stTabs [data-baseweb="tab-list"] {{
        gap: .25rem; background: var(--surface); padding: .3rem;
        border-radius: 16px; border: 1px solid var(--border);
        backdrop-filter: blur(18px);
    }}
    .stTabs [data-baseweb="tab"] {{
        border-radius: 12px; padding: .35rem .85rem; font-weight: 620;
        color: var(--text-2);
    }}
    .stTabs [aria-selected="true"] {{
        background: linear-gradient(120deg, var(--primary), var(--accent));
        color: #fff !important;
    }}
    .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none; }}
    .stProgress > div > div > div > div {{
        background: linear-gradient(90deg, var(--primary), var(--accent));
    }}
    .stExpander {{
        border-radius: var(--r-md) !important; border: 1px solid var(--border) !important;
        background: var(--surface) !important; backdrop-filter: blur(18px);
    }}
    div[data-testid="stMetric"] {{
        background: var(--surface); border: 1px solid var(--border);
        border-radius: var(--r-md); padding: .85rem 1rem;
        backdrop-filter: blur(18px); box-shadow: var(--shadow-sm);
    }}
    div[data-testid="stMetricValue"] {{ font-weight: 780; letter-spacing: -.02em; }}
    hr {{ border-color: var(--border); }}
    ::-webkit-scrollbar {{ width: 10px; height: 10px; }}
    ::-webkit-scrollbar-thumb {{ background: var(--border-strong); border-radius: 999px; }}
    ::-webkit-scrollbar-track {{ background: transparent; }}

    /* ---------- containers that behave like glass cards ---------- */
    div[class*="st-key-cardbox_"], div[class*="st-key-panelbox_"] {{
        position: relative;
        background: var(--surface);
        backdrop-filter: blur(26px) saturate(180%);
        -webkit-backdrop-filter: blur(26px) saturate(180%);
        border: 1px solid var(--border);
        border-radius: var(--r-lg);
        box-shadow: var(--shadow), var(--glow);
        padding: 1.25rem 1.35rem !important;
        margin-bottom: 1.05rem;
        transition: transform .5s var(--ease), box-shadow .5s var(--ease),
                    border-color .5s var(--ease);
        animation: cf-in .6s var(--ease) both;
        overflow: hidden;
    }}
    div[class*="st-key-cardbox_"]:hover {{
        transform: translateY(-3px);
        border-color: var(--border-strong);
        box-shadow: 0 26px 60px rgba(37,99,235,.15), var(--glow);
    }}
    div[class*="st-key-panelbox_"] {{ border-radius: var(--r-md); padding: 1rem 1.15rem !important; }}
    div[class*="st-key-cardbox_"] .stButton > button {{ font-size: calc(.86rem * var(--fs)) !important; }}

    /* ---------- floating navigation ---------- */
    .st-key-cf_nav {{
        position: sticky; bottom: 14px; z-index: 90;
        background: var(--nav-bg);
        backdrop-filter: blur(28px) saturate(180%);
        -webkit-backdrop-filter: blur(28px) saturate(180%);
        border: 1px solid var(--border-strong);
        border-radius: 22px;
        box-shadow: var(--shadow);
        padding: .4rem .5rem !important;
        margin-top: 1.4rem;
    }}
    .st-key-cf_nav .stButton > button {{
        background: transparent !important; border: none !important;
        color: var(--text-2) !important; font-size: calc(.74rem * var(--fs)) !important;
        padding: .35rem .1rem !important; width: 100%;
    }}
    .st-key-cf_nav .stButton > button:hover {{
        background: var(--surface-2) !important; box-shadow: none !important;
        transform: translateY(-2px);
    }}
    .st-key-cf_nav .stButton > button[kind="primary"] {{
        background: linear-gradient(120deg, var(--primary), var(--accent)) !important;
        color: #fff !important; box-shadow: 0 8px 22px rgba(37,99,235,.35) !important;
    }}

    /* ---------- top bar ---------- */
    .cf-topbar {{
        display: flex; align-items: center; justify-content: space-between;
        gap: .8rem; padding: .55rem .9rem; margin-bottom: 1rem;
        background: var(--surface); border: 1px solid var(--border);
        border-radius: 18px; backdrop-filter: blur(24px);
        box-shadow: var(--shadow-sm);
    }}
    .cf-brand {{ display:flex; align-items:center; gap:.6rem; font-weight:780;
        letter-spacing:-.02em; color: var(--text); font-size: calc(1.02rem * var(--fs)); }}
    .cf-orb {{
        width: 30px; height: 30px; border-radius: 11px;
        background: linear-gradient(135deg, var(--primary), var(--accent));
        box-shadow: 0 8px 20px rgba(37,99,235,.42);
        display:flex; align-items:center; justify-content:center; color:#fff;
        font-size: 15px; animation: cf-float 6s ease-in-out infinite;
    }}
    @keyframes cf-float {{ 0%,100% {{ transform: translateY(0); }} 50% {{ transform: translateY(-3px); }} }}

    /* ---------- avatars ---------- */
    .cf-av {{
        display:inline-flex; align-items:center; justify-content:center;
        border-radius: 50%; font-weight: 750; color: #fff; flex: 0 0 auto;
        box-shadow: var(--shadow-sm);
    }}

    /* ---------- misc ---------- */
    .cf-grid {{ display:grid; gap:.7rem; }}
    .cf-row {{ display:flex; align-items:center; gap:.55rem; flex-wrap:wrap; }}
    .cf-spacer {{ height: .7rem; }}
    .cf-heat {{ display:grid; grid-template-columns: repeat(auto-fill, 13px); gap:3px; }}
    .cf-heat i {{ width:13px; height:13px; border-radius:3px; display:block; }}
    .cf-quote {{
        border-left: 3px solid var(--primary); padding-left: .9rem;
        font-style: italic; color: var(--text-2);
    }}
    .cf-skeleton {{
        height: 120px; border-radius: var(--r-lg);
        background: linear-gradient(90deg, var(--surface) 25%, var(--surface-2) 37%, var(--surface) 63%);
        background-size: 400% 100%; animation: cf-shimmer 1.4s ease infinite;
    }}
    @keyframes cf-shimmer {{ 0% {{background-position: 100% 0;}} 100% {{background-position: 0 0;}} }}

    @media (max-width: 640px) {{
        .block-container {{ padding-left: .75rem !important; padding-right: .75rem !important; }}
        .cf-display {{ font-size: calc(2.1rem * var(--fs)); }}
        .cf-q {{ font-size: calc(1.24rem * var(--fs)); }}
    }}
    @media (prefers-reduced-motion: reduce) {{
        *, *::before, *::after {{ animation-duration: .001ms !important; transition-duration: .001ms !important; }}
    }}
    {anim}
    </style>
    """


def inject(dark: bool = True, font_size: str = 'Default', motion: bool = True) -> None:
    """Inject the design system for this rerun."""
    st.markdown(_css(dark, FONT_SCALE.get(font_size, 1.0), motion), unsafe_allow_html=True)


def haptic(pattern: str = 'light') -> None:
    """Fire a short vibration on devices that support it.

    Streamlit renders components in an iframe, so this is best-effort: it works
    on Android/Chrome, and silently no-ops on iOS Safari and on desktop.
    """
    ms = {'light': 8, 'medium': 18, 'heavy': [12, 24, 12], 'success': [8, 40, 14]}
    pat = ms.get(pattern, 8)
    st.markdown(
        f"<script>try{{(window.parent||window).navigator.vibrate({pat});}}catch(e){{}}</script>",
        unsafe_allow_html=True,
    )


def avatar_html(name: str, color: str, size: int = 40, ring: bool = False) -> str:
    initials = ''.join(p[0] for p in name.split()[:2]).upper() or '?'
    c2 = color
    ring_css = (
        f'box-shadow:0 0 0 2px var(--bg), 0 0 0 4px {color};' if ring else ''
    )
    return (
        f'<span class="cf-av" style="width:{size}px;height:{size}px;'
        f'font-size:{max(11, int(size * 0.38))}px;'
        f'background:linear-gradient(135deg,{color},{c2}cc);{ring_css}">{initials}</span>'
    )
