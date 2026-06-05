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

        has_key = bool(current.get("gemini_api_key"))
        placeholder = "********" if has_key else ""

        api_key = st.text_input(
            "Gemini API Key",
            value="",
            placeholder=placeholder,
            type="password",
            max_chars=150,
            help="Required for the AI Recommendations page. Get a key at https://aistudio.google.com/apikey",
        )

        submitted = st.form_submit_button("Save Settings", type="primary")

    if submitted:
        new_settings = {"timezone": timezone}
        # Only update the API key if a new one was provided
        if api_key:
            new_settings["gemini_api_key"] = api_key
        else:
            new_settings["gemini_api_key"] = current.get("gemini_api_key", "")

        save_settings(new_settings)
        st.success("Settings saved successfully!")
        st.balloons()
