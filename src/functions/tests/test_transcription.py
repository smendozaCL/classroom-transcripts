from azure.storage.blob import BlobServiceClient
from pathlib import Path
import time
import json


def monitor_transcription():
    # Connect to local storage emulator
    connection_string = "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"

    # Create the blob service client
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)

    # Get container clients
    uploads_container = blob_service_client.get_container_client("uploads")
    transcripts_container = blob_service_client.get_container_client("transcriptions")

    # List blobs in uploads container
    print("\nFiles in uploads container:")
    for blob in uploads_container.list_blobs():
        print(f"- {blob.name}")

    print("\nWaiting for transcription results...")
    print("(This may take a few minutes. Press Ctrl+C to stop monitoring)")

    # Monitor transcriptions container
    seen_transcripts = set()
    try:
        while True:
            for blob in transcripts_container.list_blobs():
                if blob.name not in seen_transcripts:
                    print(f"\nNew transcript found: {blob.name}")
                    # Download and display the transcript
                    transcript_client = transcripts_container.get_blob_client(blob.name)
                    transcript_data = json.loads(
                        transcript_client.download_blob().readall()
                    )

                    print("\nTranscript contents:")
                    for utterance in transcript_data["utterances"]:
                        print(
                            f"{utterance['timestamp']} - {utterance['speaker']}: {utterance['text']}"
                        )

                    seen_transcripts.add(blob.name)

            time.sleep(5)  # Check every 5 seconds

    except KeyboardInterrupt:
        print("\nStopped monitoring")


if __name__ == "__main__":
    monitor_transcription()
