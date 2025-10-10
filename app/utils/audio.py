# app/utils/audio.py

import os
import tempfile
import numpy as np
import soundfile as sf
import noisereduce as nr
import librosa
import torchaudio
from pathlib import Path
from pydub import AudioSegment
# from speechbrain.inference import EncoderClassifier
from speechbrain.inference import EncoderClassifier
from openai import OpenAI
from fastapi import HTTPException

# Load ECAPA model once
# speaker_model = EncoderClassifier.from_hparams(
#     source="speechbrain/spkrec-ecapa-voxceleb",
#     savedir="pretrained_models/ecapa",
#     run_opts={"local_files_only": False},
# )



os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["NO_GCE_CHECK"] = "true"
os.environ["HF_DATASETS_OFFLINE"] = "1"

MODEL_DIR = Path("app/pretrained_models/ecapa")

speaker_model = EncoderClassifier.from_hparams(
    source=str(MODEL_DIR),
    savedir=str(MODEL_DIR),
    run_opts={"local_files_only": True, "device": "cpu"},
    use_auth_token=False
)

print("✅ ECAPA model loaded 100% locally from:", MODEL_DIR)
# OpenAI client
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
client = OpenAI(api_key=OPENAI_API_KEY)


def convert_to_wav(input_path: str) -> str:
    """
    Convert input audio (e.g., .m4a, .mp3) to a temporary .wav file.
    Returns path to the converted file.
    """
    tmp_wav = tempfile.mktemp(suffix=".wav")
    audio = AudioSegment.from_file(input_path)
    audio.export(tmp_wav, format="wav")
    return tmp_wav


async def transcribe_audio(audio_path: str, language: str = "auto") -> str:
    """
    Use OpenAI Whisper API to transcribe audio in a specified language.

    Args:
        audio_path: Path to the audio file.
        language: ISO 639-1 code (e.g., "en", "fr", "yo", "ha").
                  Use "auto" to let Whisper detect automatically.
    """
    try:
        with open(audio_path, "rb") as f:
            # Automatically detect language if "auto" is passed
            kwargs = {"model": "whisper-1", "file": f}
            if language and language != "auto":
                kwargs["language"] = language

            transcript = client.audio.transcriptions.create(**kwargs)

        return transcript.text.strip()

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
