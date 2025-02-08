import assemblyai as aai
import os

# Add debug logging
print(f"Current working directory: {os.getcwd()}")
print(f"Environment variables available: {os.environ.get('ASSEMBLYAI_API_KEY')}")

# Set API key in environment variables as 
api_key = os.getenv("ASSEMBLYAI_API_KEY")
print(f"API key loaded: {'Yes' if api_key else 'No'}")

if not api_key:
    raise ValueError("ASSEMBLYAI_API_KEY not found in environment variables")

aai.settings.api_key = api_key

transcriber = aai.Transcriber()

# local file - this will need to be a publicly accessible URL

audio_url = "data/short-classroom-sample.m4a"

# this step adds speaker labels, diarization, we want to add timestamps, and PII Redaction

config = aai.TranscriptionConfig(speaker_labels=True).set_redact_pii(
    policies=[
        aai.PIIRedactionPolicy.person_name,
        aai.PIIRedactionPolicy.organization,
        aai.PIIRedactionPolicy.occupation,
    ],
    substitution=aai.PIISubstitutionPolicy.hash,
)

# lets you know what will be transcribed
transcript = transcriber.transcribe(audio_url, config)

# handles errors
if transcript.status == aai.TranscriptStatus.error:
    print(f"Transcription failed: {transcript.error}")
    exit(1)

# we need to work on formatting here
print(transcript.text)

# for utterance in transcript.utterances:
#     print(f"Speaker {utterance.speaker}: {utterance.text}")

# this is where you change out the LLM you're using, for example
# Claude 3.5 Sonnet
# Claude 3 Opus
# Claude 3 Haiku
# Claude 3 Sonnet

# this is an LLM prompt request, and not a direct request to AssemblyAI
# prompt = "Provide a timestamped, diarized version of the transcript."

# result = transcript.lemur.task(prompt, final_model=aai.LemurModel.claude3_5_sonnet)
