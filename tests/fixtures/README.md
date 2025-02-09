# Test Fixtures

This directory contains test fixtures and sample data used in tests.

## Directory Structure

```
fixtures/
├── audio/          # Sample audio files for testing
├── responses/      # Sample API responses
└── data/          # Other test data
```

## Audio Files

- `short-classroom-sample.m4a`: 5-second sample of classroom audio
- `empty.wav`: Empty audio file for error testing
- `invalid.wav`: Corrupted audio file for error testing

## API Response Samples

JSON files containing sample responses from:

- AssemblyAI API
- Azure Storage API

## Usage

Import fixtures in tests using the pytest fixture system:

```python
def test_transcription(test_audio_file):
    # test_audio_file fixture provides the path to sample audio
    assert test_audio_file.exists()
```

## Adding New Fixtures

1. Add the fixture file to the appropriate subdirectory
2. Document the fixture in this README
3. Create a corresponding fixture function in `conftest.py`
4. Add any necessary cleanup in the fixture teardown
