import streamlit as st
from azure.identity import ClientSecretCredential
import os
import logging
import assemblyai as aai
from datetime import datetime, timezone, timedelta
from azure.storage.blob import BlobSasPermissions, generate_blob_sas, BlobServiceClient
from streamlit.runtime.uploaded_file_manager import UploadedFile
import json

# Initialize AssemblyAI
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")

# Configure AssemblyAI transcription settings
transcription_config = aai.TranscriptionConfig(
    speech_model=aai.SpeechModel.best,
    iab_categories=True,
    auto_chapters=True,
    content_safety=True,
    auto_highlights=True,
    sentiment_analysis=True,
    speaker_labels=True,
    filter_profanity=True,
    language_detection=True,
).set_redact_pii(
    policies=[
        aai.PIIRedactionPolicy.medical_condition,
        aai.PIIRedactionPolicy.email_address,
        aai.PIIRedactionPolicy.phone_number,
        aai.PIIRedactionPolicy.banking_information,
        aai.PIIRedactionPolicy.credit_card_number,
        aai.PIIRedactionPolicy.credit_card_cvv,
        aai.PIIRedactionPolicy.date_of_birth,
        aai.PIIRedactionPolicy.person_name,
        aai.PIIRedactionPolicy.organization,
        aai.PIIRedactionPolicy.location,
    ],
    redact_audio=True,
    substitution=aai.PIISubstitutionPolicy.hash,

)

st.set_page_config(
    page_title="Classroom Transcripts with eddo.ai",
    page_icon="🎤",
)


def handle_exception(e):
    if st.secrets.get("DEBUG", False):
        raise e
    st.error(f"Error: {e}")
    st.stop()


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
        handle_exception(e)
        return None


# Get storage account name from environment
storage_account = os.getenv("AZURE_STORAGE_ACCOUNT")
if not storage_account:
    handle_exception(
        Exception("AZURE_STORAGE_ACCOUNT not found in environment variables")
    )


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
    handle_exception(e)


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
        handle_exception(e)
        return False, None


def upload_to_azure(file):
    try:
        # Create BlobClient for upload
        blob_client = uploads_container_client.get_blob_client(file.name)

        with st.spinner("Uploading to Azure..."):
            blob = blob_client.upload_blob(file, overwrite=True)

            # Verify the blob exists by trying to get its properties
            try:
                blob_client.get_blob_properties()
                st.success(f"'{file.name}' uploaded successfully!")
                st.info(
                    f"We'll process '{file.name}' and send you the transcript when it's ready. You can close this page or upload additional audio files."
                )
                return blob
            except Exception as e:
                handle_exception(e)
                return False

    except Exception as e:
        handle_exception(e)
        return False


def get_blob_url(blob_client):
    """Get a URL for the blob that can be accessed by AssemblyAI."""
    try:
        # Get connection string from environment
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not connection_string:
            raise Exception(
                "AZURE_STORAGE_CONNECTION_STRING not found in environment variables"
            )

        # Create a temporary blob service client with connection string to get account key
        temp_service_client = BlobServiceClient.from_connection_string(
            connection_string
        )
        account_key = temp_service_client.credential.account_key

        # Generate SAS token with proper permissions and timeframe
        sas_expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        sas_start = datetime.now(timezone.utc) - timedelta(minutes=5)

        sas_token = generate_blob_sas(
            account_name=blob_client.account_name,
            container_name=blob_client.container_name,
            blob_name=blob_client.blob_name,
            permission=BlobSasPermissions(read=True),
            expiry=sas_expiry,
            start=sas_start,
            protocol="https",
            account_key=account_key,
        )

        # Construct the full URL with the SAS token
        blob_url = f"https://{blob_client.account_name}.blob.core.windows.net/{blob_client.container_name}/{blob_client.blob_name}"
        sas_url = f"{blob_url}?{sas_token}"

        # Ensure spaces are properly escaped in the URL
        return sas_url.replace(" ", "%20")

    except Exception as e:
        handle_exception(e)
        return None


def start_transcription(file: UploadedFile) -> bool:
    """Start AssemblyAI transcription for the uploaded file."""
    try:
        transcriber = aai.Transcriber(config=transcription_config)
        file_bytes = io.BytesIO(file.getvalue())
        if file_bytes:
            transcript = transcriber.transcribe(file_bytes)
        else:
            handle_exception(Exception("File is empty"))
            return False
        
        if transcript.status == aai.TranscriptStatus.error:
            handle_exception(Exception(f"Transcription error: {transcript.error}"))
        
        if transcript.status == aai.TranscriptStatus.completed:
            # Save transcript to Azure Storage
            if file.name:
                transcript_filename = f"transcript_{file.name.split('.')[0]}.txt"
            transcript_blob = transcripts_container_client.get_blob_client(
                transcript_filename
            )
            if transcript.text:
                upload_blob = transcript_blob.upload_blob(transcript.text, overwrite=True)
                if upload_blob:
                    return True
                st.warning("Transcript was not uploaded to Azure")

            transcript_json = json.dumps(transcript.json_response)
            transcript_blob.upload_blob(transcript_json, overwrite=True)

        if transcript.status == aai.TranscriptStatus.processing:
            st.info("This may take a few minutes. We'll notify you when it's ready.")
            return False
        return False
    except Exception as e:
        handle_exception(e)
        return False


uploaded_file = st.file_uploader("Choose an audio file", type=["mp3", "wav", "m4a"])

if uploaded_file is not None:
    blob = upload_to_azure(uploaded_file)
    if blob:
        blob_client = uploads_container_client.get_blob_client(uploaded_file.name)
        blob_url = get_blob_url(blob_client)
        if blob_url:
            with st.spinner("Transcription in progress...you can leave the app or upload additional audio files."):
                if start_transcription(uploaded_file):
                    st.success("Transcription complete! We'll post the file to Google Drive.")
