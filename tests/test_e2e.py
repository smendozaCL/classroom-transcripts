import os
import time
import pytest
from pathlib import Path
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential
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
        blob_client = container_client.upload_blob(name=blob_name, data=data)
        print(f"Uploaded test file as: {blob_name}")

    try:
        # Wait for transcription to complete (max 5 minutes)
        max_wait = 300  # 5 minutes
        start_time = time.time()
        transcription_complete = False

        while time.time() - start_time < max_wait:
            # Check transcripts container
            transcripts_container = blob_service_client.get_container_client("transcripts")
            blobs = list(transcripts_container.list_blobs())
            
            # Look for our transcript
            for blob in blobs:
                if blob_name.replace(".m4a", "") in blob.name:
                    # Found our transcript
                    transcript_blob = transcripts_container.get_blob_client(blob.name)
                    transcript_data = json.loads(transcript_blob.download_blob().readall())
                    
                    if transcript_data["status"] == "completed":
                        print(f"Found completed transcript: {blob.name}")
                        print("First utterance:", transcript_data["utterances"][0])
                        transcription_complete = True
                        break
            
            if transcription_complete:
                break
                
            print(f"Waiting for transcript... ({int(time.time() - start_time)}s)")
            time.sleep(10)

        assert transcription_complete, "Transcription did not complete within timeout"

    finally:
        # Cleanup
        print(f"Cleaning up test blob: {blob_name}")
        blob_client.delete_blob() 