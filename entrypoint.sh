#!/bin/bash

# Set up Streamlit secrets directory
mkdir -p ./.streamlit

# Generate the Streamlit secrets.toml file dynamically
cat <<EOF > ./.streamlit/secrets.toml
[auth]
redirect_uri = "${AUTH_REDIRECT_URI}"
cookie_secret = "${AUTH_COOKIE_SECRET}"
client_id = "${AUTH_CLIENT_ID}"
client_secret = "${AUTH_CLIENT_SECRET}"
server_metadata_url = "https://${AUTH_SERVER_METADATA_URL}"
EOF

echo "✅ secrets.toml generated successfully."

# Start the Streamlit app
exec uv run streamlit run ./app.py --server.port 8501 --server.address 0.0.0.0
