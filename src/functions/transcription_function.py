import os
import json
import logging
import azure.functions as func
import assemblyai as aai
from assemblyai import Transcript
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from urllib.parse import urlparse


def get_azure_credential():
    """Get the appropriate Azure credential based on the environment."""
    try:
        # First try Managed Identity
        credential = ManagedIdentityCredential()
        # Test the credential
        credential.get_token("https://storage.azure.com/.default")
        logging.info("Using Managed Identity credential")
        return credential
    except Exception as e:
        logging.info(f"Managed Identity not available: {str(e)}")
        try:
            # Fall back to DefaultAzureCredential
            credential = DefaultAzureCredential()
            credential.get_token("https://storage.azure.com/.default")
            logging.info("Using Default Azure credential")
            return credential
        except Exception as e:
            logging.error(f"Failed to get Azure credential: {str(e)}")
            raise


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

        # Get Azure credential
        credential = get_azure_credential()

        # Get storage account name from environment
        storage_account = os.getenv("AZURE_STORAGE_ACCOUNT")
        if not storage_account:
            raise ValueError("AZURE_STORAGE_ACCOUNT not found in environment variables")

        # Create BlobServiceClient
        account_url = f"https://{storage_account}.blob.core.windows.net"
        blob_service_client = BlobServiceClient(account_url, credential=credential)
        logging.info(f"Connected to storage account: {account_url}")

        # Get the uploads container client
        uploads_container = blob_service_client.get_container_client("uploads")

        # Generate a URL with SAS token for AssemblyAI to access
        blob_client = uploads_container.get_blob_client(myblob.name)
        sas_token = generate_sas_token(blob_client)
        audio_url = f"{blob_client.url}?{sas_token}"
        logging.info(f"Generated SAS URL for blob: {blob_client.url}")

        # Construct webhook URL using WEBSITE_HOSTNAME
        website_hostname = os.getenv("WEBSITE_HOSTNAME", "localhost:7071")
        webhook_url = f"https://{website_hostname}/api/webhook"
        logging.info(f"Webhook URL: {webhook_url}")

        # Use the AssemblyAI API to transcribe the audio file
        logging.info("Submitting transcription request to AssemblyAI...")
        transcriber = aai.Transcriber()
        config = aai.TranscriptionConfig(
            speaker_labels=True,
            webhook_url=webhook_url,
            webhook_auth_header_name="x-functions-key",
            webhook_auth_header_value=os.getenv("AZURE_FUNCTION_KEY", ""),
            speech_model=aai.SpeechModel.best,
            iab_categories=True,
            auto_chapters=True,
            content_safety=True,
            auto_highlights=True,
            sentiment_analysis=True,
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
        logging.info(f"Transcription config: {config}")

        transcript = transcriber.submit(audio_url, config)
        logging.info(f"Submitted transcription with ID: {transcript.id}")
        logging.info(f"Full transcript response: {transcript.__dict__}")

    except Exception as e:
        logging.error(f"Error submitting transcription: {str(e)}")
        raise


def generate_sas_token(blob_client, expiry_hours=2):
    """Generate a short-lived SAS token for AssemblyAI to access the blob."""
    from datetime import datetime, timedelta
    from azure.storage.blob import generate_blob_sas, BlobSasPermissions

    # Generate SAS token that expires in specified hours
    token = generate_blob_sas(
        account_name=blob_client.account_name,
        container_name=blob_client.container_name,
        blob_name=blob_client.blob_name,
        account_key=None,  # Using Azure AD authentication
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(hours=expiry_hours),
    )
    return token


def handle_webhook(req: func.HttpRequest) -> func.HttpResponse:
    """Handle the webhook callback from AssemblyAI."""
    logging.info("Received webhook from AssemblyAI")
    logging.info(f"Request URL: {req.url}")
    logging.info(f"Request headers: {dict(req.headers)}")

    try:
        # Get Azure credential
        credential = get_azure_credential()

        # Get storage account name from environment
        storage_account = os.getenv("AZURE_STORAGE_ACCOUNT")
        if not storage_account:
            raise ValueError("AZURE_STORAGE_ACCOUNT not found in environment variables")

        # Create BlobServiceClient
        account_url = f"https://{storage_account}.blob.core.windows.net"
        blob_service_client = BlobServiceClient(account_url, credential=credential)

        # Get the transcript from the webhook
        webhook_body = req.get_json()
        logging.info(f"Webhook body: {webhook_body}")

        if webhook_body.get("status") != "completed":
            logging.info(f"Received non-completed status: {webhook_body.get('status')}")
            return func.HttpResponse(status_code=200)

        transcript_id = webhook_body.get("transcript_id")
        logging.info(f"Processing transcript ID: {transcript_id}")

        # Retrieve the complete transcript from AssemblyAI
        transcript = Transcript.get_by_id(transcript_id)
        logging.info("Retrieved transcript from AssemblyAI")

        # Format the transcript content
        formatted_transcript = []
        if hasattr(transcript, "utterances") and transcript.utterances:
            logging.info("Processing transcript utterances")
            for utterance in transcript.utterances:
                start_time = int(utterance.start / 1000)  # Convert to seconds
                hours = start_time // 3600
                minutes = (start_time % 3600) // 60
                seconds = start_time % 60
                timestamp = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

                formatted_transcript.append(
                    {
                        "timestamp": timestamp,
                        "speaker": f"Speaker {utterance.speaker}",
                        "text": utterance.text,
                    }
                )

        # Prepare transcript data
        transcript_data = {
            "transcript_id": transcript_id,
            "status": "completed",
            "utterances": formatted_transcript,
            "metadata": {
                "audio_url": transcript.audio_url,
                "duration": transcript.audio_duration,
                "language": transcript.language
                if hasattr(transcript, "language")
                else None,
                "speech_model": transcript.speech_model,
                "auto_chapters": transcript.chapters
                if hasattr(transcript, "chapters")
                else None,
                "auto_highlights": transcript.auto_highlights
                if hasattr(transcript, "auto_highlights")
                else None,
                "content_safety": transcript.content_safety
                if hasattr(transcript, "content_safety")
                else None,
                "iab_categories": transcript.iab_categories
                if hasattr(transcript, "iab_categories")
                else None,
                "sentiment_analysis": transcript.sentiment_analysis
                if hasattr(transcript, "sentiment_analysis")
                else None,
            },
        }

        # Save transcript to blob storage
        transcriptions_container = blob_service_client.get_container_client(
            "transcriptions"
        )
        blob_name = f"transcript_{transcript_id}.json"
        blob_client = transcriptions_container.get_blob_client(blob_name)

        blob_client.upload_blob(
            json.dumps(transcript_data, indent=2),
            overwrite=True,
            content_settings={"content_type": "application/json"},
        )
        logging.info(f"Saved transcript to blob: {blob_name}")

        return func.HttpResponse(
            json.dumps(
                {
                    "status": "success",
                    "transcript_id": transcript_id,
                    "message": "Transcript received and stored",
                }
            ),
            mimetype="application/json",
            status_code=200,
        )

    except Exception as e:
        logging.error(f"Error processing webhook: {str(e)}")
        return func.HttpResponse(f"Error processing webhook: {str(e)}", status_code=500)
