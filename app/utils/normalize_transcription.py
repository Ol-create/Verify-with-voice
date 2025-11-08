from word2number import w2n
import re
from num2words import num2words

def normalize_numbers_to_words(text: str) -> str:
    """Convert digits to words for consistent comparison without punctuation."""
    def replace_num(match):
        number = int(match.group(0))
        # Convert to words, remove punctuation and extra spaces
        words = num2words(number)
        words = re.sub(r'[^\w\s]', '', words)  # remove punctuation
        return words
    return re.sub(r'\d+', replace_num, text.lower())
