import azure.functions as func
import logging
import os
from azure.storage.blob import BlobServiceClient, BlobSasPermissions
from azure.identity import DefaultAzureCredential
from azure.storage.blob import generate_blob_sas
from datetime import datetime, timedelta
import requests
import assemblyai as aai

app = func.FunctionApp()


@app.function_name(name="SubmitTranscription")
@app.blob_trigger(
    arg_name="myblob", path="uploads/{name}", connection="AzureWebJobsStorage"
)
def submit_transcription(myblob: func.InputStream):
    """Submit an audio file for transcription when uploaded to blob storage."""
    logging.info(f"Python blob trigger function processed blob: {myblob.name}")
    logging.info(f"Blob URI: {myblob.uri}")

    try:
        # Set AssemblyAI API key
        api_key = os.getenv("ASSEMBLYAI_API_KEY")
        if not api_key:
            raise ValueError("ASSEMBLYAI_API_KEY not found in environment variables")
        logging.info("AssemblyAI API key found")
        aai.settings.api_key = api_key

        # Check if we're running locally
        storage_conn = os.getenv("AzureWebJobsStorage", "")
        is_local = "UseDevelopmentStorage=true" in storage_conn

        if is_local:
            # Use connection string for local development
            connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
            if not connection_string:
                raise ValueError("AZURE_STORAGE_CONNECTION_STRING not found")
            blob_service_client = BlobServiceClient.from_connection_string(
                connection_string
            )
            logging.info("Connected to local storage using connection string")
        else:
            # Use Azure AD auth for production
            credential = DefaultAzureCredential()
            storage_account = os.getenv("AZURE_STORAGE_ACCOUNT")
            if not storage_account:
                raise ValueError("AZURE_STORAGE_ACCOUNT not found")
            account_url = f"https://{storage_account}.blob.core.windows.net"
            blob_service_client = BlobServiceClient(account_url, credential=credential)
            logging.info(f"Connected to storage account: {account_url}")

        # Get the uploads container client
        uploads_container = blob_service_client.get_container_client("uploads")
        if not myblob.name:
            raise ValueError("Blob name is required")

        # Clean up blob name - remove any 'uploads/' prefix if present
        clean_blob_name = myblob.name.replace("uploads/", "", 1)
        blob_client = uploads_container.get_blob_client(clean_blob_name)

        # Get the audio URL
        if is_local:
            # For local development, use the blob URL directly
            audio_url = blob_client.url
            logging.info(f"Using local blob URL: {audio_url}")
        else:
            # Generate SAS token for the blob with read permission
            logging.info(f"\n=== Generating SAS Token ===")
            logging.info(f"Blob: {clean_blob_name}")
            try:
                sas_token = generate_blob_sas(
                    account_name=storage_account,
                    container_name="uploads",
                    blob_name=clean_blob_name,
                    account_key=None,
                    credential=credential,
                    permission=BlobSasPermissions(read=True),
                    expiry=datetime.utcnow() + timedelta(hours=1),
                )
                audio_url = f"{blob_client.url}?{sas_token}"

                # Test if blob exists and is accessible
                blob_properties = blob_client.get_blob_properties()
                logging.info("\n=== Blob Properties ===")
                logging.info(
                    f"Content Type: {blob_properties.content_settings.content_type}"
                )
                logging.info(f"Size: {blob_properties.size:,} bytes")
                logging.info(f"Created: {blob_properties.creation_time}")
                logging.info(f"Base URL: {blob_client.url}")
                logging.info("SAS URL generated successfully (token redacted)")

                # Verify SAS URL works
                logging.info("\n=== Testing SAS URL ===")
                response = requests.head(audio_url)
                logging.info(f"Status Code: {response.status_code}")
                logging.info(
                    f"Content Type: {response.headers.get('content-type', 'N/A')}"
                )
                logging.info(
                    f"Content Length: {response.headers.get('content-length', 'N/A'):,} bytes"
                )

            except Exception as e:
                logging.error(f"\n❌ Error generating/testing SAS token:")
                logging.error(str(e))
                raise

        # Construct webhook URL using WEBSITE_HOSTNAME
        website_hostname = os.getenv("WEBSITE_HOSTNAME", "localhost:7071")
        webhook_url = (
            f"http://{website_hostname}/api/webhook"
            if "localhost" in website_hostname
            else f"https://{website_hostname}/api/webhook"
        )
        logging.info(f"\n=== Webhook Configuration ===")
        logging.info(f"URL: {webhook_url}")
        logging.info(f"Auth Header: x-functions-key")

        # Use the AssemblyAI API to transcribe the audio file
        logging.info("\n=== Submitting to AssemblyAI ===")
        transcriber = aai.Transcriber()
        config = aai.TranscriptionConfig(
            speaker_labels=True,
            webhook_url=webhook_url,
            webhook_auth_header_name="x-functions-key",
            webhook_auth_header_value=os.getenv("AZURE_FUNCTION_KEY", ""),
        )
        logging.info("Configuration:")
        logging.info(f"- Speaker Labels: Enabled")
        logging.info(f"- Webhook URL: {webhook_url}")
        logging.info("- Webhook Auth: Configured")

        transcript = transcriber.submit(audio_url, config)
        logging.info("\n=== AssemblyAI Response ===")
        logging.info(f"Transcript ID: {transcript.id}")
        logging.info(f"Status: {transcript.status}")
        if hasattr(transcript, "error") and transcript.error:
            logging.error(f"❌ Error: {transcript.error}")

    except Exception as e:
        logging.error(f"Error submitting transcription: {str(e)}")
        raise
