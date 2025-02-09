import os
import time
import pytest
from pathlib import Path
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.identity import DefaultAzureCredential
import assemblyai as aai
import requests
import json
from unittest.mock import patch, MagicMock


@pytest.mark.skipif(
    os.getenv("CI") == "true", reason="Skip local e2e tests in CI environment"
)
def test_e2e_transcription(monkeypatch):
    """End-to-end test of the transcription function using local storage."""
    # Force local storage for testing
    monkeypatch.setenv("AZURE_STORAGE_ACCOUNT", "devstoreaccount1")

    # Use local storage
    account_url = "http://127.0.0.1:10000/devstoreaccount1"
    blob_service_client = BlobServiceClient.from_connection_string(
        "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
    )

    # Create container if it doesn't exist
    try:
        container_client = blob_service_client.get_container_client("uploads")
        container_client.create_container()
        print("\n=== Created 'uploads' container ===")
    except Exception as e:
        print(f"\n=== Container 'uploads' already exists: {str(e)} ===")
        container_client = blob_service_client.get_container_client("uploads")

    # Get test audio file
    test_file = (
        Path(__file__).parent.parent / "fixtures/audio/short-classroom-sample.m4a"
    )
    assert test_file.exists(), f"Test file not found at {test_file}"

    # Upload to blob storage
    blob_name = f"e2e_test_{int(time.time())}.m4a"

    with open(test_file, "rb") as data:
        file_data = data.read()
        file_size = len(file_data)
        print("\n=== Upload Details ===")
        print(f"File: {test_file}")
        print(f"Size: {file_size:,} bytes")

        # Set content type explicitly for audio files
        blob_client = container_client.get_blob_client(blob_name)
        blob_client.upload_blob(
            data=file_data, content_settings=ContentSettings(content_type="audio/x-m4a")
        )

        # Verify upload
        properties = blob_client.get_blob_properties()
        print("\n=== Blob Properties ===")
        print(f"Name: {blob_name}")
        print(f"Content Type: {properties.content_settings.content_type}")
        print(f"Size: {properties.size:,} bytes")
        print(f"Created: {properties.creation_time}")
        print(f"URL: {blob_client.url}")
        print("=====================\n")

    try:
        print("Starting transcription process...")
        max_wait = 300  # 5 minutes
        start_time = time.time()
        check_count = 0

        # Configure AssemblyAI client
        api_key = os.getenv("ASSEMBLYAI_API_KEY")
        if not api_key:
            pytest.skip("ASSEMBLYAI_API_KEY not found in environment variables")
        aai.settings.api_key = api_key

        # Submit transcription directly using the local file
        print("\nSubmitting transcription request...")
        transcriber = aai.Transcriber()
        transcript = transcriber.transcribe(str(test_file))

        # Ensure we have a transcript ID
        assert transcript.id is not None, "Failed to get transcript ID"
        transcript_id: str = transcript.id

        # Wait for completion with timeout
        while transcript.status not in ["completed", "error"]:
            if time.time() - start_time > max_wait:
                pytest.fail("Transcription timed out after 5 minutes")
            time.sleep(10)
            transcript = aai.Transcript.get_by_id(transcript_id)

        if transcript.status == "error":
            print(f"\n❌ Error: {getattr(transcript, 'error', 'Unknown error')}")
            raise ValueError(
                f"Transcription failed: {getattr(transcript, 'error', 'Unknown error')}"
            )
        elif transcript.status == "completed":
            print("\n=== Transcription Complete ===")
            print(f"ID: {transcript.id}")
            print(f"Status: {transcript.status}")
            if hasattr(transcript, "audio_duration"):
                print(f"Duration: {transcript.audio_duration}s")
            if hasattr(transcript, "utterances") and transcript.utterances is not None:
                print(f"Total Utterances: {len(transcript.utterances)}")
                if transcript.utterances:
                    print("\nFirst utterance:")
                    utterance = transcript.utterances[0]
                    print(f"Speaker: {getattr(utterance, 'speaker', 'N/A')}")
                    print(f"Text: {getattr(utterance, 'text', 'N/A')}")
            return  # Success!

    finally:
        # Cleanup
        print(f"\n=== Cleanup ===")
        print(f"Deleting test blob: {blob_name}")
        blob_client.delete_blob()
        print("Cleanup complete")
