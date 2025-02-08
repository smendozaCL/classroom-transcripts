import streamlit as st
import os
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient
from dotenv import load_dotenv

load_dotenv()

st.set_page_config(
    page_title="Classroom Transcripts with eddo.ai",
    page_icon="🎤",
)

st.title("Classroom Transcription")

st.write("Upload your classroom audio files to get a text-based transcript.")

# Azure Blob Storage configuration
AZURE_CONNECTION_STRING = os.getenv("AZURE_CONNECTION_STRING")
AZURE_CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME")

def upload_to_azure(file):
    try:
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
        blob_client = blob_service_client.get_blob_client(container=AZURE_CONTAINER_NAME, blob=file.name)
        
        with st.spinner("Uploading to Azure..."):
            blob_client.upload_blob(file, overwrite=True)
        
        st.success("File uploaded successfully!")
        return True
    except Exception as e:
        st.error(f"Error uploading file: {e}")
        return False

def handle_file_upload(file):
    if file.size > 50 * 1024 * 1024:  # 50 MB limit
        st.error("File size exceeds the 50 MB limit.")
        return
    
    if file.type not in ["audio/mpeg", "audio/wav", "audio/x-m4a"]:
        st.error("Unsupported file format. Please upload MP3, WAV, or M4A files.")
        return
    
    if upload_to_azure(file):
        st.success("You'll receive a Google Drive share notification when the transcript is ready.")

uploaded_file = st.file_uploader("Choose an audio file", type=["mp3", "wav", "m4a"])

if uploaded_file is not None:
    handle_file_upload(uploaded_file)
