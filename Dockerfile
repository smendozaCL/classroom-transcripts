# For more information, please refer to https://aka.ms/vscode-docker-python
FROM ghcr.io/astral-sh/uv:0.5.31-python3.13-bookworm-slim

# Set working directory to where the src module will be
WORKDIR /workspace

# Copy all files
COPY . .

# Install dependencies
RUN uv sync --frozen

# Creates a non-root user with an explicit UID and adds permission to access the workspace
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /workspace
USER appuser

# During debugging, this entry point will be overridden. For more information, please refer to https://aka.ms/vscode-docker-python-debug
CMD ["streamlit", "run", "src/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
