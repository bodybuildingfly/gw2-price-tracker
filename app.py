"""
GW2 Price Tracker — main entrypoint.

Uses the modern Streamlit st.navigation / st.Page API for multi-page routing.
"""

import streamlit as st

st.set_page_config(
    page_title="GW2 Price Tracker",
    page_icon="⚔️",
    layout="wide",
)

# ── Import page functions (each has a unique name) ───────────────────
from pages.dashboard import page_dashboard
from pages.item_analysis import page_item_analysis
from pages.recommendations import page_recommendations
from pages.ai_recs import page_ai_recommendations
from pages.mystic_forge import page_mystic_forge
from pages.settings_page import page_settings

# ── Define pages ─────────────────────────────────────────────────────
pages = [
    st.Page(page_dashboard, title="Dashboard", icon="🏠", default=True),
    st.Page(page_item_analysis, title="Item Analysis", icon="📊"),
    st.Page(page_recommendations, title="Recommendations", icon="📋"),
    st.Page(page_ai_recommendations, title="AI Recommendations", icon="🤖"),
    st.Page(page_mystic_forge, title="Mystic Forge", icon="🔮"),
    st.Page(page_settings, title="Settings", icon="⚙️"),
]

# ── Render navigation & selected page ───────────────────────────────
nav = st.navigation(pages)
nav.run()