import os
import azure.functions as func
import assemblyai as aai
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient

# Set AssemblyAI API key
api_key = os.getenv("ASSEMBLYAI_API_KEY")
if not api_key:
    raise ValueError("ASSEMBLYAI_API_KEY not found in environment variables")
aai.settings.api_key = api_key

# Azure Blob Storage connection string
connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
if not connection_string:
    raise ValueError("AZURE_STORAGE_CONNECTION_STRING not found in environment variables")

blob_service_client = BlobServiceClient.from_connection_string(connection_string)

def main(blob: func.InputStream):
    # Download the audio file from the blob storage
    audio_url = blob.uri

    # Use the AssemblyAI API to transcribe the audio file
    transcriber = aai.Transcriber()
    config = aai.TranscriptionConfig(speaker_labels=True, timestamps=True).set_redact_pii(
        policies=[
            aai.PIIRedactionPolicy.person_name,
            aai.PIIRedactionPolicy.organization,
        ],
        substitution=aai.PIISubstitutionPolicy.hash,
    )
    transcript = transcriber.transcribe(audio_url, config)

    # Handle errors
    if transcript.status == aai.TranscriptStatus.error:
        print(f"Transcription failed: {transcript.error}")
        return

    # Format the transcript to include speaker labels and timestamps
    formatted_transcript = ""
    for utterance in transcript.utterances:
        timestamp = utterance.start_time.strftime("%H:%M:%S")
        formatted_transcript += f"{timestamp} - Speaker {utterance.speaker}: {utterance.text}\n"

    # Store the transcription results in another blob storage container
    output_container_name = "transcriptions"
    output_blob_name = f"{os.path.splitext(blob.name)[0]}_transcript.txt"
    output_blob_client = blob_service_client.get_blob_client(container=output_container_name, blob=output_blob_name)
    output_blob_client.upload_blob(formatted_transcript, overwrite=True)
