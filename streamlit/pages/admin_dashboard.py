import streamlit as st
import assemblyai as aai
from datetime import datetime
import pandas as pd
from dotenv import load_dotenv
import os

load_dotenv()

# Configure AssemblyAI
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")

st.set_page_config(
    page_title="Transcription Admin Dashboard", page_icon="🎙️", layout="wide"
)

st.title("🎙️ Transcription Admin Dashboard")

# Sidebar filters
st.sidebar.header("Filters")
status_filter = st.sidebar.multiselect(
    "Status",
    ["completed", "error", "queued", "processing"],
    default=["completed", "processing", "queued"],
)

date_range = st.sidebar.date_input(
    "Date Range", value=(datetime.now().date(), datetime.now().date())
)

# Main content area
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Recent Transcriptions")

    # Initialize the transcriber to access the API
    transcriber = aai.Transcriber()

    try:
        # Get list of transcripts
        transcripts = transcriber.list_transcripts()

        # Convert to DataFrame for easier display
        transcript_data = []
        for t in transcripts:
            transcript_data.append(
                {
                    "ID": t.id,
                    "Status": t.status.value,
                    "Created": t.created.strftime("%Y-%m-%d %H:%M:%S"),
                    "Duration": f"{t.audio_duration:.2f}s"
                    if t.audio_duration
                    else "N/A",
                    "Words": len(t.words) if t.words else 0,
                    "Speakers": len(set(w.speaker for w in t.words)) if t.words else 0,
                }
            )

        df = pd.DataFrame(transcript_data)

        # Apply filters
        if status_filter:
            df = df[df["Status"].isin(status_filter)]

        # Display as interactive table
        st.dataframe(df, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"Error fetching transcripts: {str(e)}")

with col2:
    st.subheader("Statistics")

    if "df" in locals():
        # Summary stats
        total_transcripts = len(df)
        completed = len(df[df["Status"] == "completed"])
        in_progress = len(df[df["Status"].isin(["queued", "processing"])])
        errors = len(df[df["Status"] == "error"])

        st.metric("Total Transcripts", total_transcripts)
        st.metric("Completed", completed)
        st.metric("In Progress", in_progress)
        st.metric("Errors", errors)

        # Show any error details
        if errors > 0:
            st.error("Failed Transcripts")
            error_transcripts = df[df["Status"] == "error"]
            st.dataframe(error_transcripts[["ID", "Created"]], hide_index=True)

# Transcript details section
st.subheader("Transcript Details")
selected_transcript_id = st.text_input("Enter Transcript ID to view details")

if selected_transcript_id:
    try:
        transcript = aai.Transcript.get_by_id(selected_transcript_id)

        if transcript.status == aai.TranscriptStatus.completed:
            # Display transcript info
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(
                    "Duration",
                    f"{transcript.audio_duration:.2f}s"
                    if transcript.audio_duration
                    else "N/A",
                )
            with col2:
                st.metric("Words", len(transcript.words) if transcript.words else 0)
            with col3:
                st.metric(
                    "Speakers",
                    len(set(w.speaker for w in transcript.words))
                    if transcript.words
                    else 0,
                )

            # Display full text
            st.text_area(
                "Transcript Text",
                transcript.text if transcript.text else "",
                height=200,
            )

            # Display speaker segments
            if transcript.utterances:
                st.subheader("Speaker Segments")
                for utterance in transcript.utterances:
                    with st.expander(
                        f"Speaker {utterance.speaker}: {utterance.start:.2f}s - {utterance.end:.2f}s"
                    ):
                        st.write(utterance.text)

            # Display additional metadata if available
            if transcript.chapters:
                st.subheader("Chapters")
                for chapter in transcript.chapters:
                    st.write(f"- {chapter.headline}")

            if transcript.auto_highlights:
                st.subheader("Key Moments")
                for highlight in transcript.auto_highlights:
                    st.write(f"- {highlight.text}")

        else:
            st.warning(f"Transcript status: {transcript.status.value}")
            if transcript.status == aai.TranscriptStatus.error:
                st.error(f"Error: {transcript.error}")

    except Exception as e:
        st.error(f"Error fetching transcript details: {str(e)}")
