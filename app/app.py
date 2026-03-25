"""Streamlit entrypoint."""
from pathlib import Path
import streamlit as st
from app.wizard import SnipeSetupWizard

st.set_page_config(
    page_title="Snipe",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

wizard = SnipeSetupWizard(env_path=Path(".env"))
if not wizard.is_configured():
    wizard.run()
    st.stop()

from app.ui.components.easter_eggs import inject_konami_detector
inject_konami_detector()

with st.sidebar:
    st.divider()
    audio_enabled = st.checkbox(
        "🔊 Enable audio easter egg",
        value=False,
        help="Plays a synthesised sound on Konami code activation. Off by default.",
    )

from app.ui.Search import render
render(audio_enabled=audio_enabled)
