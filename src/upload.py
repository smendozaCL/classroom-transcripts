import streamlit as st
import assemblyai as aai
import os
import logging
import io
from azure.identity import ClientSecretCredential
from azure.storage.blob import BlobServiceClient
from azure.data.tables import TableServiceClient, TableEntity
from datetime import datetime
import asyncio
import importlib
from streamlit.runtime.uploaded_file_manager import UploadedFile


@st.cache_resource
def get_app_config():
    """Cache the application configuration."""
    return {
        "page_title": "Classroom Transcripts",
        "page_icon": "🎓",
        "layout": "wide",
        "initial_sidebar_state": "expanded",
        "menu_items": {
            "Get Help": "https://github.com/yourusername/classroom-transcripts",
            "Report a Bug": "https://github.com/yourusername/classroom-transcripts/issues",
            "About": """
            # Classroom Transcripts
            
            A tool for managing and analyzing classroom audio transcripts.
            """,
        },
    }


def main():
    """Main application entry point."""
    # Set page config explicitly with correct parameter names
    config = get_app_config()
    st.set_page_config(
        page_title=config["page_title"],
        page_icon=config["page_icon"],
        layout=config["layout"],
        initial_sidebar_state=config["initial_sidebar_state"],
        menu_items=config["menu_items"],
    )

    # Initialize session state
    if "initialized" not in st.session_state:
        st.session_state.initialized = True
        st.session_state.debug = False
        st.session_state.current_page = "dashboard"

    # Main navigation
    pages = {
        "dashboard": {
            "title": "📊 Transcript Dashboard",
            "module": "pages.admin_dashboard",
        },
        "upload": {"title": "📤 Upload Audio", "module": "pages.upload_audio"},
        "settings": {"title": "⚙️ Settings", "module": "pages.settings"},
    }

    # Sidebar navigation
    with st.sidebar:
        st.title("Navigation")
        for key, page in pages.items():
            if st.button(page["title"], key=f"nav_{key}"):
                st.session_state.current_page = key
                st.rerun()

    # Load and display current page
    try:
        page = pages[st.session_state.current_page]
        module = importlib.import_module(page["module"])
        if hasattr(module, "show"):
            module.show()
    except Exception as e:
        st.error(f"Error loading page: {str(e)}")
        if st.session_state.debug:
            st.exception(e)


if __name__ == "__main__":
    main()

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
        logging.debug("Successfully authenticated with Azure using service principal")
        return credential
    except Exception as e:
        logging.error(f"Error authenticating with Azure: {e}")
        raise e


