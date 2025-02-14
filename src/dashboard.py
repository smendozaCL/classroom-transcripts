import streamlit as st
import assemblyai as aai
from datetime import datetime
import pandas as pd
import os
import plotly.express as px
from assemblyai.types import ListTranscriptParameters
import pytz
from utils.google_drive import upload_transcript_to_drive
from wordcloud import WordCloud
import matplotlib.pyplot as plt
from utils.transcript_mapping import TranscriptMapper
import numpy as np
import requests
from typing import Optional
from azure.storage.blob import BlobServiceClient, generate_blob_sas, BlobSasPermissions
from azure.identity import DefaultAzureCredential
from datetime import timedelta
import altair as alt

# Configure AssemblyAI
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")

# Initialize session state
if "page_token" not in st.session_state:
    st.session_state.page_token = None
if "annotations" not in st.session_state:
    st.session_state.annotations = {}
if "selected_transcript" not in st.session_state:
    st.session_state.selected_transcript = None
if "transcription_settings" not in st.session_state:
    st.session_state.transcription_settings = {
        "language_code": "en",
        "speaker_labels": True,
        "auto_highlights": False,
        "punctuate": True,
        "format_text": True,
        "dual_channel": False,
        "content_safety": False,
        "filter_profanity": False,
        "disfluencies": False,
        "sentiment_analysis": False,
        "auto_chapters": False,
        "entity_detection": False,
        "redact_pii": False,
        "redact_pii_audio": False,
        "redact_pii_policies": [],
        "redact_pii_sub": "entity_type"
    }

# Initialize debug mode from secrets
# DEBUG = st.secrets.get("DEBUG", False)  # Default to False if not set
DEBUG = os.getenv("DEBUG", False)

# Main content area with sidebar
st.title("📚 Transcript Review Dashboard")

# Initialize the transcriber
transcriber = aai.Transcriber()


def format_date_with_timezone(
    date_str, timezone_name="America/New_York", show_timezone=True
):
    # Convert string to datetime if needed
    if isinstance(date_str, str):
        date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    else:
        date = date_str

    # Convert to selected timezone
    timezone = pytz.timezone(timezone_name)
    localized_date = date.astimezone(timezone)

    # Format with a friendly string like "Monday, March 20 at 2:30 PM EDT"
    format_string = "%A, %B %d at %I:%M %p"
    if show_timezone:
        format_string += " %Z"
    return localized_date.strftime(format_string)


def format_duration(seconds):
    """Convert seconds to HH:MM:SS format"""
    if not seconds:
        return "N/A"

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"


# Add caching functions
@st.cache_data(ttl=3600)
def get_transcript_list() -> list:
    """Cache the list of transcripts."""
    transcript_data = []
    completed_count = 0
    last_transcript_id = None

    while completed_count < 10:
        params = ListTranscriptParameters(limit=20, after_id=last_transcript_id)
        response = transcriber.list_transcripts(params=params)

        if not response.transcripts:
            break

        for item in response.transcripts:
            status = str(
                item.status.value if hasattr(item.status, "value") else item.status
            )
            transcript_data.append(
                {
                    "ID": item.id,
                    "Status": status,
                    "Created": item.created,
                    "Audio URL": item.audio_url or "",
                }
            )
            if status == "completed":
                completed_count += 1
                if completed_count >= 10:
                    break

        if response.transcripts:
            last_transcript_id = response.transcripts[-1].id

    return transcript_data


@st.cache_data(ttl=3600)
def get_cached_transcript_details(transcript_id: str) -> dict:
    """Get cached transcript details excluding status."""
    transcript = aai.Transcript.get_by_id(transcript_id)

    # Explicitly set audio_url to None for AssemblyAI CDN URLs
    audio_url = None
    if transcript.audio_url and "blob.core.windows.net" in transcript.audio_url:
        audio_url = transcript.audio_url

    return {
        "id": transcript.id,
        "text": transcript.text,
        "words": transcript.words,
        "utterances": transcript.utterances,
        "audio_url": audio_url,  # Only include blob storage URLs
        "audio_duration": transcript.audio_duration,
        "language_code": getattr(transcript, "language_code", "en"),
        "confidence": getattr(transcript, "confidence", None),
    }


