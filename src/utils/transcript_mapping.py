from datetime import datetime
from azure.data.tables import TableEntity
import logging

def create_upload_entity(blob_name: str, original_name: str, transcript_id: str) -> TableEntity:
    """
    Create a standardized entity for storing audio file and transcript mappings.
    
    Args:
        blob_name: Unique name of blob in storage
        original_name: Original filename before uniquification
        transcript_id: AssemblyAI transcript ID
    """
    timestamp = datetime.utcnow().isoformat()
    
    return TableEntity(
        PartitionKey="AudioFiles",
        RowKey=blob_name,
        uploadTime=timestamp,
        originalFileName=original_name,
        transcriptId=transcript_id,
        status="queued"
    )

def update_transcript_status(table_client, blob_name: str, status: str):
    """Update the transcription status for a given blob."""
    try:
        entity = {
            'PartitionKey': 'AudioFiles',
            'RowKey': blob_name,
            'status': status,
            'lastUpdated': datetime.utcnow().isoformat()
        }
        table_client.update_entity(mode='merge', entity=entity)
        logging.info(f"Updated status for {blob_name} to {status}")
    except Exception as e:
        logging.error(f"Failed to update status for {blob_name}: {e}")
        raise 