# Get storage account name from environment
storage_account = os.getenv("AZURE_STORAGE_ACCOUNT", "classroomtranscripts")
if not storage_account:
    logging.warning(
        "Environment variable AZURE_STORAGE_ACCOUNT not found. Using default value 'classroomtranscripts'."
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

    # Create table service client and ensure TranscriptMappings table exists
    try:
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not connection_string:
            raise ValueError(
                "AZURE_STORAGE_CONNECTION_STRING environment variable not set"
            )

        table_service_client = TableServiceClient.from_connection_string(
            connection_string
        )
        table_client = table_service_client.get_table_client("TranscriptMappings")

        # Use create_table_if_not_exists instead of get_table_properties
        table_service_client.create_table_if_not_exists("TranscriptMappings")
        logging.info("TranscriptMappings table exists or was created")

    except ValueError as e:
        logging.error(f"Configuration error: {e}")
        st.error("Missing required configuration. Please check environment variables.")
    except Exception as e:
        logging.error(f"Error setting up table storage: {e}")

except Exception as e:
    logging.error(f"Error connecting to Azure Storage: {e}")

logging.debug("Debug information:")
logging.debug(f"Account URL: {account_url}")
logging.debug(f"Upload Container: {uploads_container}")
logging.debug(f"Transcripts Container: {transcripts_container}")
logging.debug("Azure Identity: Using service principal authentication")

st.title("🎤 Classroom Transcripts")
if org_name := os.getenv("ORGANIZATION_NAME"):
    st.caption(f"Internal tool for testing by {org_name}.")

st.subheader("Upload a Class Recording")
st.write(
    "We'll generate a transcript and post it for you and your coach."
)


def upload_to_azure(file):
    try:
        # Create BlobClient for upload
        blob_client = uploads_container_client.get_blob_client(file.name)

        blob = blob_client.upload_blob(file, overwrite=True)

        # Verify the blob exists by trying to get its properties
        try:
            blob_client.get_blob_properties()
            return blob
        except Exception as e:
            logging.error(f"Error uploading to Azure: {e}")
            return False

    except Exception as e:
        logging.error(f"Error uploading to Azure: {e}")
        return False


async def submit_transcription(file: UploadedFile) -> str:
    try:
        # Get the callback URL from environment
        callback_url = os.getenv("ASSEMBLYAI_CALLBACK_URL")
        
        # Configure transcription with webhook if available
        config = transcription_config
        if callback_url:
            config = config.set_webhook(callback_url)
            logging.info(f"Using callback URL: {callback_url}")
            
        transcriber = aai.Transcriber(config=config)
        
        # Reset file pointer to beginning and read fresh data
        file.seek(0)
        file_bytes = io.BytesIO(file.read())
        if file_bytes.getbuffer().nbytes > 0:
            logging.info(f"Starting transcription for file: {file.name}")
            
            # Submit transcription request without polling for completion
            transcript = transcriber.submit(file_bytes)
            logging.info(f"Got transcription ID: {transcript.id}")

            # Store the initial mapping without waiting for completion
            await store_mapping_in_table(
                file.name, transcript.id, transcript.audio_url
            )

            # Return queued status - webhook will handle completion
            return aai.TranscriptStatus.queued

        else:
            logging.error("File is empty: %s", file.name)
            st.error("File is empty. Is that the right file?")
            return aai.TranscriptStatus.error

    except Exception as e:
        logging.error(f"Error submitting transcription: {e}")
        st.error("We couldn't transcribe that file. Is that the right file?")
        st.expander("Error details").write(f"{e}")
        return aai.TranscriptStatus.error


async def store_mapping_in_table(blob_name, transcript_id, audio_url):
    try:
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not connection_string:
            raise ValueError(
                "AZURE_STORAGE_CONNECTION_STRING environment variable not set"
            )

        table_service_client = TableServiceClient.from_connection_string(
            connection_string
        )
        table_client = table_service_client.get_table_client("TranscriptMappings")

        entity = TableEntity()
        entity["PartitionKey"] = "AudioFiles"
        entity["RowKey"] = blob_name
        entity["transcriptId"] = transcript_id
        entity["audioUrl"] = audio_url
        entity["uploadTime"] = datetime.utcnow().isoformat()

        table_client.create_entity(entity=entity)
        logging.info(f"Stored mapping in table: {blob_name} -> {transcript_id}")

    except ValueError as e:
        logging.error(f"Configuration error: {e}")
    except Exception as e:
        logging.error(f"Error storing mapping in table: {e}")


async def get_transcript_mapping(blob_name):
    """Retrieve transcript mapping for a given blob name."""
    try:
        connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not connection_string:
            raise ValueError(
                "AZURE_STORAGE_CONNECTION_STRING environment variable not set"
            )

        table_service_client = TableServiceClient.from_connection_string(
            connection_string
        )
        table_client = table_service_client.get_table_client("TranscriptMappings")

        try:
            entity = table_client.get_entity("AudioFiles", blob_name)
            return {
                "transcriptId": entity["transcriptId"],
                "audioUrl": entity["audioUrl"],
                "uploadTime": entity["uploadTime"],
            }
        except Exception as e:
            logging.warning(f"No mapping found for blob {blob_name}: {e}")
            return None

    except ValueError as e:
        logging.error(f"Configuration error: {e}")
        return None
    except Exception as e:
        logging.error(f"Error retrieving mapping from table: {e}")
        return None


if uploaded_file := st.file_uploader(
    "Choose an audio file",
    type=[
        "3ga",
        "8svx",
        "aac",
        "ac3",
        "aif",
        "aiff",
        "alac",
        "amr",
        "ape",
        "au",
        "dss",
        "flac",
        "flv",
        "m4a",
        "m4b",
        "m4p",
        "m4r",
        "mp3",
        "mpga",
        "ogg",
        "oga",
        "mogg",
        "opus",
        "qcp",
        "tta",
        "voc",
        "wav",
        "wma",
        "wv",
    ],
):
    if upload_to_azure(uploaded_file):
        with st.spinner("Submitting for transcription..."):
            status = asyncio.run(submit_transcription(uploaded_file))
            if status == aai.TranscriptStatus.queued:
                st.success("✅ Transcription submitted successfully!")
                st.info(
                    "We'll process that transcript and share it with your coach. You can close this window or upload another file."
                )
                logging.info(f"'{uploaded_file.name}' submitted for transcription.")
            else:
                st.error("Upload failed - please try again.")
                logging.error(f"Transcription failed with status: {status}")
    else:
        st.error("Upload to storage failed - please try again")


if feedback_email := os.getenv("FEEDBACK_EMAIL"):
    st.caption(f"📧 Help and feedback: {feedback_email}")

with st.sidebar:
    if os.getenv("DEBUG"):
        st.write(st.experimental_user)
