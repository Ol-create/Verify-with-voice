import PyPDF2
from app.utils.challenge import build_model_from_text, save_model

def load_training_text_from_pdf(pdf_path: str) -> str:
    """Extract raw text from a PDF file."""
    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text

if __name__ == "__main__":
    text = load_training_text_from_pdf("textbook.pdf")
    model = build_model_from_text(text, state_size=2)
    save_model(model)
    print("✅ Markov model trained and saved to app/utils/markov_model.json")
