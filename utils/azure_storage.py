"""Azure Storage utility functions."""
from typing import Optional
from datetime import datetime, timedelta
from azure.storage.blob import BlobServiceClient, BlobSasPermissions, generate_blob_sas
import os
import logging


def get_blob_sas_url(blob_name: str, container_name: str = None, storage_account: str = None, storage_account_key: str = None) -> Optional[str]:
    """
    Generate a read-only SAS URL for a blob with 1 hour expiry.

    Args:
        blob_name: Name of the blob
        container_name: Optional container name, defaults to uploads container
        storage_account: Optional storage account name, defaults to env var
        storage_account_key: Optional storage account key, defaults to env var

    Returns:
        str: Full SAS URL for the blob

    Raises:
        ValueError: If storage account key is not available
    """
    try:
        # Get storage account info from params or environment
        account = storage_account or os.getenv("AZURE_STORAGE_ACCOUNT")
        account_key = storage_account_key
        container = container_name or "uploads"

        if not account:
            raise ValueError("Storage account name is required")

        # If no key provided, try to get from connection string
        if not account_key:
            connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
            if connection_string:
                # Parse connection string
                parts = dict(part.split('=', 1)
                             for part in connection_string.split(';') if part)
                account_key = parts.get('AccountKey')

        if not account_key:
            raise ValueError(
                "Storage account key is required for generating SAS token")

        # Generate SAS token with read-only access
        sas_token = generate_blob_sas(
            account_name=account,
            container_name=container,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(hours=1),
        )

        # Return the full URL with SAS token
        return f"https://{account}.blob.core.windows.net/{container}/{blob_name}?{sas_token}"

    except Exception as e:
        logging.error(f"Error generating SAS URL: {str(e)}")
        return None
