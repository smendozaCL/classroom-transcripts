"""Test fixtures module for loading and providing test data."""

import json
from pathlib import Path
from typing import Dict, Any

# Get the fixtures directory
FIXTURES_DIR = Path(__file__).parent


def load_json_fixture(filename: str) -> Dict[str, Any]:
    """
    Load a JSON fixture file.

    Args:
        filename: Name of the JSON file in the responses directory

    Returns:
        Dictionary containing the JSON data
    """
    file_path = FIXTURES_DIR / "responses" / filename
    with open(file_path, "r") as f:
        return json.load(f)


def get_assemblyai_completed_response() -> Dict[str, Any]:
    """Get the sample completed AssemblyAI response."""
    return load_json_fixture("assemblyai_completed.json")


def get_assemblyai_error_response() -> Dict[str, Any]:
    """Get the sample error AssemblyAI response."""
    return load_json_fixture("assemblyai_error.json")


def get_azure_storage_response() -> Dict[str, Any]:
    """Get the sample Azure Storage response."""
    return load_json_fixture("azure_storage.json")


def get_test_audio_path() -> Path:
    """Get the path to the test audio file."""
    return FIXTURES_DIR / "audio" / "short-classroom-sample.m4a"


def get_invalid_audio_path() -> Path:
    """Get the path to the invalid test audio file."""
    return FIXTURES_DIR / "audio" / "invalid.wav"


def get_empty_audio_path() -> Path:
    """Get the path to the empty test audio file."""
    return FIXTURES_DIR / "audio" / "empty.wav"
