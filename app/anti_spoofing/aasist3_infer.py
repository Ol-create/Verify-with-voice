# from model import aasist3
from app.third_party.AASIST3.model import aasist3
import torch
import torchaudio

# Load the model directly from Hugging Face Hub
model = aasist3.from_pretrained("MTUCI/AASIST3")
model.eval()

def aasist3_score(audio_path: str):
    """Compute spoof probability using the AASIST3 model from Hugging Face."""
    
    # Load and preprocess audio
    audio, sr = torchaudio.load(audio_path)

    # Ensure 16kHz mono
    if sr != 16000:
        audio = torchaudio.transforms.Resample(sr, 16000)(audio)
    if audio.shape[0] > 1:
        audio = torch.mean(audio, dim=0, keepdim=True)

    # Pad or truncate to 64600 samples (~4 sec)
    if audio.shape[1] < 64600:
        audio = torch.nn.functional.pad(audio, (0, 64600 - audio.shape[1]))
    else:
        audio = audio[:, :64600]

    # Run inference
    with torch.no_grad():
        output = model(audio)
        probabilities = torch.softmax(output, dim=1)
        prediction = torch.argmax(probabilities, dim=1)
    
    spoof_prob = probabilities[0, 1].item()
    return spoof_prob, prediction.item()

if __name__ == "__main__":
    audio_file = "compsample2.wav"  # change this to your test file
    score, label = aasist3_score(audio_file)
    print(f"\nFile: {audio_file}")
    print(f"Spoof probability: {score:.6f}")
    print(f"Prediction: {'Bonafide' if label == 0 else 'Spoof'}\n")
