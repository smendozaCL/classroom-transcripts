# Test Data

This directory contains test data files used in various test suites.

## Directory Structure

```
data/
├── audio/              # Audio test files
│   ├── short-classroom-sample.m4a  # Short classroom recording (1.5MB)
│   └── long-classroom-sample.m4a   # Long classroom recording (23MB)
└── fixtures/           # Test fixtures and mock data
```

## Audio Files

### short-classroom-sample.m4a
- Size: 1.5MB
- Duration: ~1 minute
- Content: Short classroom discussion sample
- Used in: Unit tests, integration tests

### long-classroom-sample.m4a
- Size: 23MB
- Duration: ~15 minutes
- Content: Extended classroom lecture sample
- Used in: End-to-end tests

## Usage

These test files are used across different test suites:

1. Unit Tests (`tests/unit/`)
   - Testing audio file processing
   - Validating file format handling

2. Integration Tests (`tests/integration/`)
   - Testing Azure Blob Storage operations
   - Testing AssemblyAI transcription submission

3. End-to-End Tests (`tests/e2e/`)
   - Full workflow testing from upload to transcription
   - Performance testing with different file sizes

## Adding New Test Data

When adding new test data:

1. Place files in appropriate subdirectories
2. Update this README with file details
3. Document usage in relevant test files
4. Consider file size and test execution time
5. Include sample output if applicable 