# app/utils/embedding.py

import os
import warnings
from speechbrain.pretrained import EncoderClassifier

# Suppress symlink warning on Windows
warnings.filterwarnings(
    "ignore",
    message=".*symlinks on Windows.*"
)

# Directory to cache pretrained model
MODEL_DIR = os.path.join("pretrained_models", "spkrec-ecapa-voxceleb")

# Load ECAPA-TDNN speaker embedding model
speaker_model = EncoderClassifier.from_hparams(
    source="speechbrain/spkrec-ecapa-voxceleb",
    savedir=MODEL_DIR,
    run_opts={"device": "cpu"}  # change to "cuda" if you want GPU
)
