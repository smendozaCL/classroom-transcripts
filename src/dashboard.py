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
        "speakers_expected": 2,  # Default to 2 speakers
        "auto_highlights": False,
        "punctuate": True,
        "format_text": True,
        "content_safety": False,
        "filter_profanity": False,
        "disfluencies": False,
        "sentiment_analysis": False,
        "auto_chapters": False,
        "entity_detection": False,
        "redact_pii": False,
        "redact_pii_audio": False,
        "redact_pii_policies": [
            "person_name",
            "email_address",
            "phone_number",
            "location",
            "organization",
            "credit_card_number",
            "credit_card_cvv",
            "banking_information",
            "us_social_security_number",
            "medical_condition",
        ],  # Default PII policies including financial and medical items
        "redact_pii_sub": "entity_type",
        "word_boost": []  # Initialize empty word boost list
    }
if "transcription_settings_form" not in st.session_state:
    st.session_state.transcription_settings_form = st.session_state.transcription_settings.copy()

# Initialize debug mode from secrets
# DEBUG = st.secrets.get("DEBUG", False)  # Default to False if not set
DEBUG = os.getenv("DEBUG", False)

# Main content area with sidebar
st.title("📚 Transcript Review Dashboard")

# Initialize the transcriber
transcriber = aai.Transcriber()

# Use the same US timezone list and picker
US_TIMEZONES = [
    'US/Eastern',
    'US/Central', 
    'US/Mountain',
    'US/Pacific',
    'US/Alaska',
    'US/Hawaii'
]

if "timezone" not in st.session_state:
    st.session_state.timezone = 'US/Pacific'

