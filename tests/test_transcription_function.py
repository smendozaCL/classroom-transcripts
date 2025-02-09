import os
import pytest
from pathlib import Path
import time
from azure.storage.blob import BlobServiceClient, BlobClient
import json
import assemblyai as aai
from dotenv import load_dotenv
import azure.functions as func
from src.functions.transcription_function import (
    submit_transcription,
    handle_webhook,
)
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

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
    """Ensure test container exists."""
    try:
        container_client = blob_service_client.create_container("uploads")
        print(f"Created container: uploads")
    except Exception as e:
        print(f"Container uploads already exists")
        container_client = blob_service_client.get_container_client("uploads")
    return container_client


@pytest.fixture
def test_audio_file():
    """Get the test audio file path."""
    test_file = Path(__file__).parent / "fixtures/audio/short-classroom-sample.m4a"
    if not test_file.exists():
        pytest.fail(f"Test file not found at {test_file}")
    return test_file


def test_container_setup(test_containers):
    """Test that the Azure Storage container is properly set up."""
    # Verify container exists and is accessible
    assert test_containers.exists()


def test_audio_file_upload(blob_service_client, test_containers, test_audio_file):
    """Test uploading an audio file to the uploads container."""
    # Upload test file
    blob_name = test_audio_file.name
    with open(test_audio_file, "rb") as data:
        blob_client = test_containers.upload_blob(
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


@patch("src.functions.transcription_function.aai.Transcriber")
def test_submit_transcription_placeholder(mock_transcriber_class, test_audio_file):
    """Test the submit_transcription function with a placeholder implementation."""
    # Set up mock transcriber
    mock_transcriber = MagicMock()
    mock_transcript = MagicMock()
    mock_transcript.id = "test_transcript_123"
    mock_transcriber.submit.return_value = mock_transcript
    mock_transcriber_class.return_value = mock_transcriber

    # Create a mock blob input
    mock_blob = MockInputStream(test_audio_file.name)

    # Set required environment variables for local development
    env_vars = {
        "ASSEMBLYAI_API_KEY": "test_api_key",
        "AZURE_FUNCTION_KEY": "test_function_key",
        "WEBSITE_HOSTNAME": "test.azurewebsites.net",
        "AzureWebJobsStorage": "UseDevelopmentStorage=true",
        "AZURE_STORAGE_CONNECTION_STRING": "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;",
    }
    mock_sas_token = "sv=2021-10-04&st=2025-02-09T15%3A45%3A00Z&se=2025-02-09T16%3A45%3A00Z&sr=c&sp=r&sig=mock-signature"

    # Set up the mock blob service client
    mock_service_client = MagicMock(spec=BlobServiceClient)
    mock_container_client = MagicMock()
    mock_blob_client = MagicMock()
    mock_blob_client.url = (
        f"http://127.0.0.1:10000/devstoreaccount1/uploads/{test_audio_file.name}"
    )
    mock_blob_client.container_name = "uploads"
    mock_blob_client.blob_name = test_audio_file.name
    mock_container_client.get_blob_client.return_value = mock_blob_client
    mock_service_client.get_container_client.return_value = mock_container_client

    # Update the with block to patch BlobServiceClient.from_connection_string and generate_blob_sas
    with (
        patch.dict(os.environ, env_vars, clear=True),
        patch(
            "azure.storage.blob.BlobServiceClient.from_connection_string",
            return_value=mock_service_client,
        ),
        patch("azure.storage.blob.generate_blob_sas", return_value=mock_sas_token),
    ):
        try:
            submit_transcription(mock_blob)

            # Verify transcriber was called
            mock_transcriber.submit.assert_called_once()

            # Get the config that was passed to submit
            call_args = mock_transcriber.submit.call_args
            audio_url = call_args[0][0]
            config = None
            if len(call_args[0]) > 1:
                config = call_args[0][1]
            if not config and ("config" in call_args[1]):
                config = call_args[1]["config"]
            assert config is not None, f"config is None, call_args: {call_args}"

            # Verify audio URL construction
            assert "http://127.0.0.1:10000/devstoreaccount1/uploads/" in audio_url
            assert mock_blob.name in audio_url
            assert "sig=" in audio_url  # SAS token signature
            assert "sp=r" in audio_url  # Read permission

            # Verify webhook configuration
            assert config is not None
            assert config.speaker_labels is True
            assert config.webhook_url == "https://test.azurewebsites.net/api/webhook"
            assert config.webhook_auth_header_name == "x-functions-key"
            assert config.webhook_auth_header_value == "test_function_key"

            print("\nPlaceholder test passed with the following configuration:")
            print(f"Audio URL: {audio_url.split('?')[0]}")  # Don't print the SAS token
            print(f"Webhook URL: {config.webhook_url}")
            print(f"Speaker labels enabled: {config.speaker_labels}")
            print(f"Auth header: {config.webhook_auth_header_name}")

        except Exception as e:
            pytest.fail(f"submit_transcription failed: {str(e)}")


def test_webhook_handler():
    """Test the webhook handler function."""
    env_vars = {
        "AzureWebJobsStorage": "UseDevelopmentStorage=true",
        "AZURE_STORAGE_CONNECTION_STRING": "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;",
    }
    # Set up a mock BlobServiceClient to simulate storage for webhook processing
    mock_service_client = MagicMock(spec=BlobServiceClient)
    mock_container_client = MagicMock()
    mock_blob_client = MagicMock()
    # Configure the mock blob client for the 'transcriptions' container
    mock_blob_client.url = "http://127.0.0.1:10000/devstoreaccount1/transcriptions/transcript_test_transcript_123.json"
    mock_blob_client.container_name = "transcriptions"
    mock_blob_client.blob_name = "transcript_test_transcript_123.json"
    mock_blob_client.cache_control = ""
    mock_container_client.get_blob_client.return_value = mock_blob_client
    mock_service_client.get_container_client.return_value = mock_container_client

    # Update the with block to patch the BlobServiceClient.from_connection_string
    with (
        patch.dict(os.environ, env_vars, clear=True),
        patch(
            "azure.storage.blob.BlobServiceClient.from_connection_string",
            return_value=mock_service_client,
        ),
        patch("assemblyai.Transcript.get_by_id") as mock_get_transcript,
    ):
        # Set up mocks for transcript
        class MockUtterance:
            def __init__(self):
                self.start = 0
                self.speaker = "Bot"
                self.text = "Transcription finished. Time to send to Google Docs!"

        class MockTranscript:
            def __init__(self):
                self.utterances = [MockUtterance()]
                self.audio_url = "http://example.com/audio.mp3"
                self.audio_duration = 1000
                self.speech_model = "default"
                self.status = "completed"
                self.id = "test_transcript_123"
                self.language_model = "assemblyai_default"
                self.language_code = "en_us"
                self.acoustic_model = "assemblyai_default"

        mock_transcript = MockTranscript()
        mock_get_transcript.return_value = mock_transcript

        # Create mock HttpRequest for webhook
        mock_webhook_data = {
            "status": "completed",
            "transcript_id": "test_transcript_123",
            "audio_url": "http://example.com/audio.mp3",
        }
        mock_req = MockHttpRequest(mock_webhook_data)
        response = handle_webhook(mock_req)
        assert response.status_code == 200
        response_json = json.loads(response.get_body())
        assert response_json["status"] == "success"
        assert response_json["transcript_id"] == "test_transcript_123"
        # Verify that upload_blob was called on the mock blob client
        mock_blob_client.upload_blob.assert_called_once()


def test_webhook_handler_non_completed_status():
    """Test the webhook handler with a non-completed status."""
    mock_webhook_data = {
        "status": "processing",
        "transcript_id": "test_transcript_123",
    }
    mock_req = MockHttpRequest(mock_webhook_data)

    response = handle_webhook(mock_req)
    assert response.status_code == 200


def test_full_transcription_workflow(
    blob_service_client, test_containers, test_audio_file
):
    """Test the complete transcription workflow."""
    # Upload test file
    blob_name = test_audio_file.name
    print(f"\nUploading test file: {blob_name}")
    with open(test_audio_file, "rb") as data:
        blob_client = test_containers.upload_blob(
            name=blob_name, data=data, overwrite=True
        )
    print(f"Uploaded {blob_name} to container uploads")

    # List blobs in uploads container to verify
    print("\nContents of uploads container:")
    for blob in test_containers.list_blobs():
        print(f"- {blob.name} ({blob.size} bytes)")

    # Wait and check for transcription
    print("\nWaiting for transcription to complete...")
    max_wait_time = 300  # 5 minutes
    start_time = time.time()
    transcript_found = False

    while time.time() - start_time < max_wait_time:
        print("\nChecking uploads container...")
        blobs = list(test_containers.list_blobs())
        print(f"Found {len(blobs)} blobs in uploads container")

        for blob in blobs:
            print(f"Found blob: {blob.name}")
            if blob.name.startswith("transcript_"):
                print(f"\nFound transcript: {blob.name}")
                transcript_client = test_containers.get_blob_client(blob.name)
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
                        assert "metadata" in transcript_json
                        assert "audio_url" in transcript_json["metadata"]
                        assert "duration" in transcript_json["metadata"]
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


def test_webhook_handler_placeholder():
    """Test a simple placeholder implementation of the webhook handler."""
    # Create a mock webhook request with minimal data
    mock_webhook_data = {
        "status": "completed",
        "transcript_id": "placeholder_123",
    }
    mock_req = MockHttpRequest(mock_webhook_data)

    # Mock AssemblyAI transcript
    class MockUtterance:
        def __init__(self):
            self.start = 0
            self.speaker = "Bot"
            self.text = "Transcription finished. Time to send to Google Docs!"

    class MockTranscript:
        def __init__(self):
            self.utterances = [MockUtterance()]
            self.audio_url = "http://example.com/audio.mp3"
            self.audio_duration = 1000

    # Set local development environment
    os.environ["AzureWebJobsStorage"] = "UseDevelopmentStorage=true"

    # Mock AssemblyAI API
    with patch("assemblyai.Transcript.get_by_id") as mock_get_transcript:
        mock_transcript = MockTranscript()
        mock_get_transcript.return_value = mock_transcript

        # Call the webhook handler
        try:
            response = handle_webhook(mock_req)
            assert response.status_code == 200

            # Verify response content
            response_json = json.loads(response.get_body())
            assert response_json["status"] == "success"
            assert response_json["transcript_id"] == "placeholder_123"
            assert response_json["message"] == "Transcript received and logged"

            # Verify local JSON file
            json_path = f"transcripts/transcript_placeholder_123.json"
            assert os.path.exists(json_path), f"JSON file not found at {json_path}"

            with open(json_path, "r") as f:
                stored_data = json.load(f)
                assert stored_data["transcript_id"] == "placeholder_123"
                assert stored_data["status"] == "completed"
                assert len(stored_data["utterances"]) == 1
                assert (
                    stored_data["utterances"][0]["text"]
                    == "Transcription finished. Time to send to Google Docs!"
                )
                assert (
                    stored_data["metadata"]["audio_url"]
                    == "http://example.com/audio.mp3"
                )
                assert stored_data["metadata"]["duration"] == 1000

            print("\nWebhook test passed with response:")
            print(json.dumps(response_json, indent=2))
            print("\nStored transcript data:")
            print(json.dumps(stored_data, indent=2))

            # Clean up the test file
            os.remove(json_path)
            if not os.listdir("transcripts"):
                os.rmdir("transcripts")

        except Exception as e:
            # Clean up even if test fails
            if os.path.exists(json_path):
                os.remove(json_path)
            if os.path.exists("transcripts") and not os.listdir("transcripts"):
                os.rmdir("transcripts")
            pytest.fail(f"webhook handler placeholder failed: {str(e)}")


def test_end_to_end_local():
    """Test the complete transcription workflow with local JSON storage."""
    # Set up local development environment
    os.environ["AzureWebJobsStorage"] = "UseDevelopmentStorage=true"
    os.environ["AZURE_STORAGE_SAS_URL"] = "http://example.com/container?sas=token"
    os.environ["AZURE_FUNCTION_KEY"] = "test_function_key"
    os.environ["WEBSITE_HOSTNAME"] = "test.azurewebsites.net"
    os.environ["ASSEMBLYAI_API_KEY"] = "test_api_key"

    # Create a mock audio file input
    mock_blob = MockInputStream("test-audio.m4a")

    # Mock AssemblyAI transcriber for submission
    with patch("assemblyai.Transcriber") as mock_transcriber_class:
        # Set up mock transcriber for submission
        mock_transcriber = MagicMock()
        mock_transcript = MagicMock()
        mock_transcript.id = "test_e2e_123"
        mock_transcriber.submit.return_value = mock_transcript
        mock_transcriber_class.return_value = mock_transcriber

        # Submit the transcription
        try:
            # Call the function
            from src.functions.transcription_function import submit_transcription

            submit_transcription(mock_blob)

            # Verify transcriber was called with correct config
            mock_transcriber.submit.assert_called_once()
            call_args = mock_transcriber.submit.call_args
            audio_url = call_args[0][0]  # First positional arg is the audio URL
            config = None
            if len(call_args[0]) > 1:
                config = call_args[0][1]
            if not config and ("config" in call_args[1]):
                config = call_args[1]["config"]
            assert config is not None, f"config is None, call_args: {call_args}"

            # Verify audio URL construction
            assert "http://example.com/uploads/" in audio_url
            assert mock_blob.name in audio_url
            assert "sas=token" in audio_url

            # Verify webhook configuration
            assert config.speaker_labels is True
            assert config.webhook_url == "https://test.azurewebsites.net/api/webhook"
            assert config.webhook_auth_header_name == "x-functions-key"
            assert config.webhook_auth_header_value == "test_function_key"

            print("\nSubmitted transcription with config:")
            print(f"Audio URL: {audio_url.split('?')[0]}")  # Don't print the SAS token
            print(f"Webhook URL: {config.webhook_url}")

            # Now simulate the webhook callback
            mock_webhook_data = {
                "status": "completed",
                "transcript_id": "test_e2e_123",
            }
            mock_req = MockHttpRequest(mock_webhook_data)

            # Mock the transcript retrieval
            class MockUtterance:
                def __init__(self):
                    self.start = 0
                    self.speaker = "Teacher"
                    self.text = "Welcome to today's class!"

            class MockTranscript:
                def __init__(self):
                    self.utterances = [MockUtterance()]
                    self.audio_url = "http://example.com/test-audio.m4a"
                    self.audio_duration = 1000

            # Process the webhook
            with patch("assemblyai.Transcript.get_by_id") as mock_get_transcript:
                mock_transcript = MockTranscript()
                mock_get_transcript.return_value = mock_transcript

                try:
                    # Call webhook handler
                    response = handle_webhook(mock_req)
                    assert response.status_code == 200

                    # Verify the JSON file was created
                    json_path = f"transcripts/transcript_test_e2e_123.json"
                    assert os.path.exists(json_path), (
                        f"JSON file not found at {json_path}"
                    )

                    # Read and verify the transcript
                    with open(json_path, "r") as f:
                        stored_data = json.load(f)
                        print("\nStored transcript:")
                        print(json.dumps(stored_data, indent=2))

                        assert stored_data["transcript_id"] == "test_e2e_123"
                        assert stored_data["status"] == "completed"
                        assert len(stored_data["utterances"]) == 1
                        assert (
                            stored_data["utterances"][0]["speaker"] == "Speaker Teacher"
                        )
                        assert (
                            stored_data["utterances"][0]["text"]
                            == "Welcome to today's class!"
                        )
                        assert (
                            stored_data["metadata"]["audio_url"]
                            == "http://example.com/test-audio.m4a"
                        )

                    # Clean up
                    os.remove(json_path)
                    if not os.listdir("transcripts"):
                        os.rmdir("transcripts")

                except Exception as e:
                    # Clean up even if test fails
                    if os.path.exists(json_path):
                        os.remove(json_path)
                    if os.path.exists("transcripts") and not os.listdir("transcripts"):
                        os.rmdir("transcripts")
                    pytest.fail(f"End-to-end test failed: {str(e)}")

            print("\nEnd-to-end test completed successfully!")

        except Exception as e:
            pytest.fail(f"End-to-end test failed: {str(e)}")


def test_url_construction():
    """Test that the blob URL is constructed correctly using Azure AD authentication."""
    # Mock the input blob
    mock_blob = MagicMock(spec=func.InputStream)
    mock_blob.name = "test-audio.m4a"
    mock_blob.uri = (
        "https://classroomtranscripts.blob.core.windows.net/uploads/test-audio.m4a"
    )

    # Mock environment variables
    env_vars = {
        "ASSEMBLYAI_API_KEY": "test-key",
        "AZURE_STORAGE_ACCOUNT": "classroomtranscripts",
        "WEBSITE_HOSTNAME": "test-host",
    }

    # Mock the blob client
    mock_blob_client = MagicMock(spec=BlobClient)
    mock_blob_client.url = (
        "https://classroomtranscripts.blob.core.windows.net/uploads/test-audio.m4a"
    )

    # Mock the container client
    mock_container_client = MagicMock()
    mock_container_client.get_blob_client.return_value = mock_blob_client

    # Mock the blob service client
    mock_service_client = MagicMock(spec=BlobServiceClient)
    mock_service_client.get_container_client.return_value = mock_container_client

    # Mock the credential with a token
    mock_token = MagicMock()
    mock_token.token = "mock-azure-ad-token"
    mock_credential = MagicMock()
    mock_credential.get_token.return_value = mock_token

    # Mock the transcriber
    mock_transcriber = MagicMock()
    mock_transcriber.submit.return_value = MagicMock()

    with (
        patch.dict("os.environ", env_vars),
        patch(
            "src.functions.SubmitTranscription.get_azure_credential",
            return_value=mock_credential,
        ),
        patch(
            "src.functions.SubmitTranscription.BlobServiceClient",
            return_value=mock_service_client,
        ),
        patch("assemblyai.Transcriber", return_value=mock_transcriber),
    ):
        try:
            # Call the function
            from src.functions.transcription_function import submit_transcription

            submit_transcription(mock_blob)

            # Verify the URL construction
            mock_container_client.get_blob_client.assert_called_once_with(
                "test-audio.m4a"
            )

            # Verify Azure AD token was requested
            mock_credential.get_token.assert_called_once_with(
                "https://storage.azure.com/.default"
            )

            # Get the audio_url that was passed to transcriber.submit
            call_args = mock_transcriber.submit.call_args
            if not call_args:
                pytest.fail("transcriber.submit was not called")

            audio_url = call_args[0][0]  # First positional argument
            print(f"\nConstructed audio URL: {audio_url}")

            # Verify URL components
            assert (
                "https://classroomtranscripts.blob.core.windows.net/uploads/test-audio.m4a"
                in audio_url
            )
            # Verify we're using Azure AD token
            assert "token=mock-azure-ad-token" in audio_url

        except Exception as e:
            pytest.fail(f"Test failed with error: {str(e)}")


def test_url_construction_error_handling():
    """Test that malformed URLs are caught and handled properly."""
    # Mock the input blob with a problematic URI
    mock_blob = MagicMock(spec=func.InputStream)
    mock_blob.name = "test-audio.m4a"
    mock_blob.uri = ":///uploads/test-audio.m4a"  # Malformed URI like in the error

    # Mock environment variables
    env_vars = {
        "ASSEMBLYAI_API_KEY": "test-key",
        "AZURE_STORAGE_ACCOUNT": "classroomtranscripts",
        "WEBSITE_HOSTNAME": "test-host",
    }

    # Mock the blob client
    mock_blob_client = MagicMock(spec=BlobClient)
    mock_blob_client.url = (
        "https://classroomtranscripts.blob.core.windows.net/uploads/test-audio.m4a"
    )

    # Mock the container client
    mock_container_client = MagicMock()
    mock_container_client.get_blob_client.return_value = mock_blob_client

    # Mock the blob service client
    mock_service_client = MagicMock(spec=BlobServiceClient)
    mock_service_client.get_container_client.return_value = mock_container_client

    # Mock the credential with a token
    mock_token = MagicMock()
    mock_token.token = "mock-azure-ad-token"
    mock_credential = MagicMock()
    mock_credential.get_token.return_value = mock_token

    # Mock the transcriber
    mock_transcriber = MagicMock()
    mock_transcriber.submit.return_value = MagicMock()

    with (
        patch.dict("os.environ", env_vars),
        patch(
            "src.functions.SubmitTranscription.get_azure_credential",
            return_value=mock_credential,
        ),
        patch(
            "src.functions.SubmitTranscription.BlobServiceClient",
            return_value=mock_service_client,
        ),
        patch("assemblyai.Transcriber", return_value=mock_transcriber),
    ):
        try:
            # Call the function
            from src.functions.transcription_function import submit_transcription

            submit_transcription(mock_blob)

            # Get the audio_url that was passed to transcriber.submit
            call_args = mock_transcriber.submit.call_args
            if not call_args:
                pytest.fail("transcriber.submit was not called")

            audio_url = call_args[0][0]  # First positional argument
            print(f"\nConstructed audio URL: {audio_url}")

            # Verify URL is properly formed
            assert audio_url.startswith("https://"), (
                f"URL should start with https://, got: {audio_url}"
            )
            assert "classroomtranscripts.blob.core.windows.net" in audio_url, (
                "URL should contain storage account domain"
            )
            assert "uploads/test-audio.m4a" in audio_url, "URL should contain blob path"
            assert "token=mock-azure-ad-token" in audio_url, (
                "URL should contain Azure AD token"
            )

        except Exception as e:
            pytest.fail(f"Test failed with error: {str(e)}")


def test_simple():
    """A simple test to verify our test environment."""
    assert True


def test_sas_token_generation_local():
    """Test SAS token generation in local development environment."""
    # Mock the input blob
    mock_blob = MagicMock(spec=func.InputStream)
    mock_blob.name = "test-audio.m4a"
    mock_blob.uri = "http://127.0.0.1:10000/devstoreaccount1/uploads/test-audio.m4a"

    # Set up local development environment
    env_vars = {
        "AzureWebJobsStorage": "UseDevelopmentStorage=true",
        "AZURE_STORAGE_CONNECTION_STRING": "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;",
        "ASSEMBLYAI_API_KEY": "test-key",
        "WEBSITE_HOSTNAME": "localhost:7071",
    }

    # Mock the blob client
    mock_blob_client = MagicMock(spec=BlobClient)
    mock_blob_client.url = (
        "http://127.0.0.1:10000/devstoreaccount1/uploads/test-audio.m4a"
    )

    # Mock the container client
    mock_container_client = MagicMock()
    mock_container_client.get_blob_client.return_value = mock_blob_client

    # Mock the blob service client
    mock_service_client = MagicMock(spec=BlobServiceClient)
    mock_service_client.get_container_client.return_value = mock_container_client

    # Mock the transcriber
    mock_transcriber = MagicMock()
    mock_transcriber.submit.return_value = MagicMock()

    with (
        patch.dict(os.environ, env_vars, clear=True),
        patch(
            "azure.storage.blob.BlobServiceClient.from_connection_string",
            return_value=mock_service_client,
        ),
        patch("assemblyai.Transcriber", return_value=mock_transcriber),
    ):
        try:
            # Call the function
            from src.functions.transcription_function import submit_transcription

            submit_transcription(mock_blob)

            # Get the audio_url that was passed to transcriber.submit
            call_args = mock_transcriber.submit.call_args
            if not call_args:
                pytest.fail("transcriber.submit was not called")

            audio_url = call_args[0][0]  # First positional argument
            print(f"\nConstructed audio URL: {audio_url}")

            # Verify URL components for local development
            assert audio_url.startswith(
                "http://127.0.0.1:10000/devstoreaccount1/uploads/"
            )
            assert "test-audio.m4a" in audio_url
            assert "sig=" in audio_url  # SAS token signature
            assert "se=" in audio_url  # SAS token expiry
            assert "sp=r" in audio_url  # Read permission

        except Exception as e:
            pytest.fail(f"Test failed with error: {str(e)}")


def test_sas_token_generation_production():
    """Test SAS token generation in production environment using managed identity."""
    # Mock the input blob
    mock_blob = MagicMock(spec=func.InputStream)
    mock_blob.name = "test-audio.m4a"
    mock_blob.uri = (
        "https://classroomtranscripts.blob.core.windows.net/uploads/test-audio.m4a"
    )

    # Set up production environment
    env_vars = {
        "AZURE_STORAGE_ACCOUNT": "classroomtranscripts",
        "ASSEMBLYAI_API_KEY": "test-key",
        "WEBSITE_HOSTNAME": "classroom-transcripts-func.azurewebsites.net",
    }

    # Mock the blob client
    mock_blob_client = MagicMock(spec=BlobClient)
    mock_blob_client.url = (
        "https://classroomtranscripts.blob.core.windows.net/uploads/test-audio.m4a"
    )

    # Mock the container client
    mock_container_client = MagicMock()
    mock_container_client.get_blob_client.return_value = mock_blob_client

    # Mock the blob service client
    mock_service_client = MagicMock(spec=BlobServiceClient)
    mock_service_client.get_container_client.return_value = mock_container_client

    # Mock user delegation key
    mock_delegation_key = MagicMock()
    mock_service_client.get_user_delegation_key.return_value = mock_delegation_key

    # Mock the transcriber
    mock_transcriber = MagicMock()
    mock_transcriber.submit.return_value = MagicMock()

    with (
        patch.dict(os.environ, env_vars, clear=True),
        patch("azure.identity.DefaultAzureCredential"),
        patch("azure.storage.blob.BlobServiceClient", return_value=mock_service_client),
        patch("assemblyai.Transcriber", return_value=mock_transcriber),
    ):
        try:
            # Call the function
            from src.functions.transcription_function import submit_transcription

            submit_transcription(mock_blob)

            # Verify user delegation key was requested
            mock_service_client.get_user_delegation_key.assert_called_once()
            key_args = mock_service_client.get_user_delegation_key.call_args[1]
            assert "key_start_time" in key_args
            assert "key_expiry_time" in key_args

            # Get the audio_url that was passed to transcriber.submit
            call_args = mock_transcriber.submit.call_args
            if not call_args:
                pytest.fail("transcriber.submit was not called")

            audio_url = call_args[0][0]  # First positional argument
            print(f"\nConstructed audio URL: {audio_url}")

            # Verify URL components for production
            assert audio_url.startswith(
                "https://classroomtranscripts.blob.core.windows.net/uploads/"
            )
            assert "test-audio.m4a" in audio_url
            assert "sig=" in audio_url  # SAS token signature
            assert "se=" in audio_url  # SAS token expiry
            assert "sp=r" in audio_url  # Read permission
            assert "skoid=" in audio_url  # User delegation key components

        except Exception as e:
            pytest.fail(f"Test failed with error: {str(e)}")
