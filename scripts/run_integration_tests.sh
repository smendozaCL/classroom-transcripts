#!/bin/bash

# Function to print colored output
print_colored() {
    local color=$1
    local message=$2
    case $color in
        "red") echo -e "\033[0;31m${message}\033[0m" ;;
        "green") echo -e "\033[0;32m${message}\033[0m" ;;
        "yellow") echo -e "\033[0;33m${message}\033[0m" ;;
        "blue") echo -e "\033[0;34m${message}\033[0m" ;;
        *) echo "${message}" ;;
    esac
}

# Create necessary directories
mkdir -p logs test-results

# Start Azurite if not running
if ! docker ps | grep -q azurite; then
    print_colored "blue" "Starting Azurite..."
    docker run -d \
        --name azurite \
        -p 10000:10000 \
        -p 10001:10001 \
        -p 10002:10002 \
        mcr.microsoft.com/azure-storage/azurite
    
    # Wait for Azurite to be ready
    sleep 5
    print_colored "green" "✓ Azurite is running"
fi

# Set environment variables for local testing
export AZURE_STORAGE_ACCOUNT=devstoreaccount1
export AZURE_STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
export PYTHONUNBUFFERED=1

# Run the tests
print_colored "blue" "Running integration tests..."
pytest tests/ -v -m "integration" \
    --junitxml=test-results/junit.xml \
    --cov=src \
    --cov-report=xml:test-results/coverage.xml \
    --cov-report=html:test-results/coverage-html \
    -n auto \
    "$@"

TEST_EXIT_CODE=$?

# Process test results
if [ -f "test-results/junit.xml" ]; then
    print_colored "blue" "\nTest Summary:"
    python3 -c "
import xml.etree.ElementTree as ET
tree = ET.parse('test-results/junit.xml')
root = tree.getroot()
tests = int(root.attrib['tests'])
failures = int(root.attrib['failures'])
errors = int(root.attrib['errors'])
skipped = int(root.attrib['skipped'])
passed = tests - failures - errors - skipped

print(f'\nTotal Tests: {tests}')
print(f'Passed: {passed}')
print(f'Failed: {failures}')
print(f'Errors: {errors}')
print(f'Skipped: {skipped}')
"
fi

# Show recent log entries
if [ -d "logs" ]; then
    print_colored "blue" "\nRecent Test Logs:"
    for log in logs/*.log; do
        if [ -f "$log" ]; then
            print_colored "yellow" "\n=== ${log} ==="
            tail -n 50 "$log"
        fi
    done
fi

# Cleanup
print_colored "blue" "\nCleaning up..."
if [ "$1" != "--keep-azurite" ]; then
    docker stop azurite
    docker rm azurite
    print_colored "green" "✓ Azurite stopped and removed"
else
    print_colored "yellow" "⚠ Keeping Azurite running as requested"
fi

# Open coverage report if tests passed and --show-coverage flag is set
if [ $TEST_EXIT_CODE -eq 0 ] && [[ " $* " =~ " --show-coverage " ]]; then
    print_colored "blue" "\nOpening coverage report..."
    python -m webbrowser "test-results/coverage-html/index.html"
fi

exit $TEST_EXIT_CODE 