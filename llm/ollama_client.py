import requests


FORMALITY_PROMPTS = {
    "Formal": (
        "Rewrite the following speech transcription in a formal, professional tone. "
        "Fix any transcription errors, remove filler words, and use complete sentences. "
        "Return only the rewritten text with no commentary."
    ),
    "Casual": (
        "Rewrite the following speech transcription in a casual, conversational tone. "
        "Fix obvious transcription errors but keep it natural and relaxed. "
        "Return only the rewritten text with no commentary."
    ),
}


class OllamaClient:
    def __init__(self, settings):
        self._settings = settings

    def _base_url(self) -> str:
        return self._settings.get("ollama_url", "http://localhost:11434").rstrip("/")

    def _model(self) -> str:
        return self._settings.get("ollama_model", "llama3.2")

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{self._base_url()}/api/tags", timeout=3)
            return resp.status_code == 200
        except (requests.ConnectionError, requests.Timeout):
            return False

    def list_models(self) -> list[str]:
        try:
            resp = requests.get(f"{self._base_url()}/api/tags", timeout=5)
            resp.raise_for_status()
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def rewrite(self, text: str, level: str) -> str:
        if level == "Neutral" or not text.strip():
            return text

        system_prompt = FORMALITY_PROMPTS.get(level, FORMALITY_PROMPTS["Formal"])

        payload = {
            "model": self._model(),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "stream": False,
        }

        try:
            resp = requests.post(
                f"{self._base_url()}/api/chat",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["message"]["content"].strip()
        except (requests.ConnectionError, requests.Timeout):
            print("[OllamaClient] Connection failed — returning original text")
            return text
        except Exception as e:
            print(f"[OllamaClient] Error: {e} — returning original text")
            return text