@st.cache_data(ttl=3000)
def get_blob_sas_url(audio_url: str) -> Optional[str]:
    """Get cached SAS URL for blob storage audio file."""
    try:
        if not audio_url:
            return None

        # Only process Azure blob storage URLs
        if "blob.core.windows.net" not in audio_url:
            st.warning("Audio file not in Azure storage")
            return None

        # Parse URL to get account, container, and blob
        parts = audio_url.split("/")
        account = parts[2].split(".")[0]
        container_name = parts[3]
        blob_name = "/".join(parts[4:])

        # Connect using DefaultAzureCredential
        blob_service = BlobServiceClient(
            f"https://{account}.blob.core.windows.net",
            credential=DefaultAzureCredential(),
        )
        container_client = blob_service.get_container_client(container_name)
        blob_client = container_client.get_blob_client(blob_name)

        # Try to get metadata first
        try:
            properties = blob_client.get_blob_properties()
            if properties.metadata.get("sas_url"):
                return properties.metadata["sas_url"]
        except Exception:
            pass

        # Generate SAS token if no metadata URL
        sas_token = generate_blob_sas(
            account_name=account,
            container_name=container_name,
            blob_name=blob_name,
            account_key=blob_service.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.utcnow() + timedelta(hours=1),
        )
        return f"{blob_client.url}?{sas_token}"
    except Exception as e:
        st.warning(f"Could not generate SAS URL: {str(e)}")
        return None


def get_transcript_status(transcript_id: str) -> str:
    """Get fresh transcript status without caching."""
    transcript = aai.Transcript.get_by_id(transcript_id)
    return str(transcript.status)


def is_recent_transcript(created_date: datetime, hours: int = 12) -> bool:
    """Check if transcript is less than N hours old."""
    now = datetime.now(created_date.tzinfo)
    age = now - created_date
    return age.total_seconds() < (hours * 3600)


def try_assemblyai_audio(audio_url: str) -> bool:
    """Test if AssemblyAI CDN URL is accessible."""
    try:
        response = requests.head(audio_url, timeout=2)
        return response.status_code == 200
    except Exception:
        return False


