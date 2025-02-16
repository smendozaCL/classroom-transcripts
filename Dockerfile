# For more information, please refer to https://aka.ms/vscode-docker-python
FROM ghcr.io/astral-sh/uv:0.5.31-python3.13-bookworm-slim

# Set working directory to where the src module will be
WORKDIR /workspace


# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies using pip and uv in the virtual environment
RUN pip install uv
RUN uv pip install -r requirements.txt --system

# Copy application code
COPY . /app

# Ensure the entrypoint script is executable
RUN chmod +x /app/entrypoint.sh

# Creates a non-root user with an explicit UID and adds permission to access the workspace
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /workspace
USER appuser

# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug

CMD ["uv", "run", "streamlit", "run", "app.py", "--server.port=8501"]
