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
profile_page = st.Page( 
    "src/user_profile.py",
    title="Profile",
    icon="👤",
    url_path="/profile",
)

# Build pages list based on debug setting
pages_list = [upload_page]

if st.experimental_user.is_logged_in:
    pages_list.append(dashboard_page)
    pages_list.append(profile_page)
    with st.sidebar:
        cols = st.columns([1, 3])
        with cols[0]:
            st.image(st.experimental_user.picture)
        with cols[1]:
            st.write(st.experimental_user.name)
            st.write(st.experimental_user.email)
            if st.button("Logout"):
                st.logout()

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
