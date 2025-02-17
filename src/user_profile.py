import streamlit as st
import os
from typing import List
import requests
from time import time

if st.experimental_user.get("is_logged_in"):
    # Get the user's sub (subject) ID from Auth0
    user_id = st.experimental_user.get("sub")
else:
    st.login()

DEBUG = os.getenv("DEBUG", False)
auth_provider = os.getenv("STREAMLIT_AUTH_PROVIDER", None)
if auth_provider is not None:
    auth_dict = st.secrets.get(auth_provider, st.secrets.get("auth"))
    client_id = auth_dict.get("client_id")
    client_secret = auth_dict.get("client_secret")
    domain = auth_dict.get("domain")
    

def _get_management_api_token() -> str:
    """Get Auth0 Management API access token."""
    if DEBUG:
        st.sidebar.write("Fetching new management token...")
        st.sidebar.write(f"Domain: {domain}")
        st.sidebar.write(f"Client ID exists: {bool(client_id)}")
        st.sidebar.write(f"Client Secret exists: {bool(client_secret)}")

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "audience": f"https://{domain}/api/v2/",
        "grant_type": "client_credentials",
    }

    try:
        response = requests.post(f"https://{domain}/oauth/token", json=payload)
        response.raise_for_status()
        if DEBUG:
            st.sidebar.write("Successfully obtained new token")
        return response.json()["access_token"]
    except Exception as e:
        if DEBUG:
            st.sidebar.error(f"Token fetch failed: {str(e)}")
            st.sidebar.write(response.text if response else "No response")
        raise


# Cache for the management token
_token_cache = {"token": None, "expires_at": 0}


def get_cached_token() -> str:
    """Get a cached management token or fetch a new one if expired."""
    now = time()
    if DEBUG:
        st.sidebar.write("Token cache status:")
        st.sidebar.write(f"- Has token: {bool(_token_cache['token'])}")
        st.sidebar.write(f"- Expires at: {_token_cache['expires_at']}")
        st.sidebar.write(f"- Current time: {now}")

    if _token_cache["token"] is None or now > _token_cache["expires_at"]:
        if DEBUG:
            st.sidebar.write("Cache miss - fetching new token")
        _token_cache["token"] = _get_management_api_token()
        _token_cache["expires_at"] = now + 3500
    else:
        if DEBUG:
            st.sidebar.write("Using cached token")
    return _token_cache["token"]


def get_user_roles(user_id: str) -> List[str]:
    """
    Get user roles from Auth0 Management API.

    Args:
        user_id: The Auth0 user ID

    Returns:
        List of role names assigned to the user
    """
    if DEBUG:
        st.sidebar.write(f"Fetching roles for user: {user_id}")

    token = get_cached_token()
    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(
            f"https://{domain}/api/v2/users/{user_id}/roles", headers=headers
        )
        response.raise_for_status()
        roles = response.json()
        if DEBUG:
            st.sidebar.write(f"Roles response: {roles}")
        return [role["name"] for role in roles]
    except Exception as e:
        if DEBUG:
            st.sidebar.error(f"Roles fetch failed: {str(e)}")
            st.sidebar.write(
                "Response:", response.text if "response" in locals() else "No response"
            )
        raise


def get_user_profile(user_id: str) -> dict:
    """Get user profile including roles."""
    profile = {
        # ... existing profile fields ...
        "roles": get_user_roles(user_id)
    }
    return profile


# Main UI code
st.title(st.experimental_user.get("name"))

user = st.experimental_user

cols = st.columns([1, 3])
with cols[0]:
    st.image(user.get("picture"))

with cols[1]:
    try:
        roles = get_user_roles(user_id)
        if roles:
            for role in roles:
                with st.container(border=True):
                    st.markdown(f":key: {role}")
        else:
            st.write("No roles assigned.")
    except Exception as e:
        st.error(f"Error fetching roles: {str(e)}")
        if DEBUG:
            st.exception(e)
    email_display = (
        f"{user.get('email')} ✓"
        if user.get("email_verified")
        else "Email not verified."
    )
    st.write(email_display)


if st.button("Logout"):
    st.logout()

if DEBUG:
    st.sidebar.write(user)
