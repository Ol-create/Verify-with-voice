import markovify
import os
import random

MODEL_PATH = "app/utils/markov_model.json"

def load_training_text(file_path: str) -> str:
    """Load raw text from a textbook file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Training file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()

def build_model_from_text(text: str, state_size: int = 2):
    """Train a Markov model from supplied text."""
    return markovify.Text(text, state_size=state_size)

def save_model(model, path: str = MODEL_PATH):
    """Save trained model to JSON for reuse."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(model.to_json())

def load_model(path: str = MODEL_PATH):
    """Load trained Markov model from JSON."""
    if not os.path.exists(path):
        raise FileNotFoundError("Markov model JSON not found. Train it first.")
    with open(path, "r", encoding="utf-8") as f:
        return markovify.Text.from_json(f.read())

def generate_challenge(num_words: int = 5) -> str:
    """Generate a random short phrase for liveness challenge."""
    try:
        model = load_model()
    except FileNotFoundError:
        # fallback to tiny default text
        default_text = "The quick brown fox jumps over the lazy dog."
        model = markovify.Text(default_text)

    sentence = None
    tries = 0
    while sentence is None and tries < 5:
        sentence = model.make_sentence(tries=100)
        tries += 1

    if not sentence:
        sentence = "Please say your verification phrase now."

    return " ".join(sentence.split()[:num_words])
