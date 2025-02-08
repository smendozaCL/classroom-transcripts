import streamlit as st
from azure.storage.blob import BlobClient
from azure.core.credentials import AzureSasCredential
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

# Validate Azure credentials
sas_url = st.secrets["AZURE_STORAGE_SAS_URL"]

if not sas_url:
    st.error(
        "Azure Storage SAS URL is not properly configured. Please check your .env file."
    )
    st.stop()

# Parse SAS URL to separate components
parsed_url = urlparse(sas_url)
# Base URL without container and SAS token
account_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
# SAS token without the leading '?'
sas_token = parsed_url.query
# Fixed container name
container_name = "uploads"

# Debug information (will be hidden in production)
if st.secrets.get("DEBUG", False):
    st.write("Debug Info:")
    st.write(f"Account URL: {account_url}")
    st.write(f"Container: {container_name}")
    # Only show first/last few chars of SAS token for security
    if sas_token:
        st.write(f"SAS token length: {len(sas_token)}")
        st.write(f"SAS token preview: {sas_token[:10]}...{sas_token[-10:]}")
        # Show permissions in the SAS token
        permissions = [param for param in sas_token.split("&") if "sp=" in param]
        if permissions:
            st.write(f"SAS Permissions: {permissions[0]}")

st.set_page_config(
    page_title="Classroom Transcripts with eddo.ai",
    page_icon="🎤",
)

st.title("Classroom Transcription")

st.write("Upload your classroom audio files to get a text-based transcript.")


def upload_to_azure(file):
    try:
        # Create credential from SAS token
        credential = AzureSasCredential(sas_token)

        # Create BlobClient with separate URL and credential
        blob_client = BlobClient(
            account_url=account_url,
            container_name=container_name,
            blob_name=file.name,
            credential=credential,
        )

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
        st.success(
            "You'll receive a Google Drive share notification when the transcript is ready."
        )


uploaded_file = st.file_uploader("Choose an audio file", type=["mp3", "wav", "m4a"])

if uploaded_file is not None:
    handle_file_upload(uploaded_file)
