import os
import pytest
from pathlib import Path
import time
from azure.storage.blob import BlobServiceClient
import json
import assemblyai as aai
from dotenv import load_dotenv
import azure.functions as func
from src.classroom_transcripts.transcription_function import (
    submit_transcription,
    handle_webhook,
)
from unittest.mock import patch, MagicMock

# Load environment variables from .env.local
load_dotenv(".env.local")


# Mock classes for Azure Functions
class MockInputStream(func.InputStream):
    def __init__(self, name):
        self._name = name
        self._bytes = b""  # Empty bytes for testing
        self._length = 0
        self._uri = f"http://localhost/api/audio/{name}"

    @property
    def name(self) -> str:
        return self._name

    @property
    def length(self) -> int:
        return self._length

    @property
    def uri(self) -> str:
        return self._uri

    def read(self) -> bytes:
        return self._bytes

    def seek(self, offset: int, whence: int) -> None:
        pass

    def close(self) -> None:
        pass


class MockHttpRequest(func.HttpRequest):
    def __init__(self, body):
        self._body = json.dumps(body).encode("utf-8")
        self._json = body
        super().__init__(
            method="POST",
            url="http://localhost/api/webhook",
            body=self._body,
            params={},
            headers={},
        )

    def get_json(self):
        return self._json


@pytest.fixture
def blob_service_client():
    """Create a blob service client for testing."""
    connection_string = "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
    return BlobServiceClient.from_connection_string(connection_string)


@pytest.fixture
def test_containers(blob_service_client):
    """Ensure test containers exist."""
    containers = []
    for container_name in ["uploads", "transcriptions"]:
        try:
            container_client = blob_service_client.create_container(container_name)
            print(f"Created container: {container_name}")
        except Exception as e:
            print(f"Container {container_name} already exists")
            container_client = blob_service_client.get_container_client(container_name)
        containers.append(container_client)
    return containers


@pytest.fixture
def test_audio_file():
    """Get the test audio file path."""
    test_file = Path("data/short-classroom-sample.m4a")
    if not test_file.exists():
        pytest.fail(f"Test file not found at {test_file}")
    return test_file


def test_container_setup(test_containers):
    """Test that the Azure Storage containers are properly set up."""
    uploads_container, transcriptions_container = test_containers

    # Verify containers exist and are accessible
    assert uploads_container.exists()
    assert transcriptions_container.exists()


def test_audio_file_upload(blob_service_client, test_containers, test_audio_file):
    """Test uploading an audio file to the uploads container."""
    uploads_container = test_containers[0]

    # Upload test file
    blob_name = test_audio_file.name
    with open(test_audio_file, "rb") as data:
        blob_client = uploads_container.upload_blob(
            name=blob_name, data=data, overwrite=True
        )

    # Verify upload
    blob_properties = blob_client.get_blob_properties()
    assert blob_properties.size > 0
    print(f"Uploaded {blob_name} ({blob_properties.size} bytes) to container uploads")


def test_assemblyai_configuration():
    """Test AssemblyAI API configuration."""
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    assert api_key is not None, "ASSEMBLYAI_API_KEY not found in environment variables"

    # Test API key validity
    aai.settings.api_key = api_key
    transcriber = aai.Transcriber()
    assert transcriber is not None


def test_submit_transcription_function(test_audio_file):
    """Test the submit_transcription function."""
    # Create a mock blob input using our MockInputStream
    mock_blob = MockInputStream(test_audio_file.name)

    # Call the function
    try:
        submit_transcription(mock_blob)
    except Exception as e:
        pytest.fail(f"submit_transcription failed: {str(e)}")


