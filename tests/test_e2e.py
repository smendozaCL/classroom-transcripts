import os
import time
import pytest
from pathlib import Path
from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.identity import DefaultAzureCredential
import assemblyai as aai
import requests
import json


def test_e2e_transcription():
    """End-to-end test of the transcription function in production."""
    # Get credentials and create blob client
    credential = DefaultAzureCredential()
    storage_account = os.getenv("AZURE_STORAGE_ACCOUNT")
    account_url = f"https://{storage_account}.blob.core.windows.net"
    blob_service_client = BlobServiceClient(account_url, credential=credential)

    # Get test audio file
    test_file = Path("data/short-classroom-sample.m4a")
    assert test_file.exists(), "Test file not found"

    # Upload to blob storage
    container_client = blob_service_client.get_container_client("uploads")
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

        # Initialize AssemblyAI API
        api_key = os.getenv("ASSEMBLYAI_API_KEY")
        if not api_key:
            raise ValueError("ASSEMBLYAI_API_KEY not found in environment variables")
        headers = {"authorization": api_key}

        # Wait for the Azure function to process and submit to AssemblyAI
        print("\nWaiting for Azure function to process upload...")
        time.sleep(10)  # Give the function time to process

        # Start checking AssemblyAI for the transcript
        while time.time() - start_time < max_wait:
            check_count += 1
            print(f"\nCheck #{check_count} - Elapsed: {int(time.time() - start_time)}s")

            # List recent transcripts from AssemblyAI
            response = requests.get(
                "https://api.assemblyai.com/v2/transcript", headers=headers
            )
            if response.status_code != 200:
                print(f"❌ Error getting transcripts: {response.status_code}")
                print(response.text)
                continue

            transcripts = response.json()["transcripts"]
            print(f"Found {len(transcripts)} recent transcripts")

            # Look for our transcript
            for transcript in transcripts:
                print(f"\n=== Checking Transcript {transcript['id']} ===")
                print(f"Status: {transcript['status']}")
                if "audio_url" in transcript:
                    print(f"Audio URL: {transcript['audio_url']}")

                if blob_name in transcript.get("audio_url", ""):
                    print("\n=== Found Our Transcript ===")
                    print(f"ID: {transcript['id']}")
                    print(f"Status: {transcript['status']}")
                    if "audio_duration" in transcript:
                        print(f"Duration: {transcript['audio_duration']}s")

                    if transcript["status"] == "completed":
                        print("\n=== Transcription Complete ===")
                        # Get full transcript details
                        transcript_response = requests.get(
                            f"https://api.assemblyai.com/v2/transcript/{transcript['id']}",
                            headers=headers,
                        )
                        if transcript_response.status_code == 200:
                            full_transcript = transcript_response.json()
                            if "utterances" in full_transcript:
                                print(
                                    f"Total Utterances: {len(full_transcript['utterances'])}"
                                )
                                if full_transcript["utterances"]:
                                    print("\nFirst utterance:")
                                    utterance = full_transcript["utterances"][0]
                                    print(f"Speaker: {utterance.get('speaker', 'N/A')}")
                                    print(f"Text: {utterance.get('text', 'N/A')}")
                        return  # Success!
                    elif transcript["status"] == "error":
                        print(f"\n❌ Error: {transcript.get('error', 'Unknown error')}")
                        raise ValueError(
                            f"Transcription failed: {transcript.get('error', 'Unknown error')}"
                        )
                    else:
                        print(f"Status not complete yet: {transcript['status']}")
                        break  # Found our transcript but not complete, keep waiting

            print(f"\nWaiting 10s before next check...")
            time.sleep(10)

        print(f"\n❌ Transcription did not complete within {max_wait} seconds")
        raise TimeoutError("Transcription did not complete within timeout")

    finally:
        # Cleanup
        print(f"\n=== Cleanup ===")
        print(f"Deleting test blob: {blob_name}")
        blob_client.delete_blob()
        print("Cleanup complete")
