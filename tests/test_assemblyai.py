import os
import assemblyai as aai
from dotenv import load_dotenv

# Load environment variables
load_dotenv(".env.local")


def test_assemblyai_connection():
    """Test basic AssemblyAI API connectivity."""
    api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not api_key:
        raise ValueError("ASSEMBLYAI_API_KEY not found in environment variables")

    print(f"\nTesting AssemblyAI API key: {api_key[:4]}...{api_key[-4:]}")
    aai.settings.api_key = api_key

    # Create a transcriber instance
    transcriber = aai.Transcriber()

    # Test with a small public audio file
    audio_url = "https://github.com/AssemblyAI-Examples/audio-examples/raw/main/20230607_me_30sec.mp3"
    print(f"\nSubmitting test transcription for: {audio_url}")

    try:
        transcript = transcriber.transcribe(audio_url)
        print("\nTranscription successful!")
        print(f"Transcript ID: {transcript.id}")
        print(f"Status: {transcript.status}")
        print(f"Text: {transcript.text}")
        return True
    except Exception as e:
        print(f"\nError testing AssemblyAI API: {str(e)}")
        return False


if __name__ == "__main__":
    test_assemblyai_connection()
