import logging
import sys
from pathlib import Path
from datetime import datetime


def setup_test_logging():
    """Configure logging for integration tests with detailed error tracking."""
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # Create a unique log file for each test run
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"integration_tests_{timestamp}.log"

    # Create formatters
    console_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)8s] %(message)s (%(filename)s:%(lineno)s)"
    )
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)8s] [%(name)s] %(message)s (%(filename)s:%(lineno)s)"
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)

    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    return log_file


def log_test_result(logger, test_name, result, error=None):
    """Log test result with appropriate level and details."""
    if result == "PASS":
        logger.info(f"✅ Test passed: {test_name}")
    elif result == "SKIP":
        logger.warning(f"⏭️  Test skipped: {test_name}")
    elif result == "FAIL":
        logger.error(f"❌ Test failed: {test_name}")
        if error:
            logger.error(f"Error details: {str(error)}", exc_info=True)


def log_test_step(logger, step_description):
    """Log a test step with a consistent format."""
    logger.info(f"📝 {step_description}")


def log_resource_cleanup(logger, resource_type, resource_name, success=True):
    """Log cleanup of test resources."""
    if success:
        logger.info(f"🧹 Cleaned up {resource_type}: {resource_name}")
    else:
        logger.warning(f"⚠️  Failed to clean up {resource_type}: {resource_name}")


def log_api_interaction(logger, service_name, operation, success=True, details=None):
    """Log external API interactions."""
    if success:
        logger.info(f"🔄 {service_name} API {operation} successful")
        if details:
            logger.debug(f"Response details: {details}")
    else:
        logger.error(f"⚠️  {service_name} API {operation} failed")
        if details:
            logger.error(f"Error details: {details}")
