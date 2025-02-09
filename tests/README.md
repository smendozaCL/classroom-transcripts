# Testing Strategy

This document outlines the testing strategy for the Classroom Transcripts project.

## Test Organization

```
tests/
├── unit/           # Fast, isolated tests of individual components
├── integration/    # Tests of component interactions
├── e2e/           # Full workflow tests
├── fixtures/      # Shared test fixtures and data
└── utils/         # Test utilities and helpers
```

## Test Types

### Unit Tests 🧩

- Located in `tests/unit/`
- Test individual components in isolation
- Mock external dependencies
- Fast execution
- Run on every PR

### Integration Tests 🔗

- Located in `tests/integration/`
- Test component interactions
- Test Azure Storage, AssemblyAI integration
- May use real external services in test environment
- Run on merge to main

### End-to-End Tests 🏁

- Located in `tests/e2e/`
- Test complete workflows
- Simulate real user interactions
- Run on deployment
- Use test environment services

## Running Tests

### Running All Tests

```bash
pytest
```

### Running Specific Test Types

```bash
# Run unit tests only
pytest tests/unit

# Run integration tests only
pytest -m integration

# Run e2e tests only
pytest -m e2e

# Run all tests except slow ones
pytest -m "not slow"
```

### Test Environment Setup

1. Local Development:

   - Copy `.env.example` to `.env.local`
   - Configure test environment variables
   - Use Azurite for local Azure Storage emulation

2. CI/CD Pipeline:
   - Uses GitHub Actions
   - Configures test environment using secrets
   - Runs different test types at appropriate stages

## Test Fixtures

Common test fixtures are located in:

- `tests/conftest.py` - Global fixtures
- `tests/fixtures/` - Shared test data and fixtures

## Best Practices

1. **Test Isolation**

   - Each test should be independent
   - Clean up resources after tests
   - Use appropriate mocking

2. **Naming Conventions**

   - Test files: `test_*.py`
   - Test functions: `test_*`
   - Clear, descriptive names

3. **Test Documentation**

   - Each test should have a clear docstring
   - Explain test purpose and expectations
   - Document any special setup required

4. **Test Data**
   - Use fixture files for test data
   - Store in `tests/fixtures/`
   - Document data format and purpose

## Markers

Available pytest markers:

- `@pytest.mark.unit`: Unit tests
- `@pytest.mark.integration`: Integration tests
- `@pytest.mark.e2e`: End-to-end tests
- `@pytest.mark.slow`: Slow running tests

## Logging

Tests use structured logging:

- Logs stored in `logs/`
- Test results logged with timestamps
- Error details captured for debugging
