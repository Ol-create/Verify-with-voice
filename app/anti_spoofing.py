# app/anti_spoofing.py
import torch
import numpy as np
import librosa
import soundfile as sf

# Import third-party code
# (adjust paths depending on where submodules are placed)
import sys
sys.path.append("app/third_party/aasist")
sys.path.append("app/third_party/asvspoof_baselines")

# Lazy globals
_AASIST_MODEL = None
_LCNN_MODEL = None
_CQCC_GMM = None


def load_models(aasist_ckpt: str, lcnn_ckpt: str, cqcc_gmm_ckpt: str):
    """Load all anti-spoof models once at app startup"""
    global _AASIST_MODEL, _LCNN_MODEL, _CQCC_GMM

    if _AASIST_MODEL is None:
        from aasist.model import AASIST  # adjust to real class
        _AASIST_MODEL = AASIST()
        state = torch.load(aasist_ckpt, map_location="cpu")
        _AASIST_MODEL.load_state_dict(state)
        _AASIST_MODEL.eval()

    if _LCNN_MODEL is None:
        from asvspoof_baselines.lcnn.model import LCNN
        _LCNN_MODEL = LCNN()
        state = torch.load(lcnn_ckpt, map_location="cpu")
        _LCNN_MODEL.load_state_dict(state)
        _LCNN_MODEL.eval()

    if _CQCC_GMM is None:
        import joblib
        _CQCC_GMM = joblib.load(cqcc_gmm_ckpt)  # pretrained sklearn GMM

    return True


def aasist_score(audio_path: str) -> float:
    y, sr = sf.read(audio_path)
    y = torch.tensor(y).unsqueeze(0).float()
    with torch.no_grad():
        out = _AASIST_MODEL(y)  # logits
        prob = torch.sigmoid(out).item()
    return prob  # 0..1 (higher = spoof)


def lcnn_score(audio_path: str) -> float:
    y, sr = librosa.load(audio_path, sr=16000)
    feats = torch.tensor(y).unsqueeze(0).unsqueeze(0)  # adjust
    with torch.no_grad():
        out = _LCNN_MODEL(feats)
        prob = torch.sigmoid(out).item()
    return prob


def cqcc_gmm_score(audio_path: str) -> float:
    y, sr = librosa.load(audio_path, sr=16000)
    # Extract CQCC features using baseline code
    from asvspoof_baselines.features import cqcc_extract
    feats = cqcc_extract(y, sr)
    loglik = _CQCC_GMM.score(feats)  # log likelihood ratio
    # Normalize into [0,1] via logistic
    prob = 1.0 / (1.0 + np.exp(-loglik))
    return float(prob)
