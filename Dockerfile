# For more information, please refer to https://aka.ms/vscode-docker-python
FROM python:3.13-slim

# Set working directory to where the src module will be
WORKDIR /workspace

# Copy configuration files
COPY pyproject.toml .

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager directly
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
RUN uv sync

# Copy application code
COPY . .

# Creates a non-root user with an explicit UID and adds permission to access the workspace
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /workspace
USER appuser

# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
CMD ["streamlit", "run", "src/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
