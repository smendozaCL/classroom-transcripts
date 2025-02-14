from typing import Optional, Dict
import json
import os

class TranscriptMapper:
    def __init__(self, mapping_file: str = "data/transcript_mapping.json"):
        self.mapping_file = mapping_file
        self._ensure_mapping_file()
        self.mapping = self._load_mapping()

    def _ensure_mapping_file(self) -> None:
        """Ensure the mapping file and directory exist."""
        os.makedirs(os.path.dirname(self.mapping_file), exist_ok=True)
        if not os.path.exists(self.mapping_file):
            with open(self.mapping_file, 'w') as f:
                json.dump({}, f)

    def _load_mapping(self) -> Dict:
        """Load the mapping from file."""
        with open(self.mapping_file, 'r') as f:
            return json.load(f)

    def _save_mapping(self) -> None:
        """Save the current mapping to file."""
        with open(self.mapping_file, 'w') as f:
            json.dump(self.mapping, f, indent=2)

    def add_mapping(self, transcript_id: str, file_uri: str) -> None:
        """Add or update a transcript-file mapping."""
        self.mapping[transcript_id] = file_uri
        self._save_mapping()

    def get_file_uri(self, transcript_id: str) -> Optional[str]:
        """Get the file URI for a transcript ID."""
        return self.mapping.get(transcript_id)

    def get_transcript_id(self, file_uri: str) -> Optional[str]:
        """Get the transcript ID for a file URI."""
        for tid, uri in self.mapping.items():
            if uri == file_uri:
                return tid
        return None 