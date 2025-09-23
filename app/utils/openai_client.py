from openai import AsyncOpenAI
import os

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def generate_challenge_sentence(lang: str) -> str:
    """
    Generate a short random challenge sentence (5–7 words)
    in the requested language using OpenAI.
    """
    prompt = f"Generate a random short sentence of 5–7 words in {lang}. \
It should be natural and easy to read aloud."

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=30,
        temperature=0.8,
    )

    return response.choices[0].message["content"].strip()
