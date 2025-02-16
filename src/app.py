import streamlit as st
from azure.identity import ClientSecretCredential
import os
import assemblyai as aai
from datetime import datetime, timezone, timedelta
from azure.storage.blob import BlobSasPermissions, generate_blob_sas, BlobServiceClient
from streamlit.runtime.uploaded_file_manager import UploadedFile
import json
import logging
import io
from dotenv import load_dotenv
import asyncio
from azure.data.tables import TableServiceClient, TableEntity
from pathlib import Path
import importlib
import sys

load_dotenv()

# Configure debug settings
DEBUG = bool(os.getenv("DEBUG"))
if DEBUG:
    logging.basicConfig(level=logging.DEBUG)
    st.write("Debug mode enabled")

# Add src directory to Python path
src_path = Path(__file__).parent
sys.path.append(str(src_path))

import streamlit as st

upload_page = st.Page(
    "upload.py",
    title="Upload Audio",
    icon="📤",
    url_path="/upload",
    default=True,
)
dashboard_page = st.Page(
    "dashboard.py",
    title="Review Transcripts",
    icon="🎙️",
    url_path="/dashboard",
)

# Build pages list based on debug setting
pages_list = [upload_page, dashboard_page]
if DEBUG:
    debug_page = st.Page(
        "debug_table.py",
        title="Debug Table",
        icon="🔍",
        url_path="/debug",
    )
    pages_list.append(debug_page)

pages = st.navigation(pages_list)
pages.run()
