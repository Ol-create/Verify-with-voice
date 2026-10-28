# app/utils/audio.py

import logging
import os
import tempfile
import numpy as np
import soundfile as sf
import noisereduce as nr
import librosa
import torchaudio
from pathlib import Path
from pydub import AudioSegment
from speechbrain.inference import EncoderClassifier
from openai import OpenAI
from fastapi import HTTPException

logger = logging.getLogger(__name__)

MODEL_DIR = Path("pretrained_models/ecapa")

speaker_model = EncoderClassifier.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb",
    savedir=str(MODEL_DIR),
    run_opts={"device": "cpu"},
)
logger.info("ECAPA speaker model loaded from %s", MODEL_DIR)

# OpenAI client
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_API_KEY)


def convert_to_wav(input_path: str) -> str:
    """
    Convert input audio (e.g., .m4a, .mp3) to a temporary .wav file.
    Returns path to the converted file.
    """
    # Written next to the input, so the caller's temp dir clean-up removes it too
    fd, tmp_wav = tempfile.mkstemp(suffix=".wav", dir=os.path.dirname(os.path.abspath(input_path)))
    os.close(fd)
    audio = AudioSegment.from_file(input_path)
    audio.export(tmp_wav, format="wav")
    return tmp_wav


async def transcribe_audio(audio_path: str, language: str = "auto") -> str:
    """
    Use OpenAI Whisper API to transcribe audio in a specified language.
    """
    try:
        with open(audio_path, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=("audio.wav", f, "audio/wav"),
                language=None if language == "auto" else language,
                response_format="text",
            )

        # Some SDK versions return `str`, others return `Transcription` object
        text = transcript if isinstance(transcript, str) else getattr(transcript, "text", "")
        return text.strip()

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Whisper transcription failed: {str(e)}")


def compute_embedding(audio_path: str) -> np.ndarray:
    """Convert if needed, denoise, resample, and compute ECAPA embedding."""
    tmp_converted = None
    tmp_cleaned = None

    try:
        # Convert unsupported formats
        if audio_path.lower().endswith((".m4a", ".mp3")):
            tmp_converted = convert_to_wav(audio_path)
            audio_path = tmp_converted

        # Load + denoise
        y, sr = librosa.load(audio_path, sr=None)
        reduced = nr.reduce_noise(y=y, sr=sr)

        # Save cleaned audio
        tmp_cleaned = tempfile.mktemp(suffix=".wav")
        sf.write(tmp_cleaned, reduced, sr)

        # Load with torchaudio
        signal, fs = torchaudio.load(tmp_cleaned)

        # Resample if needed
        if fs != 16000:
            resampler = torchaudio.transforms.Resample(orig_freq=fs, new_freq=16000)
            signal = resampler(signal)

        # Ensure correct shape
        if signal.dim() == 2 and signal.shape[0] == 1:
            signal = signal.squeeze(0).unsqueeze(0)

        # Speaker embedding
        emb = speaker_model.encode_batch(signal)
        return emb.squeeze().detach().cpu().numpy().astype(np.float32)

    finally:
        # Cleanup temporary files
        if tmp_converted and os.path.exists(tmp_converted):
            os.remove(tmp_converted)
        if tmp_cleaned and os.path.exists(tmp_cleaned):
            os.remove(tmp_cleaned)
