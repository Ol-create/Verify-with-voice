import logging
import os

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def generate_challenge_sentence(lang: str) -> str:
    """
    Generate a random sequence of 5 numbers (range: 0–20)
    written in words, separated by spaces.
    Example: 'three eight one five six'
    """
    prompt = (
        "Generate a random sequence of 5 numbers written in words. "
        f"in the given {lang}. "
        "The numbers should range from 0 to 20, separated by spaces. "
        "Do not add punctuation or extra text."
    )

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=30,
        temperature=0.8,
    )

    # ✅ Use .content instead of ["content"]
    return response.choices[0].message.content.strip()


async def convert_digits_to_words(text: str, lang: str) -> str:
    """
    Converts any digits (e.g., '23 45') into their word equivalents
    in the given language using OpenAI.
    Falls back to the original text if the conversion fails.
    """
    prompt = (
        f"Convert the following digits into their corresponding words in {lang}. "
        "Write only the converted numbers in words, separated by spaces, with no punctuation or explanations.\n\n"
        f"Text: {text.strip()}"
    )

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50,
            temperature=0.3,
        )
        return response.choices[0].message.content.strip()
    except Exception:
        logger.warning("Digit-to-word conversion failed, using the raw transcript", exc_info=True)
        return text