def show():
    """Display the admin dashboard page."""
    # Move existing code here

    try:
        # Get list of transcripts with pagination
        transcript_data = get_transcript_list()
        if not transcript_data:
            st.info("No transcripts found.")
        else:
            # Create display dataframe
            df = pd.DataFrame(transcript_data)
            df["Created"] = pd.to_datetime(df["Created"]).dt.tz_localize("UTC")

            # Sort by creation date (newest first)
            df = df.sort_values("Created", ascending=False)

            # Sidebar with status summary and recent transcripts
            with st.sidebar:
                st.title("🕒 Recent Transcripts")
                # Dictionary mapping timezone names to pytz timezones
                timezones = {
                    "Eastern Standard Time (EST)": "US/Eastern",
                    "Central Standard Time (CST)": "US/Central",
                    "Mountain Standard Time (MST)": "US/Mountain",
                    "Pacific Standard Time (PST)": "US/Pacific",
                    "Alaska Standard Time (AKST)": "US/Alaska",
                    "Hawaii Standard Time (HST)": "US/Hawaii",
                    # Add more timezones as needed
                }

                # Dropdown for user to select timezone
                selected_tz = st.selectbox(
                    "Select your timezone", list(timezones.keys())
                )
                user_timezone = pytz.timezone(timezones[selected_tz])
                # Show the date range of the transcripts
                min_date = df["Created"].min()
                st.caption(
                    f"Since {min_date.astimezone(user_timezone).strftime('%B %d, %Y')} at {min_date.astimezone(user_timezone).strftime('%I:%M %p')}"
                )

                st.divider()

                # Filter to completed transcripts for selection
                completed_df = df[df["Status"] == "completed"]
                if len(completed_df) == 0:
                    st.info("No completed transcripts available.")
                    selected_id = None
                else:
                    # Show 10 most recent completed transcripts
                    recent_completed = completed_df.head(10).copy()

                    # Add load more button
                    if len(completed_df) > 10:
                        if "show_more" not in st.session_state:
                            st.session_state.show_more = False

                        if st.button("📜 Load More Transcripts"):
                            st.session_state.show_more = not st.session_state.show_more

                        if st.session_state.show_more:
                            recent_completed = completed_df.head(25).copy()

                    # Add timezone selector
                    timezone_options = [
                        "America/New_York",
                        "America/Los_Angeles",
                        "America/Chicago",
                        "UTC",
                    ]
                    selected_timezone = st.selectbox(
                        "Select Timezone", options=timezone_options, index=0
                    )

                    # Format dates with selected timezone - without timezone for radio list
                    recent_completed["Friendly Date"] = recent_completed["Created"].apply(
                        lambda x: format_date_with_timezone(
                            x, selected_timezone, show_timezone=False
                        )
                    )

                    selected_id = st.radio(
                        "Select a transcript to review",
                        options=recent_completed["ID"].tolist(),
                        format_func=lambda x: recent_completed[
                            recent_completed["ID"] == x
                        ]["Friendly Date"].iloc[0],
                        key="transcript_selector",
                    )

                    # Make a note of in transcripts still in process or error
                    processing_df = df[df["Status"] == "processing"]
                    error_df = df[df["Status"] == "error"]

                    if len(processing_df) > 0:
                        st.warning(
                            f"{len(processing_df)} transcripts are still being processed."
                        )
                    if len(error_df) > 0:
                        st.warning(f"{len(error_df)} transcripts have errors.")

                # Move filters to bottom of sidebar
                with st.expander("🔍 Advanced Filters", expanded=False):
                    # Status filter
                    status_filter = st.multiselect(
                        "Status",
                        ["completed", "error", "queued", "processing"],
                        default=["completed"],
                    )

                    # Date range filter
                    st.subheader("Date Range")
                    date_range = st.date_input(
                        "Select dates",
                        value=(datetime.now().date(), datetime.now().date()),
                        help="Filter transcripts by creation date",
                    )

            # Main content - Detail View
            if selected_id:
                try:
                    transcript_details = get_cached_transcript_details(selected_id)
                    transcript = aai.Transcript.get_by_id(selected_id)

                    if transcript.status == aai.TranscriptStatus.completed:
                        # Get the creation date and format it
                        created_date = df[df['ID'] == selected_id]['Created'].iloc[0]
                        friendly_date = format_date_with_timezone(
                            created_date, 
                            selected_timezone, 
                            show_timezone=True
                        )
                        
                        # Show friendly date as title
                        st.header(f"Transcript {friendly_date}")

                        # Add download and export buttons in a 4-column grid
                        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
                        with col1:
                            if st.button("📥 Download Transcript", type="secondary"):
                                # Prepare transcript content
                                if transcript.utterances:
                                    content = "\n\n".join(
                                        [
                                            f"{u.speaker} ({u.start / 1000:.1f}s - {u.end / 1000:.1f}s):\n{u.text}"
                                            for u in transcript.utterances
                                        ]
                                    )
                                else:
                                    content = (
                                        transcript.text
                                        or "No transcript text available"
                                    )

                                # Create download button
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
                                        result = upload_transcript_to_drive(
                                            transcript, f"transcript_{selected_id}.txt"
                                        )

                                    if result["success"]:
                                        st.success(
                                            "Successfully uploaded to Google Drive!"
                                        )
                                        st.markdown(
                                            f"[Open in Google Drive]({result['link']})"
                                        )
                                    else:
                                        st.error(f"Failed to upload: {result['error']}")
                                except Exception as e:
                                    st.error(
                                        f"Error uploading to Google Drive: {str(e)}"
                                    )

                        # Audio player spans two columns
                        if transcript.audio_url:
                            with col3, col4:
                                st.audio(transcript.audio_url)

                        # Create two columns for metadata and debug info
                        meta_col, debug_col = st.columns([2, 1])

                        with meta_col:
                            # Top-level metrics in a clean grid
                            st.subheader("📊 Key Metrics")
                            metrics_cols = st.columns(3)
                            with metrics_cols[0]:
                                st.metric(
                                    "Duration",
                                    format_duration(transcript.audio_duration)
                                    if transcript.audio_duration
                                    else "N/A",
                                )
                                st.metric(
                                    "Words",
                                    f"{len(transcript.words):,}"
                                    if transcript.words
                                    else "0",
                                )
                            with metrics_cols[1]:
                                st.metric(
                                    "Speakers",
                                    len(set(w.speaker for w in transcript.words))
                                    if transcript.words
                                    else 0,
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
                                    f"{transcript.confidence:.1%}"
                                    if hasattr(transcript, "confidence")
                                    else "N/A",
                                )
                                st.metric(
                                    "Language",
                                    getattr(transcript, "language_code", "en").upper(),
                                )

                        with debug_col:
                            # Debug expander with raw transcript data
                            if DEBUG:
                                with st.expander("🔍 Debug Info", expanded=False):
                                    st.json(
                                        {
                                            "id": transcript.id,
                                            "status": str(transcript.status),
                                            "audio_url": transcript.audio_url,
                                            "audio_duration": transcript.audio_duration,
                                            "confidence": getattr(
                                                transcript, "confidence", None
                                            ),
                                            "language": getattr(
                                                transcript, "language_code", None
                                            ),
                                        }
                                    )

                        # Main content tabs
                        tab_list = [
                            "📝 Transcript",
                            "💭 Insights",
                            "⚙️ AI Settings",
                        ]
                        if DEBUG:
                            tab_list.append("🔍 Details")

                        tabs = st.tabs(tab_list)

                        with tabs[0]:
                            # Full transcript with utterance display
                            st.subheader(" Full Transcript")
                            if transcript.utterances:
                                for utterance in transcript.utterances:
                                    with st.container():
                                        st.markdown(
                                            f"**{utterance.speaker}** ({format_duration(utterance.start / 1000)} - {format_duration(utterance.end / 1000)})"
                                        )
                                        st.write(utterance.text)
                                        st.divider()
                            else:
                                st.write(
                                    transcript.text
                                    if transcript.text
                                    else "No transcript text available"
                                )

                        with tabs[1]:  # Analysis & Speakers tab
                            if transcript.words:
                                # Word Cloud
                                st.subheader("☁️ Word Cloud")
                                text = " ".join([w.text for w in transcript.words]).lower()
                                wordcloud = WordCloud(
                                    width=1600,
                                    height=800,
                                    background_color='white',
                                    scale=2,
                                    collocations=False
                                ).generate(text)
                                
                                fig, ax = plt.subplots(figsize=(10, 5), dpi=200)
                                ax.imshow(wordcloud, interpolation='bilinear')
                                ax.axis('off')
                                st.pyplot(fig)
                                plt.close()

                                st.divider()

                            if transcript.utterances:
                                    # Speaker Timeline first
                                    st.subheader("⏱️ Speaker Timeline")
                                    timeline_data = []
                                    # Convert utterances to timeline data
                                    for utterance in transcript.utterances:
                                        try:
                                            # Validate utterance data
                                            if not all(hasattr(utterance, attr) for attr in ['start', 'end', 'speaker', 'text']):
                                                continue

                                            start_time = float(utterance.start) / 1000.0
                                            end_time = float(utterance.end) / 1000.0
                                            
                                            # Skip invalid time ranges
                                            if start_time >= end_time:
                                                continue

                                            timeline_data.append({
                                                "Speaker": str(utterance.speaker),
                                                "Start": start_time,
                                                "End": end_time,
                                                "Text": utterance.text[:50] + "..." if len(utterance.text) > 50 else utterance.text
                                            })

                                        except Exception as e:
                                            st.warning(f"Skipped utterance: {str(e)}")
                                            continue

                                    # If there's valid data, create visualization
                                    if timeline_data:
                                        try:
                                            # Create DataFrame and verify data
                                            timeline_df = pd.DataFrame(timeline_data)
                                            timeline_df['Speaker'] = timeline_df['Speaker'].astype(str)
                                            timeline_df['Text'] = timeline_df['Text'].astype(str)
                                            timeline_df = timeline_df.sort_values('Start')
                                            
                                            # Create Altair chart
                                            # Add time formatting
                                            def format_time(seconds):
                                                minutes = int(seconds // 60)
                                                secs = int(seconds % 60)
                                                return f"{minutes:02d}:{secs:02d}"

                                            # Create base chart with formatted time axis
                                            timeline = alt.Chart(timeline_df).encode(
                                                x=alt.X('Start:Q', 
                                                    title='Time',
                                                    axis=alt.Axis(
                                                        format='d',
                                                        labelExpr="datum.value == 0 ? '00:00' : timeFormat(datum.value * 1000, '%M:%S')",
                                                        grid=True
                                                    )
                                                ),
                                                x2='End:Q',
                                                y=alt.Y('Speaker:N', 
                                                    sort=alt.EncodingSortField(field='Start', order='ascending'),
                                                    title='Speaker'
                                                ),
                                                color=alt.Color('Speaker:N', 
                                                    legend=None,
                                                    scale=alt.Scale(scheme='tableau10')
                                                ),
                                                tooltip=[
                                                    'Speaker',
                                                    alt.Tooltip('Start:Q', format='.1f', title='Start'),
                                                    alt.Tooltip('End:Q', format='.1f', title='End'),
                                                    'Text'
                                                ]
                                            ).mark_bar(
                                                opacity=0.8,
                                                height=20,
                                                cornerRadius=3
                                            ).properties(
                                                width='container',
                                                height=300,
                                                title='Conversation Flow'
                                            )
                                            
                                            # Add brush selection for zooming
                                            brush = alt.selection_interval(
                                                encodings=['x'],
                                                name='brush'
                                            )
                                            
                                            # Combine charts with zoom
                                            timeline = timeline.add_selection(
                                                brush
                                            ).transform_filter(
                                                brush
                                            )
                                            
                                            # Customize the chart appearance
                                            timeline = timeline.configure_axis(
                                                grid=True,
                                                gridColor='#EEEEEE',
                                                labelFontSize=12,
                                                titleFontSize=14
                                            ).configure_view(
                                                strokeWidth=0
                                            ).configure_title(
                                                fontSize=16,
                                                anchor='start'
                                            )
                                            
                                            # Display the chart
                                            st.altair_chart(timeline, use_container_width=True)
                                            
                                        except Exception as e:
                                            st.error(f"Visualization error: {str(e)}")
                                            if DEBUG:
                                                st.write("Error details:", str(e))

                        # Then Speaker Statistics
                        st.subheader("👥 Speaker Statistics")
                        speaker_stats: dict[str, dict[str, int | float]] = {}
                        stats_df = pd.DataFrame()  # Initialize empty DataFrame
                        
                        if transcript and transcript.utterances:
                            for utterance in transcript.utterances:
                                if not utterance.speaker:
                                    continue
                                    
                                if utterance.speaker not in speaker_stats:
                                    speaker_stats[utterance.speaker] = {
                                        "word_count": 0,
                                        "duration": 0,
                                        "turns": 0
                                    }

                                speaker_stats[utterance.speaker]["word_count"] += len(utterance.text.split())
                                speaker_stats[utterance.speaker]["duration"] += (utterance.end - utterance.start) / 1000
                                speaker_stats[utterance.speaker]["turns"] += 1

                            if speaker_stats:  # Only create DataFrame if we have stats
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
                            # AI Settings
                            st.subheader("⚙️ AI Configuration")
                            
                            # Define default configuration
                            default_config = pd.Series({
                                "language_code": "en",
                                "speaker_labels": True,
                                "auto_highlights": False,
                                "punctuate": True,
                                "format_text": True,
                                "dual_channel": False,
                                "content_safety": False,
                                "filter_profanity": False,
                                "disfluencies": False,
                                "sentiment_analysis": False,
                                "auto_chapters": False,
                                "entity_detection": False,
                                "redact_pii": False,
                                "redact_pii_audio": False,
                                "redact_pii_policies": None,
                                "redact_pii_sub": None
                            })
                            
                            # Get current config as a series
                            current_config = pd.Series({
                                key: getattr(transcript.config, key, default_config[key])
                                for key in default_config.index
                            })
                            
                            # Find non-default settings
                            non_default = current_config[current_config != default_config]
                            
                            if not non_default.empty:
                                st.write("**Custom Settings Used:**")
                                for key, value in non_default.items():
                                    formatted_key = str(key).replace('_', ' ').title()
                                    if isinstance(value, bool):
                                        st.write(f"- {formatted_key}: {'✅' if value else '❌'}")
                                    elif key == "redact_pii_policies" and value:
                                        st.write(f"- {formatted_key}: {', '.join(value)}")
                                    elif key == "redact_pii_sub":
                                        st.write(f"- {formatted_key}: {str(value)}")
                                    else:
                                        st.write(f"- {formatted_key}: {value}")
                            else:
                                st.info("Default configuration was used")
                            
                            st.divider()
                            st.subheader("🔄 New Transcription Settings")
                            
                            with st.form("transcription_settings"):
                                # Core settings in a clean layout
                                st.write("**Core Settings**")
                                col1, col2 = st.columns([1, 1])
                                
                                with col1:
                                    language = st.selectbox(
                                        "Language",
                                        options=["en", "es", "fr", "de", "it", "pt"],
                                        format_func=lambda x: {
                                            "en": "🇺🇸 English",
                                            "es": "🇪🇸 Spanish",
                                            "fr": "🇫🇷 French",
                                            "de": "🇩🇪 German",
                                            "it": "🇮🇹 Italian",
                                            "pt": "🇵🇹 Portuguese",
                                        }[x],
                                        index=["en", "es", "fr", "de", "it", "pt"].index(
                                            getattr(transcript.config, "language_code", "en")
                                        )
                                    )
                                    speaker_labels = st.toggle(
                                        "Speaker Detection",
                                        value=getattr(transcript.config, "speaker_labels", True),
                                        help="Identify and label different speakers"
                                    )
                                
                                with col2:
                                    speakers_expected = st.number_input(
                                        "Expected Speakers",
                                        min_value=1,
                                        max_value=10,
                                        value=getattr(transcript.config, "speakers_expected", 2),
                                        help="Approximate number of speakers expected"
                                    )
                                    dual_channel = st.toggle(
                                        "Dual Channel",
                                        value=getattr(transcript.config, "dual_channel", False),
                                        help="Process left/right channels separately"
                                    )
                                
                                # Privacy & Content settings
                                st.write("")  # Spacing
                                st.write("**Privacy & Content**")
                                privacy_cols = st.columns(2)
                                
                                with privacy_cols[0]:
                                    content_safety = st.toggle(
                                        "Content Safety",
                                        value=getattr(transcript.config, "content_safety", False),
                                        help="Flag potentially unsafe content"
                                    )
                                    filter_profanity = st.toggle(
                                        "Filter Profanity",
                                        value=getattr(transcript.config, "filter_profanity", False),
                                        help="Replace profanity with ***"
                                    )

                                with privacy_cols[1]:
                                    redact_pii = st.toggle(
                                        "PII Redaction",
                                        value=getattr(transcript.config, "redact_pii", False),
                                        help="Remove personal information"
                                    )
                                    
                                if redact_pii:
                                    # Count enabled PII types from session state
                                    current_pii_types = st.session_state.transcription_settings.get("redact_pii_policies", [])
                                    
                                    # Create summary text
                                    pii_categories = {
                                        "Personal": ["person_name", "email_address", "phone_number", "date_of_birth", "person_age"],
                                        "Financial": ["credit_card_number", "banking_information", "account_number"],
                                        "Medical": ["healthcare_number", "medical_condition", "medical_process", "drug", "blood_type"],
                                        "IDs": ["us_social_security_number", "drivers_license", "passport_number"],
                                    }
                                    
                                    enabled_categories = []
                                    for category, types in pii_categories.items():
                                        if any(pii_type in current_pii_types for pii_type in types):
                                            enabled_categories.append(category)
                                    
                                    summary = f"PII Redaction ({len(current_pii_types)} types"
                                    if enabled_categories:
                                        summary += f": {', '.join(enabled_categories)}"
                                    summary += ")"
                                    
                                    # Full-width expander with summary
                                    with st.expander(summary, expanded=True):
                                        # Personal Information
                                        st.write("**👤 Personal Information**")
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            pii_toggles = {
                                                "person_name": st.toggle(
                                                    "Names", 
                                                    value="person_name" in current_pii_types,
                                                    key="pii_person_name"
                                                ),
                                                "email_address": st.toggle(
                                                    "Email Addresses", 
                                                    value="email_address" in current_pii_types,
                                                    key="pii_email"
                                                ),
                                                "phone_number": st.toggle(
                                                    "Phone Numbers", 
                                                    value="phone_number" in current_pii_types,
                                                    key="pii_phone"
                                                ),
                                                "date_of_birth": st.toggle(
                                                    "Date of Birth", 
                                                    value="date_of_birth" in current_pii_types,
                                                    key="pii_dob"
                                                ),
                                                "person_age": st.toggle(
                                                    "Age", 
                                                    value="person_age" in current_pii_types,
                                                    key="pii_age"
                                                ),
                                            }
                                        with col2:
                                            pii_toggles.update({
                                                "gender_sexuality": st.toggle("Gender/Sexuality", "gender_sexuality" in current_pii_types),
                                                "nationality": st.toggle("Nationality/Ethnicity", "nationality" in current_pii_types),
                                                "religion": st.toggle("Religion", "religion" in current_pii_types),
                                                "political_affiliation": st.toggle("Political Affiliation", "political_affiliation" in current_pii_types),
                                            })
                                        
                                        st.write("**🏢 Location & Organization**")
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            pii_toggles.update({
                                                "location": st.toggle("Locations/Addresses", "location" in current_pii_types),
                                                "organization": st.toggle("Organizations", "organization" in current_pii_types),
                                                "occupation": st.toggle("Occupations", "occupation" in current_pii_types),
                                            })
                                        
                                        st.write("**💳 Financial & ID Numbers**")
                                        col1, col2 = st.columns(2)
                                        with col1:
                                            pii_toggles.update({
                                                "credit_card_number": st.toggle("Credit Card Numbers", "credit_card_number" in current_pii_types),
                                                "banking_information": st.toggle("Banking Information", "banking_information" in current_pii_types),
                                                "account_number": st.toggle("Account Numbers", "account_number" in current_pii_types),
                                            })
                                        with col2:
                                            pii_toggles.update({
                                                "us_social_security_number": st.toggle("SSN", "us_social_security_number" in current_pii_types),
                                                "drivers_license": st.toggle("Driver's License", "drivers_license" in current_pii_types),
                                                "passport_number": st.toggle("Passport Numbers", "passport_number" in current_pii_types),
                                            })
                                        
                                        with st.expander("🏥 Medical Information", expanded=False):
                                            pii_toggles.update({
                                                "healthcare_number": st.toggle("Healthcare Numbers", "healthcare_number" in current_pii_types),
                                                "medical_condition": st.toggle("Medical Conditions", "medical_condition" in current_pii_types),
                                                "medical_process": st.toggle("Medical Procedures", "medical_process" in current_pii_types),
                                                "drug": st.toggle("Medications", "drug" in current_pii_types),
                                                "blood_type": st.toggle("Blood Type", "blood_type" in current_pii_types),
                                                "injury": st.toggle("Injuries", "injury" in current_pii_types),
                                            })
                                        
                                        with st.expander("🔒 Digital & Other", expanded=False):
                                            pii_toggles.update({
                                                "username": st.toggle("Usernames", "username" in current_pii_types),
                                                "password": st.toggle("Passwords", "password" in current_pii_types),
                                                "ip_address": st.toggle("IP Addresses", "ip_address" in current_pii_types),
                                                "url": st.toggle("URLs", "url" in current_pii_types),
                                                "vehicle_id": st.toggle("Vehicle IDs", "vehicle_id" in current_pii_types),
                                                "number_sequence": st.toggle("Number Sequences", "number_sequence" in current_pii_types),
                                            })
                            
                                # Advanced features in expander
                                with st.expander("Advanced Features", expanded=False):
                                    st.write("**Analysis Features**")
                                    analysis_cols = st.columns(2)
                                    
                                    with analysis_cols[0]:
                                        auto_highlights = st.toggle("Auto Highlights", value=True)
                                        sentiment_analysis = st.toggle("Sentiment Analysis", value=False)
                                        entity_detection = st.toggle("Entity Detection", value=False)
                                    
                                    with analysis_cols[1]:
                                        auto_chapters = st.toggle("Auto Chapters", value=False)
                                        disfluencies = st.toggle("Include Disfluencies", value=False)
                                        word_boost = st.text_area(
                                            "Boost Words",
                                            placeholder="Enter words to boost, separated by commas",
                                            help="Improve recognition of specific terms"
                                        )
                                
                                # Submit button with clear styling
                                submitted = st.form_submit_button(
                                    "💾 Save Settings",
                                    type="primary",
                                    use_container_width=True
                                )
                                
                                if submitted:
                                    # Update transcription settings in session state
                                    st.session_state.transcription_settings.update({
                                        "language_code": language,
                                        "speaker_labels": speaker_labels,
                                        "speakers_expected": speakers_expected if speaker_labels else None,
                                        "dual_channel": dual_channel,
                                        "content_safety": content_safety,
                                        "redact_pii": redact_pii,
                                        "filter_profanity": filter_profanity,
                                        "auto_highlights": auto_highlights,
                                        "sentiment_analysis": sentiment_analysis,
                                        "entity_detection": entity_detection,
                                        "auto_chapters": auto_chapters,
                                        "disfluencies": disfluencies,
                                        "word_boost": [w.strip() for w in word_boost.split(",")] if word_boost else [],
                                        "redact_pii_audio": redact_pii,
                                        "redact_pii_sub": "entity_type",
                                        "redact_pii_policies": [
                                            pii_type for pii_type, enabled in pii_toggles.items() 
                                            if enabled
                                        ]
                                    })
                                    st.success("✅ Settings saved successfully!")
                            
                            # Audio source info at the bottom
                            st.divider()
                            if transcript.audio_url:
                                source_cols = st.columns([1, 4])
                                with source_cols[0]:
                                    st.subheader("🎙️ Source")
                                with source_cols[1]:
                                    if "blob.core.windows.net" in transcript.audio_url:
                                        st.success("Azure Blob Storage")
                                    else:
                                        st.info("External Source")
                                    with st.expander("View URL", expanded=False):
                                        st.write(transcript.audio_url)
                    else:
                        st.warning(f"Transcript status: {transcript.status}")
                        if transcript.status == aai.TranscriptStatus.error:
                            st.error(
                                "Transcription failed. Please check the logs for details."
                            )
                        elif transcript.status in [
                            aai.TranscriptStatus.queued,
                            aai.TranscriptStatus.processing,
                        ]:
                            st.info(
                                "Transcript is still being processed. Please check back later."
                            )

                except Exception as e:
                    st.error(f"Error loading transcript details: {str(e)}")

    except Exception as e:
        st.error(f"Error loading dashboard: {str(e)}")


show()