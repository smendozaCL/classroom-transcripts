import logging
import os
from datetime import datetime
from pathlib import Path


def setup_test_logging():
    """Set up logging configuration for tests"""
    # Create logs directory if it doesn't exist
    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)

    # Create log file with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = logs_dir / f"integration_tests_{timestamp}.log"

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
    )

    return log_file


def log_test_result(logger, test_name, result):
    """Log test result"""
    logger.info(f"Test {test_name}: {result}")


def log_resource_cleanup(resource_type, resource_name):
    """Log resource cleanup operations"""
    logger = logging.getLogger(__name__)
    logger.info(f"Cleaning up {resource_type}: {resource_name}")
