import os
import pytest
import logging
from pathlib import Path
from azure.storage.blob import BlobServiceClient
from azure.identity import DefaultAzureCredential
from azure.core.exceptions import AzureError
from dotenv import load_dotenv
import assemblyai as aai
from .test_logging import setup_test_logging, log_test_result, log_resource_cleanup

# Load environment variables
load_dotenv(".env.local")

# Set up logging for all tests
log_file = setup_test_logging()
logger = logging.getLogger(__name__)


@pytest.fixture(scope="session", autouse=True)
def setup_logging():
    """Set up logging for the test session."""
    logger.info(f"Starting test session. Logs will be written to: {log_file}")
    yield
    logger.info("Test session completed.")


@pytest.fixture(scope="session")
def azure_credential():
    """Get Azure credential for the test session."""
    try:
        credential = DefaultAzureCredential()
        logger.info("Successfully obtained Azure credentials")
        return credential
    except Exception as e:
        logger.error(f"Failed to obtain Azure credentials: {str(e)}", exc_info=True)
        pytest.skip("Azure credentials not available")


@pytest.fixture(scope="session")
def storage_account():
    """Get storage account name from environment."""
    account = os.getenv("AZURE_STORAGE_ACCOUNT")
    if not account:
        logger.error("AZURE_STORAGE_ACCOUNT not found in environment variables")
        pytest.skip("AZURE_STORAGE_ACCOUNT not found in environment variables")
    logger.info(f"Using storage account: {account}")
    return account


@pytest.fixture(scope="session")
def blob_service_client(azure_credential, storage_account):
    """Create a blob service client for testing."""
    try:
        account_url = f"https://{storage_account}.blob.core.windows.net"
        client = BlobServiceClient(account_url, credential=azure_credential)
        # Test the connection
        client.get_service_properties()
        logger.info(f"Successfully connected to blob storage at {account_url}")
        return client
    except AzureError as e:
        logger.error(f"Failed to connect to blob storage: {str(e)}", exc_info=True)
        pytest.skip("Blob storage connection failed")


@pytest.fixture(scope="session")
def test_containers(blob_service_client):
    """Ensure test containers exist."""
    containers = ["uploads", "transcripts"]
    created = []

    for container_name in containers:
        try:
            container_client = blob_service_client.create_container(container_name)
            created.append(container_client)
            logger.info(f"Created container: {container_name}")
        except Exception as e:
            logger.warning(f"Container {container_name} already exists: {str(e)}")
            container_client = blob_service_client.get_container_client(container_name)
            created.append(container_client)

    yield created

    # Cleanup containers after tests
    for container in created:
        try:
            container.delete_container()
            log_resource_cleanup(logger, "container", container.container_name)
        except Exception as e:
            log_resource_cleanup(
                logger, "container", container.container_name, success=False
            )
            logger.warning(
                f"Failed to delete container {container.container_name}: {str(e)}"
            )


@pytest.fixture(scope="session")
def assemblyai_client():
    """Configure and return AssemblyAI client."""
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        logger.error("ASSEMBLYAI_API_KEY not found in environment variables")
        pytest.skip("ASSEMBLYAI_API_KEY not found in environment variables")

    try:
        aai.settings.api_key = api_key
        transcriber = aai.Transcriber()
        # Test the API key with a simple request
        transcriber.transcribe("Hello world")  # Simple test
        logger.info("Successfully configured AssemblyAI client")
        return transcriber
    except Exception as e:
        logger.error(f"Failed to initialize AssemblyAI client: {str(e)}", exc_info=True)
        pytest.skip("AssemblyAI client initialization failed")


@pytest.fixture
def test_audio_file():
    """Get the test audio file path."""
    test_file = Path("data/short-classroom-sample.m4a")
    if not test_file.exists():
        logger.error(f"Test file not found at {test_file}")
        pytest.skip(f"Test file not found at {test_file}")
    logger.info(f"Using test audio file: {test_file}")
    return test_file


@pytest.fixture
def mock_env(monkeypatch):
    """Mock environment variables for testing."""
    env_vars = {
        "ASSEMBLYAI_API_KEY": "test_api_key",
        "AZURE_STORAGE_SAS_URL": "http://example.com/container?sas=token",
        "AZURE_FUNCTION_KEY": "test_function_key",
        "WEBSITE_HOSTNAME": "test.azurewebsites.net",
        "AZURE_STORAGE_ACCOUNT": "teststorage",
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
        logger.debug(f"Mocked environment variable: {key}")
    return env_vars


@pytest.fixture(autouse=True)
def log_test_case(request):
    """Log the start and end of each test case."""
    test_name = request.node.name
    logger.info(f"Starting test: {test_name}")
    yield
    # Log test result
    if request.node.rep_call.passed:
        log_test_result(logger, test_name, "PASS")
    elif request.node.rep_call.failed:
        log_test_result(logger, test_name, "FAIL", request.node.rep_call.longrepr)
    elif request.node.rep_call.skipped:
        log_test_result(logger, test_name, "SKIP")


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Store test results for use in fixtures."""
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)
