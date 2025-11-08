from openai import AsyncOpenAI
import os

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def generate_challenge_sentence(lang: str) -> str:
    """
    Generate a random sequence of 3-4 numbers (range: 1–100)
    written in words, separated by spaces.
    Example: 'three eight one five six'
    """
    prompt = (
        "Generate a random sequence of 5 numbers written in words. "
        f"in the given {lang}. "
        "The numbers should range from zero to twenty, separated by spaces. "
        "Do not add punctuation or extra text."
    )

    # """
    # Generate a random sentence of 5–7 words
    # in the given language.
    # Example: 'the quick brown fox jumps high'
    # """
    # prompt = (
    #     "Generate a random sentence of 5 to 7 words "
    #     f"in the given {lang}. "
    #     "Do not add punctuation or extra text."
    # )

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
    If the text has no digits, it returns the original text.
    """
    # if not any(char.isdigit() for char in text):
    #     return text  # no digits, return as-is

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
    except Exception as e:
        # You can add optional logging here
        # return text  # fallback to original text if conversion fails
        print(f"OpenAI conversion error: {e}")

