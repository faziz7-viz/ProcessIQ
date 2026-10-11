"""Explicit, session-only recording transcription through the existing provider."""

import io
import wave

from openai import OpenAI, APIConnectionError, APIStatusError, APITimeoutError
from processiq.interview import MAX_MESSAGE_CHARS
from processiq.llm import InterviewError, load_api_configuration


def transcribe_recording(audio: bytes, *, client=None) -> str:
    """Return editable text only. This function never advances the interview."""
    try:
        if not audio or len(audio) > 4_000_000:
            raise ValueError
        with wave.open(io.BytesIO(audio)) as recording:
            seconds = recording.getnframes() / recording.getframerate()
            if not 0 < seconds <= 120:
                raise ValueError
    except (ValueError, wave.Error, EOFError, ZeroDivisionError):
        raise InterviewError("Use a recording of up to two minutes, or type your answer.") from None

    def transcribe(provider):
        return provider.audio.transcriptions.create(
            model="gpt-4o-mini-transcribe", file=("answer.wav", audio, "audio/wav"),
        ).text

    try:
        if client is not None:
            text = transcribe(client)
        else:
            key = load_api_configuration().get("api_key")
            if not key:
                raise InterviewError("Audio transcription needs the existing OpenAI API key. You can still type your answer.")
            with OpenAI(api_key=key, base_url="https://api.openai.com/v1", timeout=30, max_retries=0) as provider:
                text = transcribe(provider)
    except (APIConnectionError, APITimeoutError, APIStatusError):
        raise InterviewError("The recording could not be transcribed. Your answer is unchanged. Try again or type your answer.") from None
    if not isinstance(text, str) or not text.strip():
        raise InterviewError("No speech was transcribed. Try recording again or type your answer.")
    if len(text.strip()) > MAX_MESSAGE_CHARS:
        raise InterviewError("That recording is too long for one answer. Record a shorter answer or type it.")
    return " ".join(text.split())
