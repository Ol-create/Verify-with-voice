# make_dummy_audio.py
import numpy as np
import soundfile as sf

# Settings
sample_rate = 16000   # 16 kHz, as AASIST expects
duration = 3.0        # 3 seconds long
frequency = 440.0     # A4 note (440 Hz)

# Generate time axis
t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)

# Generate sine wave
audio = 0.5 * np.sin(2 * np.pi * frequency * t).astype(np.float32)

# Save as WAV
sf.write("test_audio.wav", audio, sample_rate)

print("✅ Dummy sine-wave saved as test_audio.wav")
