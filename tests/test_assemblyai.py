import os
import pytest
import assemblyai as aai
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential
import time
from pathlib import Path
from io import BytesIO
import json

# Load environment variables
load_dotenv(".env.local")


@pytest.fixture
def blob_service_client():
    """Create a blob service client for testing."""
    storage_account = os.getenv("AZURE_STORAGE_ACCOUNT")
    if not storage_account:
        pytest.skip("AZURE_STORAGE_ACCOUNT not found in environment variables")

    # Get Azure credential
    credential = DefaultAzureCredential()
    account_url = f"https://{storage_account}.blob.core.windows.net"
    return BlobServiceClient(account_url, credential=credential)


@pytest.fixture
def test_containers(blob_service_client):
    """Ensure test container exists."""
    try:
        container_client = blob_service_client.create_container("uploads")
        print(f"Created container: uploads")
    except Exception as e:
        print(f"Container uploads already exists")
        container_client = blob_service_client.get_container_client("uploads")
    return container_client


@pytest.mark.integration
def test_assemblyai_integration():
    """Integration test for AssemblyAI API connectivity using local file.
    This test makes actual API calls and should be run separately from unit tests.
    """
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        pytest.skip("ASSEMBLYAI_API_KEY not found in environment variables")

    print(f"\nTesting AssemblyAI API key: {api_key[:4]}...{api_key[-4:]}")
    aai.settings.api_key = api_key

    # Create a transcriber instance
    transcriber = aai.Transcriber()

    # Test with our local test audio file
    test_file = Path("data/short-classroom-sample.m4a")
    if not test_file.exists():
        pytest.skip("Test audio file not found")

    print(f"\nSubmitting test transcription for local file: {test_file}")

    try:
        transcript = transcriber.transcribe(str(test_file))
        assert transcript.status != "error", f"Transcription failed: {transcript.error}"
        assert transcript.text, "Transcript text is empty"

        print("\nTranscription successful!")
        print(f"Transcript ID: {transcript.id}")
        print(f"Status: {transcript.status}")
        print(f"Text: {transcript.text}")
    except Exception as e:
        pytest.fail(f"AssemblyAI API test failed: {str(e)}")


@pytest.mark.integration
def test_azure_blob_transcription():
    """Integration test for transcribing audio from Azure blob storage.
    Tests the complete flow using Azure AD authentication.
    """
    # Check required environment variables
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    storage_account = os.getenv("AZURE_STORAGE_ACCOUNT")
    if not api_key or not storage_account:
        pytest.skip("Required environment variables not found")

    print(f"\nTesting Azure blob transcription with storage account: {storage_account}")
    aai.settings.api_key = api_key

    try:
        # Get Azure credential
        credential = DefaultAzureCredential()

        # Create BlobServiceClient
        account_url = f"https://{storage_account}.blob.core.windows.net"
        blob_service_client = BlobServiceClient(account_url, credential=credential)

        # Get the uploads container
        container_client = blob_service_client.get_container_client("uploads")

        # Get a test audio file (use the first .m4a or .mp3 file found)
        audio_files = [
            blob
            for blob in container_client.list_blobs()
            if blob.name.endswith((".m4a", ".mp3"))
        ]

        if not audio_files:
            pytest.skip("No audio files found in uploads container")

        test_blob = audio_files[0]
        blob_client = container_client.get_blob_client(test_blob.name)

        # Download the blob content
        print(f"\nDownloading blob: {test_blob.name}")
        blob_data = blob_client.download_blob().readall()

        # Upload to AssemblyAI
        print("\nUploading to AssemblyAI...")
        transcriber = aai.Transcriber()
        transcript = transcriber.transcribe(BytesIO(blob_data))

        # Verify transcription
        assert transcript.status != "error", f"Transcription failed: {transcript.error}"
        assert transcript.text, "Transcript text is empty"

        print("\nAzure blob transcription successful!")
        print(f"Transcript ID: {transcript.id}")
        print(f"Audio file: {test_blob.name}")
        print(f"Text preview: {transcript.text[:200]}...")

    except Exception as e:
        pytest.fail(f"Azure blob transcription test failed: {str(e)}")


