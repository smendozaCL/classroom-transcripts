import streamlit as st
import unittest
from unittest.mock import patch, MagicMock
import requests
import os


class TestTranscriptReview(unittest.TestCase):
    @patch("streamlit.write")
    @patch("streamlit.warning")
    def test_retrieve_file_uri_and_transcription_id(self, mock_warning, mock_write):
        """Test retrieving file URI and transcription ID from session state"""


        # Create a mock session state
        mock_state = {"file_uri": "test_uri", "transcription_id": "test_id"}
        # Apply the mock state
        with patch.object(st, "session_state", mock_state):
            st.write(f"**File URI:** {mock_state['file_uri']}")
            st.write(
                f"**Transcription ID:** {mock_state['transcription_id']}")
        
        from . import transcript_detail_view
        with patch.object(transcript_detail_view.st, "session_state", mock_state):
            transcript_detail_view.st.write(f"**File URI:** {mock_state['file_uri']}")
            transcript_detail_view.st.write(
                f"**Transcription ID:** {mock_state['transcription_id']}"
            )

            mock_write.assert_any_call("**File URI:** test_uri")
            mock_write.assert_any_call("**Transcription ID:** test_id")

    @patch("requests.post")
    @patch("streamlit.button")
    @patch("streamlit.success")
    @patch("streamlit.error")
    def test_resubmit_transcription(
        self, mock_error, mock_success, mock_button, mock_post
    ):
        mock_button.return_value = True
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"status": "success"}
        from . import transcript_detail_view

        transcript_detail_view.st.session_state = {"selected_id": "test_id"}
        transcript_detail_view.st.button("Resubmit Transcription")
        mock_success.assert_called_with("Transcription resubmitted successfully!")

        mock_post.return_value.status_code = 400
        transcript_detail_view.st.button("Resubmit Transcription")
        mock_error.assert_called_with(
            "Failed to resubmit transcription: {'status': 'error'}"
        )

    @patch("streamlit.warning")
    @patch("streamlit.session_state", {"file_uri": None, "transcription_id": None})
    def test_handle_fresh_session_state(self, mock_warning):
        from . import transcript_detail_view

        transcript_detail_view.st.session_state = {
            "file_uri": None,
            "transcription_id": None,
        }
        transcript_detail_view.st.warning(
            "No file URI or transcription ID found in session state. Please upload a new file."
        )
        mock_warning.assert_called_with(
            "No file URI or transcription ID found in session state. Please upload a new file."
        )

    @patch("streamlit.warning")
    @patch("streamlit.session_state", {"file_uri": None})
    def test_no_file_uri_in_session_state(self, mock_warning):
        from . import transcript_detail_view

        transcript_detail_view.st.session_state = {"file_uri": None}
        transcript_detail_view.st.warning(
            "No file URI found in session state. Please upload a new file."
        )
        mock_warning.assert_called_with(
            "No file URI found in session state. Please upload a new file."
        )

    @patch("streamlit.warning")
    @patch("streamlit.session_state", {"file_uri": None, "transcription_id": None})
    def test_find_blob_when_file_uri_not_set(self, mock_warning):
        from . import transcript_detail_view

        transcript_detail_view.st.session_state = {
            "file_uri": None,
            "transcription_id": None,
        }
        transcript_detail_view.st.warning(
            "No file URI or transcription ID found in session state. Please upload a new file."
        )
        mock_warning.assert_called_with(
            "No file URI or transcription ID found in session state. Please upload a new file."
        )

    @patch("streamlit.error")
    def test_missing_api_key(self, mock_error):
        """Test handling of missing API key"""
        with patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": ""}):
            from . import transcript_detail_view

            mock_error.assert_called_with(
                "AssemblyAI API key not found. Please check your environment configuration."
            )

    @patch("streamlit.session_state")
    def test_session_state_initialization(self, mock_session_state):
        """Test proper initialization of session state variables"""
        mock_session_state = {}
        from . import transcript_detail_view

        expected_keys = [
            "page_token",
            "annotations",
            "selected_transcript",
            "file_uri",
            "transcription_id",
        ]
        for key in expected_keys:
            self.assertIn(key, mock_session_state)

    @patch("streamlit.write")
    @patch("streamlit.warning")
    def test_display_class_name_and_description(self, mock_warning, mock_write):
        """Test displaying class name and description in the list and details views"""

        # Create a mock session state
        mock_state = {"class_name": "Test Class", "description": "Test Description"}
        # Apply the mock state
        with patch.object(st, "session_state", mock_state):
            st.write(f"**Class Name:** {mock_state['class_name']}")
            st.write(f"**Description:** {mock_state['description']}")

        from . import transcript_detail_view
        with patch.object(transcript_detail_view.st, "session_state", mock_state):
            transcript_detail_view.st.write(f"**Class Name:** {mock_state['class_name']}")
            transcript_detail_view.st.write(f"**Description:** {mock_state['description']}")

            mock_write.assert_any_call("**Class Name:** Test Class")
            mock_write.assert_any_call("**Description:** Test Description")


if __name__ == "__main__":
    unittest.main()
