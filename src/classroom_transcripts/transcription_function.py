import os
import json
import logging
import azure.functions as func
import assemblyai as aai
from assemblyai import Transcript
from azure.storage.blob import BlobClient
from urllib.parse import urlparse, parse_qs


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

        # Get the SAS URL from environment variables
        storage_sas_url = os.getenv("AZURE_STORAGE_SAS_URL")
        if not storage_sas_url:
            raise ValueError("AZURE_STORAGE_SAS_URL not found in environment variables")
        logging.info("Storage SAS URL found")

        # Parse the base SAS URL
        parsed_url = urlparse(storage_sas_url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        sas_token = parsed_url.query
        logging.info(f"Base URL: {base_url}")

        # Construct the audio file URL
        audio_url = f"{base_url}/uploads/{myblob.name}?{sas_token}"
        logging.info(
            f"Audio URL constructed: {audio_url.split('?')[0]}"
        )  # Log URL without SAS token

        # Construct webhook URL using WEBSITE_HOSTNAME
        website_hostname = os.getenv("WEBSITE_HOSTNAME", "localhost:7071")
        webhook_url = f"http://{website_hostname}/api/webhook"  # Changed to http for local development
        logging.info(f"Webhook URL: {webhook_url}")

        # Test AssemblyAI API connection
        try:
            transcriber = aai.Transcriber()
            # Test API with a simple request
            test_response = transcriber.test_connection()
            logging.info(f"AssemblyAI API test response: {test_response}")
        except Exception as api_error:
            logging.error(f"AssemblyAI API test failed: {str(api_error)}")
            raise

        # Use the AssemblyAI API to transcribe the audio file
        logging.info("Submitting transcription request to AssemblyAI...")
        config = aai.TranscriptionConfig(
            speaker_labels=True,
            webhook_url=webhook_url,
            webhook_auth_header_name="x-functions-key",
            webhook_auth_header_value=os.getenv("AZURE_FUNCTION_KEY", ""),
        )
        logging.info(f"Transcription config: {config}")

        transcript = transcriber.submit(audio_url, config)
        logging.info(f"Submitted transcription with ID: {transcript.id}")
        logging.info(f"Full transcript response: {transcript.__dict__}")

    except Exception as e:
        logging.error(f"Error submitting transcription: {str(e)}")
        raise


def handle_webhook(req: func.HttpRequest) -> func.HttpResponse:
    """Handle the webhook callback from AssemblyAI."""
    logging.info("Received webhook from AssemblyAI")
    logging.info(f"Request URL: {req.url}")
    logging.info(f"Request headers: {dict(req.headers)}")

    try:
        # Get the SAS URL from environment variables
        storage_sas_url = os.getenv("AZURE_STORAGE_SAS_URL")
        if not storage_sas_url:
            raise ValueError("AZURE_STORAGE_SAS_URL not found in environment variables")
        logging.info("Storage SAS URL found")

        # Get the transcript from the webhook
        webhook_body = req.get_json()
        logging.info(f"Webhook body: {webhook_body}")

        if webhook_body.get("status") != "completed":
            logging.info(f"Received non-completed status: {webhook_body.get('status')}")
            return func.HttpResponse(
                status_code=200
            )  # Acknowledge non-completed webhooks

        transcript_id = webhook_body.get("transcript_id")
        logging.info(f"Processing transcript ID: {transcript_id}")

        # Retrieve the complete transcript from AssemblyAI
        transcript = Transcript.get_by_id(transcript_id)
        logging.info("Retrieved transcript from AssemblyAI")

        # Format the transcript to include speaker labels and timestamps
        formatted_transcript = []
        if hasattr(transcript, "utterances") and transcript.utterances:
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

        # Store the transcription results using SAS URL
        try:
            # Parse the base SAS URL to get the container
            parsed_url = urlparse(storage_sas_url)
            path_parts = parsed_url.path.split("/")
            container_name = path_parts[1] if len(path_parts) > 1 else "transcriptions"

            # Generate output blob name using transcript ID
            output_blob_name = f"transcript_{transcript_id}.json"

            # Construct the full blob URL with SAS token
            blob_url_with_sas = f"{parsed_url.scheme}://{parsed_url.netloc}/{container_name}/{output_blob_name}?{parsed_url.query}"

            # Create blob client with SAS URL
            blob_client = BlobClient.from_blob_url(blob_url_with_sas)

            # Upload the formatted transcript as JSON
            transcript_data = {
                "transcript_id": transcript_id,
                "status": "completed",
                "utterances": formatted_transcript,
                "metadata": {
                    "audio_url": transcript.audio_url,
                    "language": transcript.language,
                    "duration": transcript.audio_duration,
                    "created": transcript.created,
                },
            }

            blob_client.upload_blob(
                json.dumps(transcript_data, indent=2), overwrite=True
            )

            return func.HttpResponse(
                json.dumps(
                    {
                        "status": "success",
                        "transcript_id": transcript_id,
                        "blob_url": blob_url_with_sas.split("?")[
                            0
                        ],  # Remove SAS token from response
                    }
                ),
                mimetype="application/json",
                status_code=200,
            )

        except Exception as e:
            logging.error(f"Error storing transcript: {str(e)}")
            return func.HttpResponse(
                f"Error storing transcript: {str(e)}", status_code=500
            )

    except Exception as e:
        logging.error(f"Error processing webhook: {str(e)}")
        return func.HttpResponse(f"Error processing webhook: {str(e)}", status_code=500)
