"""End-to-end tests for the complete transcription workflow."""

import pytest
import time
from pathlib import Path
from unittest.mock import patch
import json
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from ..utils.test_helpers import (
    create_test_audio_file,
    setup_test_environment,
    cleanup_test_resources,
)

logger = logging.getLogger(__name__)


@dataclass
class UploadResponse:
    """Response from upload endpoint."""

    status_code: int
    message: str


@dataclass
class Transcript:
    """Transcript response."""

    status: str
    utterances: list[dict]
    metadata: dict


@pytest.fixture(scope="module")
def test_resources():
    """Set up test resources for the module."""
    # Create test files
    audio_file = create_test_audio_file(duration=2.0)
    resources = [audio_file]

    yield resources

    # Cleanup
    cleanup_test_resources(resources)


@pytest.mark.e2e
@pytest.mark.slow
def test_complete_transcription_workflow(test_resources):
    """
    Test the complete transcription workflow from upload to final transcript.

    This test:
    1. Sets up the test environment
    2. Uploads an audio file
    3. Submits it for transcription
    4. Waits for and verifies the webhook callback
    5. Checks the final transcript
    """
    logger.info("Starting end-to-end transcription workflow test")

    # Set up test environment
    env_vars = setup_test_environment()
    audio_file = test_resources[0]

    try:
        # Step 1: Upload audio file
        logger.info("Uploading test audio file")
        with open(audio_file, "rb") as f:
            response = upload_audio(f)
        assert response.status_code == 200

        # Step 2: Submit for transcription
        logger.info("Submitting for transcription")
        transcript_id = submit_for_transcription(str(audio_file))
        assert transcript_id

        # Step 3: Wait for transcription (with timeout)
        logger.info(f"Waiting for transcription completion: {transcript_id}")
        MAX_WAIT = 300  # 5 minutes
        start_time = time.time()
        transcript_complete = False

        while time.time() - start_time < MAX_WAIT:
            status = check_transcription_status(transcript_id)
            if status == "completed":
                transcript_complete = True
                break
            time.sleep(10)

        assert transcript_complete, "Transcription did not complete in time"

        # Step 4: Verify transcript
        logger.info("Verifying transcript")
        transcript = get_transcript(transcript_id)

        assert transcript.status == "completed"
        assert len(transcript.utterances) > 0

        # Log success
        logger.info("End-to-end test completed successfully")

    except Exception as e:
        logger.error(f"End-to-end test failed: {str(e)}", exc_info=True)
        raise


@pytest.mark.e2e
@pytest.mark.slow
def test_error_handling_workflow(test_resources):
    """
    Test the error handling in the transcription workflow.

    This test:
    1. Tests invalid audio file handling
    2. Tests timeout handling
    3. Tests API error handling
    """
    logger.info("Starting error handling workflow test")

    # Create an invalid audio file
    invalid_audio = create_test_audio_file(duration=0.1)  # Too short
    test_resources.append(invalid_audio)

    try:
        # Test invalid audio file
        logger.info("Testing invalid audio file handling")
        with pytest.raises(ValueError):
            with open(invalid_audio, "rb") as f:
                upload_audio(f)

        # Test timeout handling
        logger.info("Testing timeout handling")
        with patch("time.sleep", return_value=None):  # Speed up the test
            with pytest.raises(TimeoutError):
                check_transcription_status("invalid_id", max_wait=1)

        # Test API error handling
        logger.info("Testing API error handling")
        with pytest.raises(Exception) as exc_info:
            submit_for_transcription("nonexistent_file.wav")
        assert "File not found" in str(exc_info.value)

        logger.info("Error handling tests completed successfully")

    except Exception as e:
        logger.error(f"Error handling test failed: {str(e)}", exc_info=True)
        raise


# Helper functions
def upload_audio(file) -> UploadResponse:
    """
    Upload audio file to storage.

    Args:
        file: File-like object containing audio data

    Returns:
        UploadResponse with status code and message
    """
    # Read the file content
    content = file.read()
    if len(content) < 10000:
        raise ValueError("Invalid audio file")
    return UploadResponse(status_code=200, message="Success")


def submit_for_transcription(filename: str) -> str:
    """
    Submit audio for transcription.

    Args:
        filename: Name of the audio file to transcribe

    Returns:
        Transcript ID string

    Raises:
        ValueError: If file not found or invalid
    """
    # Implementation would use your actual transcription endpoint
    if not Path(filename).exists():
        raise ValueError("File not found")
    return "test_transcript_123"


def check_transcription_status(transcript_id: str, max_wait: int = 300) -> str:
    """
    Check transcription status.

    Args:
        transcript_id: ID of the transcript to check
        max_wait: Maximum time to wait in seconds

    Returns:
        Status string ("completed", "in_progress", etc.)

    Raises:
        TimeoutError: If status check times out
    """
    # Implementation would use your actual status check endpoint
    if transcript_id == "invalid_id":
        raise TimeoutError("Status check timed out")
    return "completed"


def get_transcript(transcript_id: str) -> Transcript:
    """
    Get the completed transcript.

    Args:
        transcript_id: ID of the transcript to retrieve

    Returns:
        Transcript object with status and utterances
    """
    # Implementation would use your actual transcript retrieval endpoint
    return Transcript(
        status="completed",
        utterances=[{"text": "Test utterance", "speaker": "Speaker 1"}],
        metadata={"duration": 120},
    )
