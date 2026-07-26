from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from packages.shared.config import Settings, get_settings


@dataclass(slots=True)
class ModelResponse:
    content: str
    model: str
    provider: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_duration_ns: int | None = None


class OllamaProvider:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def health(self, timeout: float = 1.5) -> dict[str, Any]:
        try:
            with httpx.Client(trust_env=False, timeout=timeout) as client:
                response = client.get(
                    f"{self.settings.ollama_base_url.rstrip('/')}/api/tags"
                )
            response.raise_for_status()
            models = [
                item.get("name", "")
                for item in response.json().get("models", [])
                if item.get("name")
            ]
            return {
                "status": "ok",
                "configured_model": self.settings.ollama_model,
                "available_models": models,
            }
        except (httpx.HTTPError, ValueError) as exc:
            return {
                "status": "unavailable",
                "configured_model": self.settings.ollama_model,
                "error": type(exc).__name__,
            }

    def generate(
        self,
        *,
        system: str,
        prompt: str,
        temperature: float = 0.1,
        timeout: float = 90,
    ) -> ModelResponse:
        with httpx.Client(trust_env=False, timeout=timeout) as client:
            response = client.post(
                f"{self.settings.ollama_base_url.rstrip('/')}/api/chat",
                json={
                    "model": self.settings.ollama_model,
                    "stream": False,
                    "think": False,
                    "keep_alive": "10m",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "options": {
                        "temperature": temperature,
                        "num_ctx": 6144,
                        "num_predict": 1200,
                    },
                },
            )
        response.raise_for_status()
        payload = response.json()
        return ModelResponse(
            content=payload["message"]["content"],
            model=payload.get("model", self.settings.ollama_model),
            provider="ollama",
            prompt_tokens=payload.get("prompt_eval_count"),
            completion_tokens=payload.get("eval_count"),
            total_duration_ns=payload.get("total_duration"),
        )
