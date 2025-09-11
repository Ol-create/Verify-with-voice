import os
import tempfile
import numpy as np
import librosa
import noisereduce as nr
import soundfile as sf
import torchaudio
from speechbrain.inference import EncoderClassifier


# Load ECAPA once (global)
speaker_model = EncoderClassifier.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb",
    savedir="pretrained_models/ecapa",
    run_opts={"local_files_only": False},
)
print("✅ ECAPA model loaded")


def compute_embedding(audio_path: str) -> np.ndarray:
    """Denoise audio, resample, and compute ECAPA embedding as float32 numpy array."""

    # --- Step 1: Denoise with librosa + noisereduce ---
    y, sr = librosa.load(audio_path, sr=None)
    reduced = nr.reduce_noise(y=y, sr=sr)

    # --- Step 2: Write to a temporary cleaned file ---
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmpfile:
        sf.write(tmpfile.name, reduced, sr)
        cleaned_path = tmpfile.name

    try:
        # --- Step 3: Load with torchaudio ---
        signal, fs = torchaudio.load(cleaned_path)

        # --- Step 4: Resample to 16kHz if needed ---
        if fs != 16000:
            resampler = torchaudio.transforms.Resample(orig_freq=fs, new_freq=16000)
            signal = resampler(signal)
            fs = 16000

        # --- Step 5: Ensure shape (batch, samples) ---
        if signal.dim() == 2 and signal.shape[0] == 1:
            signal = signal.squeeze(0).unsqueeze(0)

        # --- Step 6: Compute embedding ---
        emb = speaker_model.encode_batch(signal)
        arr = emb.squeeze().detach().cpu().numpy().astype(np.float32)

        return arr
    finally:
        # --- Step 7: Clean up temporary file ---
        if os.path.exists(cleaned_path):
            os.remove(cleaned_path)
