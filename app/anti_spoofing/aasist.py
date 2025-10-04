# app/anti_spoofing/aasist.py

import json
import torch
import soundfile as sf
from app.third_party.aasist.models.AASIST import Model as AASISTModel

# --- Paths ---
CONFIG_PATH = "app/third_party/aasist/config/AASIST.conf"
WEIGHTS_PATH = "app/third_party/aasist/models/weights/AASIST.pth"

# --- Load config (d_args) ---
with open(CONFIG_PATH, "r") as f:
    cfg = json.load(f)
d_args = cfg["model_config"]

# --- Load AASIST once (global) ---
_aasist = AASISTModel(d_args)
_aasist.load_state_dict(torch.load(WEIGHTS_PATH, map_location="cpu"))
_aasist.eval()

def aasist_score(audio_path: str) -> float:
    """
    Run AASIST spoof detection on an audio file.
    Returns probability of spoof (float between 0–1).
    """
    wav, sr = sf.read(audio_path)
    if wav.ndim > 1:  # stereo → mono
        wav = wav.mean(axis=1)

    x = torch.tensor(wav, dtype=torch.float32).unsqueeze(0)
    with torch.no_grad():
        _, logits = _aasist(x)
        prob = torch.softmax(logits, dim=1)[0, 1].item()  # spoof class
    return float(prob)
