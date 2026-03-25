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

from app.ui.Search import render
render()