def test_webhook_handler():
    """Test the webhook handler function."""
    # Set up AssemblyAI API key
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    assert api_key is not None, "ASSEMBLYAI_API_KEY not found in environment variables"
    aai.settings.api_key = api_key

    # Create mock transcript data
    class MockUtterance:
        def __init__(self, start, speaker, text):
            self.start = start
            self.speaker = speaker
            self.text = text

        def to_dict(self):
            return {"start": self.start, "speaker": self.speaker, "text": self.text}

    class MockTranscript:
        def __init__(self):
            self.utterances = [
                MockUtterance(
                    start=1000,  # 1 second
                    speaker="A",
                    text="Hello, this is a test.",
                )
            ]
            self.audio_url = "http://example.com/audio.mp3"
            self.language = "en"
            self.audio_duration = 5000  # 5 seconds
            self.created = "2024-02-08T00:00:00Z"

        def to_dict(self):
            return {
                "utterances": [u.to_dict() for u in self.utterances],
                "audio_url": self.audio_url,
                "language": self.language,
                "audio_duration": self.audio_duration,
                "created": self.created,
            }

    # Create a mock webhook request
    mock_webhook_data = {
        "status": "completed",
        "transcript_id": "test_transcript_123",
        "audio_url": "http://example.com/audio.mp3",
    }

    # Use our MockHttpRequest
    mock_req = MockHttpRequest(mock_webhook_data)

    # Mock the AssemblyAI transcriber and Azure Storage
    with (
        patch("assemblyai.Transcriber") as mock_transcriber_class,
        patch("azure.storage.blob.BlobClient.from_blob_url") as mock_blob_client_class,
    ):
        # Mock AssemblyAI
        mock_transcriber = MagicMock()
        mock_transcript = MockTranscript()
        mock_transcriber.transcripts = MagicMock()
        mock_transcriber.transcripts.get.return_value = mock_transcript
        mock_transcriber_class.return_value = mock_transcriber

        # Mock Azure Storage
        mock_blob_client = MagicMock()
        mock_blob_client.upload_blob.return_value = None
        mock_blob_client_class.return_value = mock_blob_client

        # Set up environment variables
        os.environ["AZURE_STORAGE_SAS_URL"] = "http://example.com/container?sas=token"

        # Call the webhook handler
        try:
            response = handle_webhook(mock_req)
            assert response.status_code == 200

            # Verify response content
            response_json = json.loads(response.get_body())
            assert response_json["status"] == "success"
            assert response_json["transcript_id"] == "test_transcript_123"

            # Verify Azure Storage interaction
            mock_blob_client.upload_blob.assert_called_once()
            upload_data = json.loads(mock_blob_client.upload_blob.call_args[0][0])
            assert upload_data["transcript_id"] == "test_transcript_123"
            assert upload_data["status"] == "completed"
            assert len(upload_data["utterances"]) > 0
        except Exception as e:
            pytest.fail(f"handle_webhook failed: {str(e)}")


def test_full_transcription_workflow(
    blob_service_client, test_containers, test_audio_file
):
    """Test the complete transcription workflow."""
    uploads_container, transcriptions_container = test_containers

    # Upload test file
    blob_name = test_audio_file.name
    print(f"\nUploading test file: {blob_name}")
    with open(test_audio_file, "rb") as data:
        blob_client = uploads_container.upload_blob(
            name=blob_name, data=data, overwrite=True
        )
    print(f"Uploaded {blob_name} to container uploads")

    # List blobs in uploads container to verify
    print("\nContents of uploads container:")
    for blob in uploads_container.list_blobs():
        print(f"- {blob.name} ({blob.size} bytes)")

    # Wait and check for transcription
    print("\nWaiting for transcription to complete...")
    max_wait_time = 300  # 5 minutes
    start_time = time.time()
    transcript_found = False

    while time.time() - start_time < max_wait_time:
        print("\nChecking transcriptions container...")
        blobs = list(transcriptions_container.list_blobs())
        print(f"Found {len(blobs)} blobs in transcriptions container")

        for blob in blobs:
            print(f"Found blob: {blob.name}")
            if blob.name.startswith(os.path.splitext(blob_name)[0]):
                print(f"\nFound transcript: {blob.name}")
                transcript_client = transcriptions_container.get_blob_client(blob.name)
                transcript_data = transcript_client.download_blob().readall()
                try:
                    transcript_json = json.loads(transcript_data)
                    if "utterances" in transcript_json:
                        for utterance in transcript_json["utterances"]:
                            print(
                                f"{utterance['timestamp']} - {utterance['speaker']}: {utterance['text']}"
                            )
                        assert "transcript_id" in transcript_json
                        assert "status" in transcript_json
                        assert transcript_json["status"] == "completed"
                    transcript_found = True
                    break
                except json.JSONDecodeError:
                    print(f"Transcript content: {transcript_data.decode()}")
                    transcript_found = True
                    break

        if transcript_found:
            break
        time.sleep(10)  # Check every 10 seconds
        print(f"Time elapsed: {int(time.time() - start_time)} seconds")

    assert transcript_found, "Transcription was not completed within the expected time"
