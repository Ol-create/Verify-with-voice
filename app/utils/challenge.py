import time
import httpx
from app.config import settings


# In-memory store: production should use Redis or DB with TTL
ACTIVE_CHALLENGES = {}


async def generate_phrase(user_id: str, ttl: int = 5):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
    json_payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Generate a short random phrase (3-6 words)."}
        ],
        "max_tokens": 16,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=json_payload)
        if resp.status_code != 200:
            raise RuntimeError(f"OpenAI error: {resp.status_code} - {resp.text}")

        phrase = resp.json()["choices"][0]["message"]["content"].strip()
        ACTIVE_CHALLENGES[user_id] = {"phrase": phrase, "expires": time.time() + ttl}
        return phrase


def validate_challenge(user_id: str, phrase: str) -> bool:
    data = ACTIVE_CHALLENGES.get(user_id)
    if not data:
        return False

    if time.time() > data["expires"]:
        # expired
        del ACTIVE_CHALLENGES[user_id]
        return False

    # case-insensitive match (you can make it fuzzy if needed)
    ok = data["phrase"].strip().lower() == phrase.strip().lower()

    # consume challenge
    del ACTIVE_CHALLENGES[user_id]
    return ok