@pytest.mark.integration
def test_blob_trigger_transcription():
    """Integration test for the blob trigger function.
    Tests that uploading an audio file to the blob storage triggers a transcription request.
    """
    # Check required environment variables
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    storage_account = os.getenv("AZURE_STORAGE_ACCOUNT")
    if not api_key or not storage_account:
        pytest.skip("Required environment variables not found")

    print(f"\nTesting blob trigger with storage account: {storage_account}")

    try:
        # Get Azure credential
        credential = DefaultAzureCredential()
        print("Successfully obtained Azure credential")

        # Create BlobServiceClient
        account_url = f"https://{storage_account}.blob.core.windows.net"
        blob_service_client = BlobServiceClient(account_url, credential=credential)
        print(f"Connected to blob storage at {account_url}")

        # Get the uploads container
        uploads_container = blob_service_client.get_container_client("uploads")
        if not uploads_container.exists():
            pytest.skip("Uploads container does not exist")
        print("Found uploads container")

        # Use a test audio file
        test_file = Path("data/short-classroom-sample.m4a")
        if not test_file.exists():
            pytest.skip("Test audio file not found")
        print(f"Found test file: {test_file}")

        # Generate a unique blob name
        timestamp = int(time.time())
        blob_name = f"test-trigger-{timestamp}.m4a"
        print(f"\nUploading test file as: {blob_name}")

        # Upload the test file
        with open(test_file, "rb") as data:
            blob_client = uploads_container.upload_blob(name=blob_name, data=data)
            print(f"Successfully uploaded blob to: {blob_client.url}")

        # Wait for the function to process and create a transcript
        max_wait_time = 180  # 3 minutes
        start_time = time.time()
        transcription_started = False

        print("\nWaiting for transcription file to appear...")
        transcripts_dir = Path("transcripts")
        while time.time() - start_time < max_wait_time:
            try:
                # Check if transcripts directory exists
                if transcripts_dir.exists():
                    # List all transcript files
                    transcript_files = list(transcripts_dir.glob("transcript_*.json"))

                    if transcript_files:
                        print(
                            f"\nFound transcript files: {[f.name for f in transcript_files]}"
                        )
                        # Read the most recent transcript file
                        latest_transcript = max(
                            transcript_files, key=lambda x: x.stat().st_mtime
                        )
                        with open(latest_transcript) as f:
                            transcript_data = json.load(f)
                            print(f"\nTranscript content preview:")
                            print(
                                f"Transcript ID: {transcript_data.get('transcript_id')}"
                            )
                            print(f"Status: {transcript_data.get('status')}")
                            if transcript_data.get("utterances"):
                                print(
                                    f"First utterance: {transcript_data['utterances'][0]}"
                                )
                        transcription_started = True
                        break

            except Exception as e:
                print(f"\nError checking status: {str(e)}")

            time.sleep(10)  # Check every 10 seconds
            elapsed = int(time.time() - start_time)
            print(f"Elapsed time: {elapsed}s / {max_wait_time}s", end="\r", flush=True)

        if transcription_started:
            print("\nBlob trigger processed the file successfully!")
        else:
            print("\nTimeout reached. Transcript file was not created.")
            if transcripts_dir.exists():
                print("\nCurrent transcripts directory contents:")
                for file in transcripts_dir.glob("*"):
                    print(f"- {file.name}")

        assert transcription_started, (
            "Blob trigger did not process the file within the expected time"
        )

    except Exception as e:
        pytest.fail(f"Blob trigger test failed: {str(e)}")
    finally:
        # Cleanup: Try to delete the test blob if it still exists
        try:
            blob_client.delete_blob()
            print(f"Cleaned up test blob: {blob_name}")
        except Exception as e:
            print(f"Cleanup error (can ignore): {str(e)}")


if __name__ == "__main__":
    # When run as a script, execute the tests and print results
    try:
        test_assemblyai_integration()
        test_azure_blob_transcription()
        test_blob_trigger_transcription()
        print("\nAll integration tests passed!")
    except Exception as e:
        print(f"\nIntegration tests failed: {str(e)}")
        exit(1)
