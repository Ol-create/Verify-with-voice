# train_markov.py
from app.utils.challenge import load_training_text, build_model_from_text, save_model

if __name__ == "__main__":
    text = load_training_text("textbook.txt")
    model = build_model_from_text(text, state_size=2)
    save_model(model)
    print("✅ Markov model trained and saved to app/utils/markov_model.json")
