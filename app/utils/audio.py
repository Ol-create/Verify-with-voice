import numpy as np
import torchaudio
from speechbrain.inference import EncoderClassifier


# Load ECAPA once
speaker_model = EncoderClassifier.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb",
    savedir="pretrained_models/ecapa",
    run_opts={"local_files_only": False},
)
print("✅ ECAPA model loaded")


class IdentityDenoiser:
    def enhance_batch(self, x):
        # placeholder denoiser - pass-through
        return x


denoiser = IdentityDenoiser()


def compute_embedding(audio_path: str):
    """Load audio and compute ECAPA embedding as float32 numpy array."""
    signal, fs = torchaudio.load(audio_path)

    # Resample to 16kHz if needed (ECAPA is trained on 16kHz)
    if fs != 16000:
        resampler = torchaudio.transforms.Resample(orig_freq=fs, new_freq=16000)
        signal = resampler(signal)
        fs = 16000

    # Ensure shape (batch, samples)
    if signal.dim() == 2 and signal.shape[0] == 1:
        signal = signal.squeeze(0).unsqueeze(0)

    enhanced = denoiser.enhance_batch(signal)
    emb = speaker_model.encode_batch(enhanced)
    arr = emb.squeeze().detach().cpu().numpy().astype(np.float32)
    return arr
