import os
import tempfile
import logging
import dotenv
import streamlit as st
from pydub import AudioSegment
from pydub.effects import normalize
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_community.document_loaders.generic import GenericLoader
from langchain_community.document_loaders.parsers import OpenAIWhisperParser
from langchain_community.callbacks import StreamlitCallbackHandler
from langchain_core.output_parsers import StrOutputParser

dotenv.load_dotenv()
# Configure logging
logging.basicConfig(
    filename=os.path.join(tempfile.gettempdir(), "app.log"),
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

OPENAI_MODEL = st.secrets.get("OPENAI_MODEL", "gpt-4o")
if os.environ.get("OPENAI_API_KEY") is None:
    os.environ["OPENAI_API_KEY"] = st.secrets.get("OPENAI_API_KEY", "")

st.title("Transcribe an audio file using OpenAI's Whisper model")
temp_dir = tempfile.gettempdir()



# Initialize the transcription tool
transcription_tool = OpenAIWhisperParser()


# Helper function to preprocess audio for better transcription quality
def preprocess_audio(audio_segment):
    """Preprocess audio for better transcription quality"""
    try:
        # Normalize audio
        normalized_audio = normalize(audio_segment)

        # Convert to mono if stereo
        if normalized_audio.channels > 1:
            normalized_audio = normalized_audio.set_channels(1)

        # Set sample rate to 16kHz (preferred by many speech recognition systems)
        normalized_audio = normalized_audio.set_frame_rate(16000)

        logging.info("Successfully preprocessed audio")
        return normalized_audio

    except Exception as e:
        logging.error(f"Error preprocessing audio: {str(e)}")
        return audio_segment  # Return original if preprocessing fails


# Helper function to split audio into chunks
def split_audio(file_path, chunk_length_ms):
    try:
        logging.info(f"Attempting to split audio file: {file_path}")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Input file not found: {file_path}")

        try:
            audio = AudioSegment.from_file(file_path)
            logging.info(f"Successfully loaded audio file: {len(audio)}ms")
        except Exception as format_error:
            logging.warning(f"Failed to detect format, trying MP3: {format_error}")
            audio = AudioSegment.from_mp3(file_path)
            logging.info(f"Successfully loaded as MP3: {len(audio)}ms")

        # Add preprocessing step
        audio = preprocess_audio(audio)
        logging.info(f"Preprocessed audio length: {len(audio)}ms")

        if len(audio) == 0:
            raise ValueError("Audio file appears to be empty after preprocessing")

        chunks = [
            audio[i : i + chunk_length_ms]
            for i in range(0, len(audio), chunk_length_ms)
        ]

        # Validate chunks
        valid_chunks = [chunk for chunk in chunks if len(chunk) > 0]
        logging.info(f"Split audio into {len(valid_chunks)} valid chunks")

        if not valid_chunks:
            raise ValueError("No valid chunks were created from the audio file")

        return valid_chunks

    except Exception as e:
        logging.error(f"Error splitting audio: {str(e)}", exc_info=True)
        st.error(f"Error processing audio file: {str(e)}")
        return []


# Helper function to save chunks to temporary files
def save_chunks(chunks):
    try:
        chunk_paths = []
        for i, chunk in enumerate(chunks):
            chunk_path = os.path.join(temp_dir, f"chunk_{i}.mp3")
            logging.info(f"Saving chunk {i} ({len(chunk)}ms) to {chunk_path}")

            # Validate chunk before export
            if len(chunk) == 0:
                logging.error(f"Chunk {i} is empty, skipping")
                continue

            # Add export parameters for better quality control
            chunk.export(
                chunk_path,
                format="mp3",
                parameters=[
                    "-q:a",
                    "0",  # Highest quality
                    "-b:a",
                    "192k",  # Bitrate
                ],
            )

            # Verify exported file
            if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 0:
                chunk_paths.append(chunk_path)
                logging.info(f"Successfully saved chunk {i} to {chunk_path}")
            else:
                logging.error(f"Failed to save chunk {i} or file is empty")

        if not chunk_paths:
            logging.error("No chunks were successfully saved")
            st.error("Failed to save any audio chunks")

        return chunk_paths

    except Exception as e:
        logging.error(f"Error saving audio chunks: {str(e)}", exc_info=True)
        st.error(f"Error saving audio chunks: {str(e)}")
        return []


def transcribe_chunks(chunk_paths, progress_bar=None):
    """Transcribe audio chunks using Langchain's OpenAIWhisperParser"""
    try:
        transcriptions = []
        parser = OpenAIWhisperParser()

        for i, chunk_path in enumerate(chunk_paths):
            try:
                # Load and parse the audio chunk
                loader = GenericLoader.from_filesystem(chunk_path, parser=parser)
                docs = loader.load()

                if docs:
                    # Extract text from documents
                    for doc in docs:
                        transcriptions.append(doc.page_content)
                else:
                    logging.error(f"No text found in transcription for {chunk_path}")

                # Update progress if available
                if progress_bar:
                    progress = (i + 1) / len(chunk_paths)
                    progress_bar.progress(progress)

            except Exception as e:
                logging.error(
                    f"Error transcribing chunk {chunk_path}: {str(e)}", exc_info=True
                )
                st.error(f"Error transcribing chunk {chunk_path}")
                continue

        return transcriptions

    except Exception as e:
        logging.error(f"Error in transcription process: {str(e)}", exc_info=True)
        st.error("An error occurred during transcription")
        return []


@st.cache_data
def preview_transcription(chunk_path):
    """Preview transcription with first audio chunk using Langchain parser"""
    try:
        logging.info(f"Starting preview transcription for {chunk_path}")
        if not os.path.exists(chunk_path):
            logging.error(f"Preview chunk file not found: {chunk_path}")
            return None

        file_size = os.path.getsize(chunk_path)
        logging.info(f"Preview chunk file size: {file_size} bytes")

        if file_size == 0:
            logging.error("Preview chunk file is empty")
            return None

        # Use Langchain's parser for preview
        parser = OpenAIWhisperParser(response_format="verbose_json")
        loader = GenericLoader.from_filesystem(chunk_path, parser=parser)
        docs = loader.load()

        if docs:
            result = docs[0].page_content
            logging.info(f"Preview transcription successful: {result[:100]}...")
            return result
        else:
            logging.error("Preview transcription returned no documents")
            return None

    except Exception as e:
        logging.error(f"Error in preview transcription: {str(e)}", exc_info=True)
        st.error(f"Transcription error: {str(e)}")
        return None


def verify_api_key():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logging.error("OpenAI API key not found in environment")
        st.error("OpenAI API key not configured. Please check your settings.")
        return False
    logging.info("OpenAI API key verified")
    return True


# Modify transcribe_upload function
def transcribe_upload():
    """Transcribe an uploaded audio file."""
    st.session_state.transcript = None
    st.session_state.formatted_text = None

    if not verify_api_key():
        return

    if st.session_state.get("upload") is not None:
        file = st.session_state.upload
        try:
            with st.spinner("Processing audio file"):
                temp_file_path = os.path.join(temp_dir, file.name)
                # Save uploaded file
                with open(temp_file_path, "wb") as f:
                    f.write(file.getvalue())

                chunk_length_ms = 600000  # 10-minute chunks
                audio_chunks = split_audio(temp_file_path, chunk_length_ms)
                if not audio_chunks:
                    return

                # Save only first chunk for preview
                preview_chunk = save_chunks([audio_chunks[0]])
                if not preview_chunk:
                    return

                # Show preview of first chunk
                preview_text = preview_transcription(preview_chunk[0])
                if preview_text:
                    st.info("Preview of first segment:")
                    st.text(preview_text)

                    if st.button("Continue with full transcription"):
                        # Save remaining chunks
                        chunk_paths = save_chunks(audio_chunks)
                        if not chunk_paths:
                            return

                        # Transcribe chunks with progress bar
                        progress_bar = st.progress(0)
                        transcriptions = transcribe_chunks(chunk_paths, progress_bar)

                        if not transcriptions:
                            st.error("No transcriptions were generated")
                            return

                        # Join transcriptions and continue with existing formatting...
                        raw_text = " ".join(transcriptions)
                        logging.info(f"Raw transcription text: {raw_text}")

                        if not raw_text.strip():
                            logging.error("Transcription resulted in empty text.")
                            st.error(
                                "The transcription resulted in empty text. Please try a different audio file."
                            )
                            return

                        # Clean up with llm
                        prompt = ChatPromptTemplate.from_template(
                            "Format this transcript in markdown for readability. Raw transcript:\n{text}\nMarkdown formatted transcript:"
                        )
                        model = ChatOpenAI(
                            model=OPENAI_MODEL or "gpt-4o",
                            streaming=True,
                            callbacks=[StreamlitCallbackHandler(st.container())],
                        )

                        chain = prompt | model | StrOutputParser()
                        result_text = chain.invoke({"text": raw_text})

                        if not result_text:
                            logging.error("LLM returned an empty response.")
                            st.error(
                                "The LLM returned an empty response. Please check the input data or try again later."
                            )
                            return

                        expander = st.expander(
                            f"Raw transcript for {file.name}", expanded=True
                        )
                        expander.write(raw_text)

                        st.session_state.transcript = result_text
                else:
                    st.error(
                        "Could not generate preview. Please try a different audio file."
                    )

                # Clean up temporary files
                os.remove(temp_file_path)
                for path in preview_chunk:
                    os.remove(path)

        except Exception as e:
            logging.error(f"Error processing the uploaded file: {e}")
            st.error("An unexpected error occurred while processing the file.")


# Upload an audio file
with st.container():
    if st.session_state.get("upload") is None:
        st.file_uploader(
            label="Upload an audio file to convert to text",
            type=[
                "m4a",
                "mp3",
                "webm",
                "mp4",
                "mpga",
                "wav",
                "mpeg",
                "ogg",
                "oga",
                "flac",
            ],
            key="upload",
            on_change=transcribe_upload,
        )

if st.session_state.get("formatted_text") is not None:
    if st.download_button(
        "Download JSON",
        st.session_state.transcript.model_dump_json(indent=2),
        f"{st.session_state.get('file_name')} transcript.json",
    ):
        pass
    if st.download_button(
        "Download markdown",
        st.session_state.formatted_text,
        f"{st.session_state.get('file_name')} transcript.md",
    ):
        pass

if st.session_state.get("transcript") is not None:
    transcript = st.session_state.get("transcript")
    st.write("Transcript:")
    st.write(transcript)
    st.code(transcript)
    if st.button("Clear transcript"):
        st.session_state.clear()
        st.rerun()
