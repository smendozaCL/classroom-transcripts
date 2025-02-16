import streamlit as st
import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Configure debug settings
DEBUG = bool(os.getenv("DEBUG", "true"))  # Force debug mode temporarily
if DEBUG:
    logging.getLogger('watchdog').setLevel(logging.WARNING)
    logging.basicConfig(level=logging.DEBUG)
    st.write("Debug mode enabled")


upload_page = st.Page(
    "src/upload.py",
    title="Upload Audio",
    icon="📤",
    url_path="/upload",
    default=True,
)
dashboard_page = st.Page(
    "src/dashboard.py",
    title="Review Transcripts",
    icon="🎙️",
    url_path="/dashboard",
)

# Build pages list based on debug setting
pages_list = [upload_page, dashboard_page]
if DEBUG:
    debug_page = st.Page(
        "src/debug_table.py",
        title="Debug Table",
        icon="🔍",
        url_path="/debug",
    )
    pages_list.append(debug_page)

pages = st.navigation(pages_list)
pages.run()
