# app/anti_spoofing/aasist.py

import json
import logging
import torch
import soundfile as sf
import tempfile
import os
import gc
import numpy as np
from pydub import AudioSegment
from threading import Lock

from app.third_party.aasist.models.AASIST import Model as AASISTModel

logger = logging.getLogger(__name__)

# --- Paths ---
CONFIG_PATH = "app/third_party/aasist/config/AASIST.conf"
WEIGHTS_PATH = "app/third_party/aasist/models/weights/AASIST.pth"

# --- Global lock for thread safety ---
_infer_lock = Lock()

# --- Load config ---
with open(CONFIG_PATH, "r") as f:
    cfg = json.load(f)
d_args = cfg["model_config"]

# --- Load model once ---
_aasist = AASISTModel(d_args)
_aasist.load_state_dict(torch.load(WEIGHTS_PATH, map_location="cpu"))
_aasist.eval()


def preprocess_audio(audio_path: str, target_sr=16000):
    """Ensure consistent waveform and normalization."""
    audio = AudioSegment.from_file(audio_path)
    audio = audio.set_channels(1).set_frame_rate(target_sr)
    samples = np.array(audio.get_array_of_samples()).astype(np.float32)
    samples /= np.max(np.abs(samples)) + 1e-8  # normalize to [-1, 1]
    return samples, target_sr


def aasist_score(audio_path: str) -> float:
    """
    Thread-safe AASIST inference.
    Returns probability of spoof (float between 0–1).
    """
    tmp_wav = None
    x = None
    try:
        # ✅ Convert to WAV if needed
        if not audio_path.lower().endswith(".wav"):
            fd, tmp_wav = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            audio = AudioSegment.from_file(audio_path)
            audio.export(tmp_wav, format="wav")
            audio_path = tmp_wav

        # ✅ Load and normalize
        wav, sr = sf.read(audio_path)
        if wav.ndim > 1:
            wav = wav.mean(axis=1)
        wav = wav.astype(np.float32)
        wav /= np.max(np.abs(wav)) + 1e-8

        x = torch.tensor(wav, dtype=torch.float32).unsqueeze(0)

        # ✅ Thread-safe inference
        with _infer_lock:
            with torch.no_grad():
                _, logits = _aasist(x)
                prob = torch.softmax(logits, dim=1)[0, 1].item()

        return float(prob)

    except Exception:
        logger.exception("AASIST failed on %s, treating the audio as spoofed", audio_path)
        return 1.0  # fail-safe: treat as spoof

    finally:
        # ✅ Cleanup
        if tmp_wav and os.path.exists(tmp_wav):
            os.remove(tmp_wav)
        del x
        gc.collect()
        torch.cuda.empty_cache()
