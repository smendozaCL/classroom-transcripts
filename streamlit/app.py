import streamlit as st
from azure.storage.blob import BlobClient, BlobServiceClient
from azure.identity import ClientSecretCredential
import os
import time
import logging


st.set_page_config(
    page_title="Classroom Transcripts with eddo.ai",
    page_icon="🎤",
)


def get_azure_credential():
    """Get Azure credential using service principal."""
    try:
        # Get service principal credentials from environment
        tenant_id = os.getenv("AZURE_TENANT_ID")
        client_id = os.getenv("AZURE_CLIENT_ID")
        client_secret = os.getenv("AZURE_CLIENT_SECRET")

        if not all([tenant_id, client_id, client_secret]):
            raise ValueError(
                "Missing required Azure credentials in environment variables"
            )

        # Create service principal credential
        credential = ClientSecretCredential(
            tenant_id=str(tenant_id),
            client_id=str(client_id),
            client_secret=str(client_secret),
        )

        # Test the credential
        credential.get_token("https://storage.azure.com/.default")
        st.success("Successfully authenticated with Azure using service principal")
        return credential
    except Exception as e:
        st.error(f"Failed to authenticate with Azure: {str(e)}")
        raise


# Get storage account name from environment
storage_account = os.getenv("AZURE_STORAGE_ACCOUNT")
if not storage_account:
    st.error("AZURE_STORAGE_ACCOUNT not found in environment variables")
    st.stop()

try:
    # Get Azure credential
    credential = get_azure_credential()

    # Create BlobServiceClient
    account_url = f"https://{storage_account}.blob.core.windows.net"
    blob_service_client = BlobServiceClient(account_url, credential=credential)

    # Fixed container names
    uploads_container = "uploads"
    transcripts_container = "transcriptions"

    # Get container clients and create if they don't exist
    uploads_container_client = blob_service_client.get_container_client(
        uploads_container
    )
    transcripts_container_client = blob_service_client.get_container_client(
        transcripts_container
    )

    # Create containers if they don't exist
    try:
        uploads_container_client.get_container_properties()
    except Exception:
        st.info(f"Creating {uploads_container} container...")
        uploads_container_client = blob_service_client.create_container(
            uploads_container
        )

    try:
        transcripts_container_client.get_container_properties()
    except Exception:
        st.info(f"Creating {transcripts_container} container...")
        transcripts_container_client = blob_service_client.create_container(
            transcripts_container
        )

    st.success("Successfully connected to Azure Storage")

except Exception as e:
    st.error(f"Failed to connect to Azure Storage: {str(e)}")
    st.stop()

# Debug information (will be hidden in production)
if st.secrets.get("DEBUG", False):
    st.write("Debug Info:")
    st.write(f"Account URL: {account_url}")
    st.write(f"Upload Container: {uploads_container}")
    st.write(f"Transcripts Container: {transcripts_container}")
    st.write("Azure Identity: Using service principal authentication")


st.title("Classroom Transcription")

st.write("Upload your classroom audio files to get a text-based transcript.")


def check_transcript_status(blob_name):
    """Check if a transcript has been generated for the uploaded file."""
    try:
        if not blob_name:
            return False, None

        transcript_prefix = f"transcript_{blob_name.split('.')[0]}"

        matching_transcripts = list(
            transcripts_container_client.list_blobs(name_starts_with=transcript_prefix)
        )
        if matching_transcripts:
            # Get the most recent transcript
            latest_transcript = max(matching_transcripts, key=lambda x: x.last_modified)
            return True, str(latest_transcript.name)
        return False, None
    except Exception as e:
        st.error(f"Error checking transcript status: {e}")
        return False, None


def upload_to_azure(file):
    try:
        # Create BlobClient for upload
        blob_client = uploads_container_client.get_blob_client(file.name)

        with st.spinner("Uploading to Azure..."):
            blob_client.upload_blob(file, overwrite=True)

            # Verify the blob exists by trying to get its properties
            try:
                blob_client.get_blob_properties()
                st.success(f"'{file.name}' uploaded successfully!")
                st.info(
                    f"We'll process '{file.name}' and send you the transcript when it's ready. You can close this page or upload additional audio files."
                )
                return True
            except Exception as e:
                st.error(
                    "Upload appeared to succeed but file not found in Azure. Please try again."
                )
                logging.error(f"Blob verification failed: {str(e)}")
                return False

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

    upload_to_azure(file)


uploaded_file = st.file_uploader("Choose an audio file", type=["mp3", "wav", "m4a"])

if uploaded_file is not None:
    handle_file_upload(uploaded_file)
