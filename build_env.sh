set -a
source .env
set +a

docker build \
  --build-arg AUTH_REDIRECT_URI="$AUTH_REDIRECT_URI" \
  --build-arg AUTH_COOKIE_SECRET="$AUTH_COOKIE_SECRET" \
  --build-arg AUTH_CLIENT_ID="$AUTH_CLIENT_ID" \
  --build-arg AUTH_CLIENT_SECRET="$AUTH_CLIENT_SECRET" \
  --build-arg AUTH_SERVER_METADATA_URL="$AUTH_SERVER_METADATA_URL" \
  -t my-streamlit-app .