with st.sidebar:
    st.session_state.timezone = st.selectbox(
        "Select Timezone",
        options=US_TIMEZONES,
        index=US_TIMEZONES.index(st.session_state.timezone),
        help="Choose your local timezone",
        format_func=lambda x: x.replace('US/', '')
    )

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

                    if DEBUG:
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

                # Settings section in sidebar
                st.divider()
                st.subheader("⚙️ Settings")
                
                # Core settings
                st.write("**Core Settings**")
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
                    key="form_language_code"
                )
                speaker_labels = st.toggle(
                    "Speaker Detection",
                    value=st.session_state.transcription_settings_form["speaker_labels"],
                    key="form_speaker_labels"
                )
                
                if speaker_labels:
                    speakers_expected = st.number_input(
                        "Expected Speakers",
                        min_value=1,
                        max_value=10,
                        value=2,
                        help="Approximate number of speakers expected in the recording"
                    )
                else:
                    speakers_expected = None

                # Privacy & Content settings
                st.write("")
                st.write("**Privacy & Content**")
                content_safety = st.toggle(
                    "Content Safety",
                    value=False,
                    help="Flag potentially unsafe content"
                )
                filter_profanity = st.toggle(
                    "Filter Profanity",
                    value=False,
                    help="Replace profanity with ***"
                )
                redact_pii = st.toggle(
                    "PII Redaction",
                    value=False,
                    help="Remove personal information"
                )

                # PII Settings
                if redact_pii:
                    with st.expander("🔒 PII Settings"):
                        st.caption("Always redacted: Credit Card Numbers, Bank Account Information, Social Security Numbers")
                        
                        st.write("**👤 Personal Information**")
                        pii_toggles = {
                            "person_name": st.toggle("Names", True),
                            "email_address": st.toggle("Email Addresses", True),
                            "phone_number": st.toggle("Phone Numbers", True),
                            "date_of_birth": st.toggle("Date of Birth", True),
                            "person_age": st.toggle("Age", True),
                            "occupation": st.toggle("Occupation", False, help="Redact mentions of jobs and professional roles"),
                        }
                        
                        st.write("**🏢 Location & Organization**")
                        pii_toggles.update({
                            "location": st.toggle("Locations/Addresses", True),
                            "organization": st.toggle("Organizations", True),
                        })

                        st.write("**🏥 Medical Information**")
                        pii_toggles.update({
                            "medical_condition": st.toggle("Medical Conditions", False, help="Redact mentions of medical conditions, diseases, and treatments"),
                        })

                # Advanced features
                with st.expander("🔧 Advanced Features"):
                    st.write("**Text Formatting**")
                    format_text = st.toggle("Format Text", value=True)
                    
                    st.write("**Analysis Features**")
                    auto_highlights = st.toggle("Auto Highlights", value=True)
                    sentiment_analysis = st.toggle("Sentiment Analysis", value=False)
                    entity_detection = st.toggle("Entity Detection", value=False)
                    auto_chapters = st.toggle("Auto Chapters", value=False)
                    disfluencies = st.toggle(
                        "Exclude Disfluencies",
                        value=False,
                        help="Remove filler words like 'um', 'uh', 'er' from the transcript"
                    )
                    word_boost = st.text_area(
                        "Custom Dictionary",
                        placeholder="Enter custom words or spellings to boost recognition accuracy, separated by commas",
                        help="Add domain-specific terms, proper names, or technical words to improve their recognition in the transcript"
                    )

                # Save and Re-transcribe buttons
                st.divider()
                if st.button("💾 Save Settings", type="primary", use_container_width=True):
                    # Create a new dictionary for the updated settings
                    new_settings = {
                        "language_code": language,
                        "speaker_labels": speaker_labels,
                        "speakers_expected": speakers_expected if speaker_labels else None,
                        "content_safety": content_safety,
                        "redact_pii": redact_pii,
                        "filter_profanity": filter_profanity,
                        "auto_highlights": auto_highlights,
                        "sentiment_analysis": sentiment_analysis,
                        "entity_detection": entity_detection,
                        "auto_chapters": auto_chapters,
                        "disfluencies": disfluencies,
                        "format_text": format_text,
                        "word_boost": [w.strip() for w in word_boost.split(",")] if word_boost and word_boost.strip() else [],
                        "redact_pii_audio": redact_pii,
                        "redact_pii_sub": aai.types.PIISubstitutionPolicy.entity_name if redact_pii else None,
                        "redact_pii_policies": [aai.PIIRedactionPolicy(p) for p in pii_toggles.keys() if pii_toggles[p]] if redact_pii else [
                            aai.PIIRedactionPolicy.person_name,
                            aai.PIIRedactionPolicy.email_address,
                            aai.PIIRedactionPolicy.phone_number,
                            aai.PIIRedactionPolicy.location,
                            aai.PIIRedactionPolicy.organization,
                            aai.PIIRedactionPolicy.credit_card_number,
                            aai.PIIRedactionPolicy.credit_card_cvv,
                            aai.PIIRedactionPolicy.banking_information,
                            aai.PIIRedactionPolicy.us_social_security_number,
                            aai.PIIRedactionPolicy.medical_condition,
                        ]  # Default policies if none selected
                    }
                    
                    # Update both session states
                    st.session_state.transcription_settings = new_settings
                    st.session_state.transcription_settings_form = new_settings
                    st.success("✅ Settings saved successfully!")

                if st.button("🔄 Re-transcribe", type="secondary", use_container_width=True):
                    if not selected_id:
                        st.error("Please select a transcript first")
                    else:
                        try:
                            transcript = aai.Transcript.get_by_id(selected_id)
                            if not transcript.audio_url:
                                st.error("No audio URL available for this transcript")
                                return
                            
                            # Use current settings from form
                            config = aai.TranscriptionConfig(
                                language_code=language,
                                speaker_labels=speaker_labels,
                                speakers_expected=speakers_expected if speaker_labels else None,
                                content_safety=content_safety,
                                redact_pii=redact_pii,
                                filter_profanity=filter_profanity,
                                auto_highlights=auto_highlights,
                                sentiment_analysis=sentiment_analysis,
                                entity_detection=entity_detection,
                                auto_chapters=auto_chapters,
                                disfluencies=disfluencies,
                                format_text=format_text,
                                word_boost=[w.strip() for w in word_boost.split(",")] if word_boost and word_boost.strip() else [],
                                redact_pii_audio=redact_pii,
                                redact_pii_sub=aai.types.PIISubstitutionPolicy.entity_name if redact_pii else None,
                                redact_pii_policies=[aai.PIIRedactionPolicy(p) for p in pii_toggles.keys() if pii_toggles[p]] if redact_pii else [
                                    aai.PIIRedactionPolicy.person_name,
                                    aai.PIIRedactionPolicy.email_address,
                                    aai.PIIRedactionPolicy.phone_number,
                                    aai.PIIRedactionPolicy.location,
                                    aai.PIIRedactionPolicy.organization,
                                    aai.PIIRedactionPolicy.credit_card_number,
                                    aai.PIIRedactionPolicy.credit_card_cvv,
                                    aai.PIIRedactionPolicy.banking_information,
                                    aai.PIIRedactionPolicy.us_social_security_number,
                                    aai.PIIRedactionPolicy.medical_condition,
                                ]  # Default policies if none selected
                            )
                            
                            # Submit new transcription request
                            new_transcript = transcriber.transcribe(
                                transcript.audio_url,
                                config=config
                            )
                            st.success(f"✅ New transcription started! ID: {new_transcript.id}")
                        except Exception as e:
                            st.error(f"Failed to start transcription: {str(e)}")

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

                        # Main content tabs - removed Settings tab
                        tab_list = [
                            "📝 Transcript",
                            "💭 Insights"
                        ]
                        if DEBUG:
                            tab_list.append("🔍 Details")

                        # Download options
                        download_cols = st.columns([1, 1, 2])
                        with download_cols[0]:
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
                                    content = transcript.text or "No transcript text available"

                                # Create download button
                                st.download_button(
                                    label="Save as TXT",
                                    data=content,
                                    file_name=f"transcript_{selected_id}.txt",
                                    mime="text/plain",
                                )

                        with download_cols[1]:
                            if transcript.audio_url and "blob.core.windows.net" in transcript.audio_url:
                                # Get SAS URL for Azure blob storage
                                download_url = get_blob_sas_url(transcript.audio_url)
                                if download_url:
                                    st.link_button("🔊 Download Audio", download_url, type="secondary")

                        tabs = st.tabs(tab_list)

                        with tabs[0]:
                            # Quick stats summary at top
                            quick_stats = st.columns(4)
                            with quick_stats[0]:
                                st.caption("Duration")
                                st.write(f"⏱️ {format_duration(transcript.audio_duration) if transcript.audio_duration else 'N/A'}")
                            with quick_stats[1]:
                                st.caption("Speakers")
                                st.write(f"👥 {len(set(w.speaker for w in transcript.words)) if transcript.words else '0'}")
                            with quick_stats[2]:
                                st.caption("Words")
                                st.write(f"📝 {len(transcript.words):,}" if transcript.words else "0")
                            with quick_stats[3]:
                                st.caption("Language")
                                st.write(f"🌐 {getattr(transcript, 'language_code', 'en').upper()}")
                            
                            
                            # Audio player
                            if transcript.audio_url and "blob.core.windows.net" in transcript.audio_url:
                                # Use the same SAS URL for the audio player
                                player_url = get_blob_sas_url(transcript.audio_url)
                                if player_url:
                                    st.audio(player_url)
                            
                            st.divider()

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
                                            
                                            # Add brush selection for zoom
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

                        if DEBUG:
                            with tabs[2]:  # Debug tab
                                st.write("Debug information:")
                                st.write(f"Transcript ID: {transcript.id}")
                                st.write(f"Status: {transcript.status}")
                                st.write(f"Audio URL: {transcript.audio_url}")
                                st.write(f"Text: {transcript.text}")
                                st.write(f"Words: {len(transcript.words) if transcript.words else 0}")
                                st.write(f"Utterances: {len(transcript.utterances) if transcript.utterances else 0}")
                                st.write(f"Language: {getattr(transcript, 'language_code', 'en').upper()}")
                                st.write(f"Confidence: {getattr(transcript, 'confidence', 'N/A')}")
                                st.write(f"Duration: {format_duration(transcript.audio_duration) if transcript.audio_duration else 'N/A'}")
                                created_date = df[df['ID'] == selected_id]['Created'].iloc[0]
                                st.write(f"Created: {format_date_with_timezone(created_date)}")

                except Exception as e:
                    st.error(f"Error loading transcript details: {str(e)}")

    except Exception as e:
        st.error(f"Error loading dashboard: {str(e)}")


show()