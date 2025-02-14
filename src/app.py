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

pages = st.navigation([upload_page, dashboard_page])
pages.run()
