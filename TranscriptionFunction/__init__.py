import os
import azure.functions as func
import assemblyai as aai
from azure.storage.blob import BlobClient
from urllib.parse import urlparse


def main(blob: func.InputStream):
    # Set AssemblyAI API key
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key or api_key.startswith("$"):
        raise ValueError("Please set ASSEMBLYAI_API_KEY with your actual API key")
    aai.settings.api_key = api_key

    # Get Azure Storage SAS URLs
    source_sas_url = os.getenv("AZURE_STORAGE_SAS_URL")
    target_sas_url = os.getenv("AZURE_STORAGE_TARGET_SAS_URL")
    if not source_sas_url or source_sas_url.startswith("$"):
        raise ValueError("Please set AZURE_STORAGE_SAS_URL with your actual SAS URL")
    if not target_sas_url or target_sas_url.startswith("$"):
        raise ValueError(
            "Please set AZURE_STORAGE_TARGET_SAS_URL with your actual SAS URL"
        )

    # Use the AssemblyAI API to transcribe the audio file
    transcriber = aai.Transcriber()
    config = aai.TranscriptionConfig(speaker_labels=True)
    transcript = transcriber.transcribe(blob.uri, config)

    # Handle errors
    if transcript.status == aai.TranscriptStatus.error:
        print(f"Transcription failed: {transcript.error}")
        return

    # Format the transcript to include speaker labels and timestamps
    formatted_transcript = ""
    if transcript.utterances:
        for utterance in transcript.utterances:
            start_time = int(utterance.start / 1000)  # Convert to seconds
            hours = start_time // 3600
            minutes = (start_time % 3600) // 60
            seconds = start_time % 60
            timestamp = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            formatted_transcript += (
                f"{timestamp} - Speaker {utterance.speaker}: {utterance.text}\n"
            )

    # Parse the target SAS URL
    parsed_url = urlparse(target_sas_url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

    # Store the transcription results in the target container
    output_container_name = "transcriptions"
    output_blob_name = f"{os.path.splitext(blob.name)[0]}_transcript.txt"

    # Construct the full blob URL with SAS token
    output_blob_url = (
        f"{base_url}/{output_container_name}/{output_blob_name}?{parsed_url.query}"
    )

    # Create blob client with SAS URL
    output_blob_client = BlobClient.from_blob_url(output_blob_url)

    # Upload the formatted transcript
    output_blob_client.upload_blob(formatted_transcript, overwrite=True)
