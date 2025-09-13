import os
from openai import OpenAI
from difflib import SequenceMatcher
import numpy as np
import torchaudio
# from app.utils.audio import denoise_audio
from app.utils.embedding import speaker_model


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "sk-your-key")
client = OpenAI(api_key=OPENAI_API_KEY)


def transcribe_audio(file_path: str) -> str:
    """Send audio to OpenAI Whisper for transcription."""
    with open(file_path, "rb") as f:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=f
        )
    return transcript.text.strip()


def compute_embedding(audio_path: str) -> np.ndarray:
    """Denoise, resample to 16kHz, and compute ECAPA speaker embedding."""
    clean_path = denoise_audio(audio_path)

    try:
        signal, fs = torchaudio.load(clean_path)

        # Resample if needed (ECAPA expects 16kHz)
        if fs != 16000:
            resampler = torchaudio.transforms.Resample(orig_freq=fs, new_freq=16000)
            signal = resampler(signal)

        # Ensure shape (batch, samples)
        if signal.dim() == 2 and signal.shape[0] == 1:
            signal = signal.squeeze(0).unsqueeze(0)

        embedding = speaker_model.encode_batch(signal)
        return embedding.squeeze().detach().cpu().numpy().astype(np.float32)
    finally:
        if os.path.exists(clean_path):
            os.remove(clean_path)


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Safe cosine similarity between two vectors."""
    denom = np.linalg.norm(vec1) * np.linalg.norm(vec2)
    if denom == 0:
        return 0.0
    return float(np.dot(vec1, vec2) / denom)


def fuzzy_match(transcript: str, challenge: str, threshold: float = 0.8) -> tuple[bool, float]:
    """
    Compare transcript to challenge phrase using fuzzy ratio.

    Returns:
        (bool: match, float: similarity ratio)
    """
    ratio = SequenceMatcher(None, transcript.lower(), challenge.lower()).ratio()
    return ratio >= threshold, ratio
