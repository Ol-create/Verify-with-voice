# import sys
# sys.path.append("app/third_party/aasist")
# sys.path.append("app/asvspoof_baseline")

# import torch
# import soundfile as sf
# import numpy as np
# import joblib

# # --- AASIST ---
# from app.third_party.aasist.models.AASIST import Model as AASISTModel

# # --- LCNN + LFCC ---
# from baseline.lcnn.model import LCNN
# from baseline.features.lfcc import extract_lfcc

# # --- CQCC-GMM ---
# from baseline.features.cqcc import extract_cqcc

# # 1. Load audio
# wav, sr = sf.read("test_audio.wav")

# # 2. AASIST
# aasist = AASISTModel()
# aasist.load_state_dict(torch.load("app/third_party/aasist/models/weights/AASIST.pth", map_location="cpu"))
# aasist.eval()
# aasist_score = aasist(torch.tensor(wav).unsqueeze(0)).item()

# # 3. LCNN
# lfcc_feats = extract_lfcc(wav, sr)
# lcnn = LCNN()
# lcnn.load_state_dict(torch.load("weights/lcnn_asvspoof2021.pth", map_location="cpu"))
# lcnn.eval()
# lcnn_score = lcnn(torch.tensor(lfcc_feats).unsqueeze(0).unsqueeze(0).float()).item()

# # 4. CQCC-GMM
# cqcc_feats = extract_cqcc(wav, sr)
# cqcc_gmm = joblib.load("weights/cqcc_gmm.pkl")
# cqcc_score = cqcc_gmm.score(cqcc_feats)

# print("AASIST:", aasist_score)
# print("LCNN:", lcnn_score)
# print("CQCC:", cqcc_score)

from app.anti_spoofing.aasist import aasist_score

score = aasist_score("test_audio.wav")
print("Spoof probability:", score)

