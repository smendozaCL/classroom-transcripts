# For more information, please refer to https://aka.ms/vscode-docker-python
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Set working directory to where the src module will be
WORKDIR /app

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy


# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY . /app
COPY ./.streamlit ./app/.streamlit

# Install the project's dependencies using the lockfile and settings
RUN uv sync --frozen --no-install-project --no-dev

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Reset the entrypoint, don't invoke `uv`
ENTRYPOINT []

# Run the streamlit app
CMD ["streamlit", "run", "app.py"]