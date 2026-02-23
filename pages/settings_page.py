"""
Page 4 — Settings
Save timezone and Gemini API key to a persistent JSON file.
"""

import streamlit as st
import pytz
from settings import load_settings, save_settings


def page_settings() -> None:
    st.header("Settings")

    current = load_settings()

    all_timezones = sorted(pytz.common_timezones)

    # Determine current index for the selectbox
    current_tz = current.get("timezone", "America/New_York")
    try:
        tz_index = all_timezones.index(current_tz)
    except ValueError:
        tz_index = all_timezones.index("America/New_York")

    with st.form("settings_form"):
        timezone = st.selectbox(
            "Display Timezone",
            options=all_timezones,
            index=tz_index,
            help="All chart timestamps will be converted to this timezone.",
        )

        api_key = st.text_input(
            "Gemini API Key",
            value=current.get("gemini_api_key", ""),
            type="password",
            help="Required for the AI Recommendations page. Get a key at https://aistudio.google.com/apikey",
        )

        submitted = st.form_submit_button("Save Settings", type="primary")

    if submitted:
        save_settings({"timezone": timezone, "gemini_api_key": api_key})
        st.success("Settings saved successfully!")
        st.balloons()
