import streamlit as st
import assemblyai as aai
from datetime import datetime
import pandas as pd
import os
import plotly.express as px
from assemblyai.types import ListTranscriptParameters
import pytz
from utils.google_drive import upload_transcript_to_drive

st.set_page_config(
    page_title="Transcript Review",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Configure AssemblyAI
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")

# Initialize session state
if "page_token" not in st.session_state:
    st.session_state.page_token = None
if "annotations" not in st.session_state:
    st.session_state.annotations = {}
if "selected_transcript" not in st.session_state:
    st.session_state.selected_transcript = None

# Initialize debug mode from secrets
DEBUG = os.getenv("DEBUG", False)

# Main content area with sidebar
st.title("📄 Transcript Review")

# Initialize the transcriber
transcriber = aai.Transcriber()

def format_date_with_timezone(date_str, timezone_name="America/New_York", show_timezone=True):
    if isinstance(date_str, str):
        date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    else:
        date = date_str

    timezone = pytz.timezone(timezone_name)
    localized_date = date.astimezone(timezone)

    format_string = "%A, %B %d at %I:%M %p"
    if show_timezone:
        format_string += " %Z"
    return localized_date.strftime(format_string)

def format_duration(seconds):
    if not seconds:
        return "N/A"

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"

try:
    transcript_data = []
    completed_count = 0
    last_transcript_id = None

    while completed_count < 10:
        params = ListTranscriptParameters(
            limit=20,
            after_id=last_transcript_id,
        )
        response = transcriber.list_transcripts(params=params)

        if DEBUG:
            with st.sidebar:
                with st.expander("🔍 Debug: Raw Transcripts", expanded=False):
                    st.write(response)

        if not response.transcripts:
            break

        for item in response.transcripts:
            try:
                status = item.status.value if hasattr(item.status, "value") else str(item.status)
                created_date = pd.to_datetime(item.created)
                friendly_date = created_date.strftime("%A, %B %d at %I:%M %p")

                transcript_data.append(
                    {
                        "ID": item.id,
                        "Status": status,
                        "Created": item.created,
                        "Friendly Date": friendly_date,
                        "Audio URL": item.audio_url or "",
                    }
                )

                if status == "completed":
                    completed_count += 1
                    if completed_count >= 10:
                        break

            except Exception as e:
                st.warning(f"Error processing transcript: {str(e)}")
                continue

        if response.transcripts:
            last_transcript_id = response.transcripts[-1].id
        else:
            break

    if not transcript_data:
        st.info("No transcripts found.")
    else:
        df = pd.DataFrame(transcript_data)
        df["Created"] = pd.to_datetime(df["Created"]).dt.tz_localize("UTC")
        df = df.sort_values("Created", ascending=False)

        with st.sidebar:
            st.title("🕒 Recent Transcripts")
            timezones = {
                "Eastern Standard Time (EST)": "US/Eastern",
                "Central Standard Time (CST)": "US/Central",
                "Mountain Standard Time (MST)": "US/Mountain",
                "Pacific Standard Time (PST)": "US/Pacific",
                "Alaska Standard Time (AKST)": "US/Alaska",
                "Hawaii Standard Time (HST)": "US/Hawaii",
            }

            selected_tz = st.selectbox("Select your timezone", list(timezones.keys()))
            user_timezone = pytz.timezone(timezones[selected_tz])
            min_date = df["Created"].min()
            st.caption(f"Since {min_date.astimezone(user_timezone).strftime('%B %d, %Y')} at {min_date.astimezone(user_timezone).strftime('%I:%M %p')}")

            st.divider()

            completed_df = df[df["Status"] == "completed"]
            if len(completed_df) == 0:
                st.info("No completed transcripts available.")
                selected_id = None
            else:
                recent_completed = completed_df.head(10)

                if len(completed_df) > 10:
                    if "show_more" not in st.session_state:
                        st.session_state.show_more = False

                    if st.button("📜 Load More Transcripts"):
                        st.session_state.show_more = not st.session_state.show_more

                    if st.session_state.show_more:
                        recent_completed = completed_df.head(25)

                timezone_options = [
                    "America/New_York",
                    "America/Los Angeles",
                    "America/Chicago",
                    "UTC",
                ]
                selected_timezone = st.selectbox("Select Timezone", options=timezone_options, index=0)

                recent_completed["Friendly Date"] = recent_completed["Created"].apply(
                    lambda x: format_date_with_timezone(x, selected_timezone, show_timezone=False)
                )

                selected_id = st.radio(
                    "Select a transcript to review",
                    options=recent_completed["ID"].tolist(),
                    format_func=lambda x: recent_completed[recent_completed["ID"] == x]["Friendly Date"].iloc[0],
                    key="transcript_selector",
                )

                processing_df = df[df["Status"] == "processing"]
                error_df = df[df["Status"] == "error"]

                if len(processing_df) > 0:
                    st.warning(f"{len(processing_df)} transcripts are still being processed.")
                if len(error_df) > 0:
                    st.warning(f"{len(error_df)} transcripts have errors.")

            with st.expander("🔍 Advanced Filters", expanded=False):
                status_filter = st.multiselect(
                    "Status",
                    ["completed", "error", "queued", "processing"],
                    default=["completed"],
                )

                st.subheader("Date Range")
                date_range = st.date_input(
                    "Select dates",
                    value=(datetime.now().date(), datetime.now().date()),
                    help="Filter transcripts by creation date",
                )

        if selected_id:
            try:
                transcript = aai.Transcript.get_by_id(selected_id)

                if transcript.status == aai.TranscriptStatus.completed:
                    st.header(f"📝 {df[df['ID'] == selected_id]['Friendly Date'].iloc[0]}")

                    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
                    with col1:
                        if st.button("📥 Download Transcript", type="secondary"):
                            if transcript.utterances:
                                content = "\n\n".join(
                                    [
                                        f"{u.speaker} ({u.start / 1000:.1f}s - {u.end / 1000:.1f}s):\n{u.text}"
                                        for u in transcript.utterances
                                    ]
                                )
                            else:
                                content = transcript.text or "No transcript text available"

                            st.download_button(
                                label="Save as TXT",
                                data=content,
                                file_name=f"transcript_{selected_id}.txt",
                                mime="text/plain",
                            )

                    with col2:
                        if st.button("📤 Send to Google Drive", type="secondary"):
                            try:
                                with st.spinner("Uploading to Google Drive..."):
                                    result = upload_transcript_to_drive(transcript, f"transcript_{selected_id}.txt")

                                if result["success"]:
                                    st.success("Successfully uploaded to Google Drive!")
                                    st.markdown(f"[Open in Google Drive]({result['link']})")
                                else:
                                    st.error(f"Failed to upload: {result['error']}")
                            except Exception as e:
                                st.error(f"Error uploading to Google Drive: {str(e)}")

                    if transcript.audio_url:
                        with col3, col4:
                            st.audio(transcript.audio_url)

                    meta_col, debug_col = st.columns([2, 1])

                    with meta_col:
                        st.subheader("📊 Key Metrics")
                        metrics_cols = st.columns(3)
                        with metrics_cols[0]:
                            st.metric(
                                "Duration",
                                format_duration(transcript.audio_duration) if transcript.audio_duration else "N/A",
                            )
                            st.metric(
                                "Words",
                                f"{len(transcript.words):,}" if transcript.words else "0",
                            )
                        with metrics_cols[1]:
                            st.metric(
                                "Speakers",
                                len(set(w.speaker for w in transcript.words)) if transcript.words else 0,
                            )
                            st.metric(
                                "Avg Words/Min",
                                f"{(len(transcript.words or []) / (transcript.audio_duration or 1) * 60):.1f}"
                                if transcript.words and transcript.audio_duration
                                else "N/A",
                            )
                        with metrics_cols[2]:
                            st.metric(
                                "Confidence",
                                f"{transcript.confidence:.1%}" if hasattr(transcript, "confidence") else "N/A",
                            )
                            st.metric(
                                "Language",
                                getattr(transcript, "language_code", "en").upper(),
                            )

                    with debug_col:
                        if DEBUG:
                            with st.expander("🔍 Debug Info", expanded=False):
                                st.json(
                                    {
                                        "id": transcript.id,
                                        "status": str(transcript.status),
                                        "audio_url": transcript.audio_url,
                                        "audio_duration": transcript.audio_duration,
                                        "confidence": getattr(transcript, "confidence", None),
                                        "language": getattr(transcript, "language_code", None),
                                    }
                                )

                    tab_list = [
                        "📝 Transcript",
                        "👥 Speakers",
                        "📊 Analysis",
                        "💭 Feedback",
                    ]
                    if DEBUG:
                        tab_list.append("🔍 Details")

                    tabs = st.tabs(tab_list)

                    with tabs[0]:
                        st.subheader("📜 Full Transcript")
                        if transcript.utterances:
                            for utterance in transcript.utterances:
                                with st.container():
                                    st.markdown(
                                        f"**{utterance.speaker}** ({format_duration(utterance.start / 1000)} - {format_duration(utterance.end / 1000)})"
                                    )
                                    st.write(utterance.text)
                                    st.divider()
                        else:
                            st.write(transcript.text if transcript.text else "No transcript text available")

                    with tabs[1]:
                        if transcript.utterances:
                            st.subheader("👥 Speaker Statistics")
                            speaker_stats = {}
                            for utterance in transcript.utterances:
                                if utterance.speaker not in speaker_stats:
                                    speaker_stats[utterance.speaker] = {
                                        "word_count": len(utterance.text.split()),
                                        "duration": (utterance.end - utterance.start) / 1000,
                                        "turns": 1,
                                    }
                                else:
                                    speaker_stats[utterance.speaker]["word_count"] += len(utterance.text.split())
                                    speaker_stats[utterance.speaker]["duration"] += (utterance.end - utterance.start) / 1000
                                    speaker_stats[utterance.speaker]["turns"] += 1

                            stats_df = pd.DataFrame.from_dict(speaker_stats, orient="index")
                            stats_df["words_per_minute"] = (stats_df["word_count"] / (stats_df["duration"] / 60)).round(1)
                            stats_df = stats_df.round(2)

                            st.dataframe(
                                stats_df,
                                column_config={
                                    "word_count": "Total Words",
                                    "duration": "Speaking Time (s)",
                                    "turns": "Speaking Turns",
                                    "words_per_minute": "Words per Minute",
                                },
                            )

                    with tabs[2]:
                        if transcript.words:
                            st.subheader("📊 Word Frequency")
                            word_freq = pd.Series(
                                " ".join([w.text for w in transcript.words]).lower().split()
                            ).value_counts()
                            common_words = word_freq.head(15)

                            fig = px.bar(
                                x=common_words.index,
                                y=common_words.values,
                                labels={"x": "Word", "y": "Frequency"},
                                title="Most Common Words",
                            )
                            st.plotly_chart(fig, use_container_width=True)

                            if transcript.utterances:
                                st.subheader("⏱️ Speaker Timeline")
                                timeline_data = []
                                for utterance in transcript.utterances:
                                    timeline_data.append(
                                        {
                                            "Speaker": utterance.speaker,
                                            "Start": utterance.start / 1000,
                                            "End": utterance.end / 1000,
                                            "Duration": (utterance.end - utterance.start) / 1000,
                                            "Text": utterance.text,
                                        }
                                    )

                                timeline_df = pd.DataFrame(timeline_data)
                                fig = px.timeline(
                                    timeline_df,
                                    x_start="Start",
                                    x_end="End",
                                    y="Speaker",
                                    color="Speaker",
                                    hover_data=["Text", "Duration"],
                                    title="Conversation Flow",
                                )
                                fig.update_layout(xaxis_title="Time (seconds)", yaxis_title="Speaker")
                                st.plotly_chart(fig, use_container_width=True)

                    with tabs[3]:
                        st.subheader("💭 Feedback")

                        with st.expander("✍️ Add Feedback", expanded=True):
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                feedback_text = st.text_area(
                                    "Feedback",
                                    placeholder="Enter your feedback here...",
                                    key="new_feedback",
                                )
                            with col2:
                                feedback_type = st.selectbox(
                                    "Type",
                                    [
                                        "General",
                                        "Questioning",
                                        "Engagement",
                                        "Pacing",
                                        "Content",
                                    ],
                                )

                            if st.button("Save Feedback", type="primary"):
                                if feedback_text:
                                    if selected_id not in st.session_state.annotations:
                                        st.session_state.annotations[selected_id] = []

                                    st.session_state.annotations[selected_id].append(
                                        {
                                            "timestamp": datetime.now().timestamp(),
                                            "type": feedback_type,
                                            "feedback": feedback_text,
                                            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                        }
                                    )
                                    st.success("Feedback saved!")
                                    st.rerun()

                        if selected_id in st.session_state.annotations and st.session_state.annotations[selected_id]:
                            for annotation in sorted(
                                st.session_state.annotations[selected_id],
                                key=lambda x: x["timestamp"],
                                reverse=True,
                            ):
                                with st.expander(f"📝 {annotation['type']} - {annotation['created']}", expanded=True):
                                    st.write(annotation["feedback"])
                        else:
                            st.info("No feedback added yet.")

                    if DEBUG and len(tabs) > 4:
                        with tabs[4]:
                            st.subheader("🔍 Details")
                            st.write(transcript)
                else:
                    st.warning(f"Transcript status: {transcript.status}")
                    if transcript.status == aai.TranscriptStatus.error:
                        st.error("Transcription failed. Please check the logs for details.")
                    elif transcript.status in [aai.TranscriptStatus.queued, aai.TranscriptStatus.processing]:
                        st.info("Transcript is still being processed. Please check back later.")

            except Exception as e:
                st.error(f"Error loading transcript details: {str(e)}")

except Exception as e:
    st.error(f"Error loading dashboard: {str(e)}")

if st.button("Resubmit Transcription"):
    try:
        response = requests.post(
            f"https://api.assemblyai.com/v2/transcript/{selected_id}/resubmit",
            headers={"authorization": os.getenv("ASSEMBLYAI_API_KEY")},
        )
        if response.status_code == 200:
            st.success("Transcription resubmitted successfully!")
        else:
            st.error(f"Failed to resubmit transcription: {response.json()}")
    except Exception as e:
        st.error(f"Error resubmitting transcription: {str(e)}")

if "file_uri" not in st.session_state:
    st.session_state.file_uri = None

if "transcription_id" not in st.session_state:
    st.session_state.transcription_id = None

if st.session_state.file_uri is None or st.session_state.transcription_id is None:
    st.warning("No file URI or transcription ID found in session state. Please upload a new file.")
else:
    st.write(f"**File URI:** {st.session_state.file_uri}")
    st.write(f"**Transcription ID:** {st.session_state.transcription_id}")
