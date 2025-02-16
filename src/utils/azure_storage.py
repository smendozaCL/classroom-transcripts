from datetime import datetime, timedelta
from azure.storage.blob import BlobSasPermissions, generate_blob_sas
import logging

def get_blob_sas_url(
    blob_name: str,
    container_name: str,
    storage_account: str,
    storage_account_key: str,
    expiry_hours: int = 24
) -> str:
    """
    Generate a SAS URL for a blob with read permissions.
    
    Args:
        blob_name: Name of the blob
        container_name: Name of the container
        storage_account: Storage account name
        storage_account_key: Storage account key
        expiry_hours: Number of hours until SAS token expires (default 24)
    
    Returns:
        str: Full URL with SAS token
    """
    try:
        # Set start time to now and expiry time to 24 hours from now
        start_time = datetime.utcnow()
        expiry_time = start_time + timedelta(hours=expiry_hours)

        # Create SAS token with read permission
        sas_token = generate_blob_sas(
            account_name=storage_account,
            container_name=container_name,
            blob_name=blob_name,
            account_key=storage_account_key,
            permission=BlobSasPermissions(read=True),
            start=start_time,
            expiry=expiry_time
        )

        # Construct the full URL
        sas_url = f"https://{storage_account}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}"
        
        logging.debug(f"Generated SAS URL for blob {blob_name}")
        return sas_url

    except Exception as e:
        logging.error(f"Error generating SAS URL for {blob_name}: {e}")
        raise 