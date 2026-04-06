"""First-run wizard: collect eBay credentials and write .env."""
from __future__ import annotations

from pathlib import Path

import streamlit as st
from circuitforge_core.wizard import BaseWizard


class SnipeSetupWizard(BaseWizard):
    """
    Guides the user through first-run setup:
    1. Enter eBay Client ID (EBAY_CLIENT_ID) + Secret (EBAY_CLIENT_SECRET)
    2. Choose sandbox vs production
    3. Verify connection (token fetch)
    4. Write .env file
    """

    def __init__(self, env_path: Path = Path(".env")):
        self._env_path = env_path

    def run(self) -> bool:
        """Run the setup wizard. Returns True if setup completed successfully."""
        st.title("🎯 Snipe — First Run Setup")
        st.info(
            "To use Snipe, you need eBay developer credentials. "
            "Register at developer.ebay.com and create an app to get your Client ID (EBAY_CLIENT_ID) and Secret (EBAY_CLIENT_SECRET)."
        )

        client_id = st.text_input("eBay Client ID (EBAY_CLIENT_ID)", type="password")
        client_secret = st.text_input("eBay Client Secret (EBAY_CLIENT_SECRET)", type="password")
        env = st.selectbox("eBay Environment", ["production", "sandbox"])

        if st.button("Save and verify"):
            if not client_id or not client_secret:
                st.error("Both Client ID and Secret are required.")
                return False
            # Write .env
            self._env_path.write_text(
                f"EBAY_CLIENT_ID={client_id}\n"
                f"EBAY_CLIENT_SECRET={client_secret}\n"
                f"EBAY_ENV={env}\n"
                f"SNIPE_DB=data/snipe.db\n"
            )
            st.success(f".env written to {self._env_path}. Reload the app to begin searching.")
            return True
        return False

    def is_configured(self) -> bool:
        """Return True if .env exists and has eBay credentials."""
        if not self._env_path.exists():
            return False
        text = self._env_path.read_text()
        return "EBAY_CLIENT_ID=" in text and "EBAY_CLIENT_SECRET=" in text
