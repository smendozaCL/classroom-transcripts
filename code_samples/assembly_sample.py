# Start by making sure the `assemblyai` package is installed.
# If not, you can install it by running the following command:
# pip install -U assemblyai
#
# Note: Some macOS users may need to use `pip3` instead of `pip`.
import os
import assemblyai as aai

# Replace with your API key
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")

# URL of the file to transcribe
FILE_URL = "https://assemblyaiusercontent.com/playground/CLx_YCjLXcb.m4a"

# You can also transcribe a local file by passing in a file path
# FILE_URL = './path/to/file.mp3'

# You can set additional parameters for the transcription
config = aai.TranscriptionConfig(
    speech_model=aai.SpeechModel.best,
    iab_categories=True,
    auto_chapters=True,
    content_safety=True,
    auto_highlights=True,
    sentiment_analysis=True,
    speaker_labels=True,
    filter_profanity=True,
    language_detection=True,
).set_redact_pii(
    policies=[
        aai.PIIRedactionPolicy.medical_condition,
        aai.PIIRedactionPolicy.email_address,
        aai.PIIRedactionPolicy.phone_number,
        aai.PIIRedactionPolicy.banking_information,
        aai.PIIRedactionPolicy.credit_card_number,
        aai.PIIRedactionPolicy.credit_card_cvv,
        aai.PIIRedactionPolicy.date_of_birth,
        aai.PIIRedactionPolicy.person_name,
        aai.PIIRedactionPolicy.organization,
        aai.PIIRedactionPolicy.location,
    ],
    redact_audio=True,
    substitution=aai.PIISubstitutionPolicy.hash,
)

transcriber = aai.Transcriber(config=config)
transcript = transcriber.transcribe(FILE_URL)

if transcript.status == aai.TranscriptStatus.error:
    print(transcript.error)
else:
    print(transcript.text)
