#!/bin/bash

# Set up Streamlit secrets directory
mkdir -p /app/.streamlit

# Generate the Streamlit secrets.toml file dynamically
cat <<EOF > /app/.streamlit/secrets.toml
[auth]
redirect_uri = "${STREAMLIT_AUTH_REDIRECT_URI}"
cookie_secret = "${STREAMLIT_AUTH_COOKIE_SECRET}"

[auth.auth0]
client_id = "${STREAMLIT_AUTH_CLIENT_ID}"
client_secret = "${STREAMLIT_AUTH_CLIENT_SECRET}"
server_metadata_url = "https://${STREAMLIT_AUTH0_DOMAIN}/.well-known/openid-configuration"
EOF

echo "✅ secrets.toml generated successfully."

# Start the Streamlit app
exec streamlit run /app/app.py --server.port 8501 --server.address 0.0.0.0
