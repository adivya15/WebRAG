import os
from pathlib import Path
import httpx
from dotenv import load_dotenv

# Ensure .env from atlasai_backend is loaded
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=_env_path, override=True)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-120b"
CANDIDATE_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
]


async def chat_completion(system_prompt: str, user_prompt: str, model: str = DEFAULT_MODEL) -> str:
    # Re-read .env so any updates to GROQ_API_KEY apply instantly without server restart
    load_dotenv(dotenv_path=_env_path, override=True)
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or api_key == "your_groq_api_key_here" or api_key.startswith("your_"):
        raise RuntimeError(
            "GROQ_API_KEY is not configured or still set to the placeholder in atlasai_backend/.env. "
            "Please obtain a free key at https://console.groq.com/keys and set GROQ_API_KEY."
        )

    # Models to attempt in order
    models_to_try = [model] + [m for m in CANDIDATE_MODELS if m != model]

    async with httpx.AsyncClient(timeout=30.0) as client:
        last_err = None
        for m in models_to_try:
            try:
                res = await client.post(
                    GROQ_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": m,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": 0.2,
                    },
                )
                if res.status_code == 200:
                    data = res.json()
                    return data["choices"][0]["message"]["content"]
                elif res.status_code == 401:
                    raise RuntimeError("Groq API 401 Unauthorized: Invalid or expired GROQ_API_KEY.")
                elif res.status_code in (400, 404):
                    # Model decommissioned or not found, try next candidate
                    last_err = RuntimeError(f"Groq API error ({res.status_code}): {res.text}")
                    continue
                else:
                    res.raise_for_status()
            except httpx.HTTPStatusError as e:
                last_err = e
            except RuntimeError:
                raise
            except Exception as e:
                last_err = e

        raise last_err or RuntimeError("Failed to obtain completion from any Groq model.")


