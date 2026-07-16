"""Adaptador OpenRouter: chat com saída JSON e síntese de voz.

A regra de negócio (pipeline) só conhece as funções deste módulo, nunca o provedor.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import requests

from .config import OPENROUTER_BASE_URL, Settings

_HEADERS_EXTRA = {
    "HTTP-Referer": "https://github.com/Felipe-Alcantara/Akita-On-Rails-to-Podcast",
    "X-Title": "Akita on Rails to Podcast",
}

_MAX_RETRIES = 3
_TIMEOUT = 300


class OpenRouterError(RuntimeError):
    pass


def _post(settings: Settings, endpoint: str, payload: dict[str, Any]) -> requests.Response:
    headers = {"Authorization": f"Bearer {settings.require_api_key()}", **_HEADERS_EXTRA}
    last_error: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = requests.post(
                f"{OPENROUTER_BASE_URL}{endpoint}", json=payload,
                headers=headers, timeout=_TIMEOUT,
            )
            if response.status_code in (429, 500, 502, 503):
                raise OpenRouterError(f"HTTP {response.status_code} (transitório)")
            if response.status_code != 200:
                # Não logar o corpo integral: pode ecoar conteúdo ou detalhes do provedor.
                raise OpenRouterError(
                    f"HTTP {response.status_code} em {endpoint}: {response.text[:300]}"
                )
            return response
        except requests.RequestException as error:
            last_error = error
        except OpenRouterError as error:
            last_error = error
            if "transitório" not in str(error):
                raise
        if attempt < _MAX_RETRIES:
            time.sleep(2**attempt)
    raise OpenRouterError(f"Falha após {_MAX_RETRIES} tentativas em {endpoint}: {last_error}")


def _extract_json(text: str) -> Any:
    """Aceita JSON puro ou cercado por ```json ... ```."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=0)
    return json.loads(text[start:])


def chat_json(settings: Settings, model: str, system: str, user: str) -> Any:
    """Chamada de chat que exige resposta JSON e a devolve já decodificada."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.4,
    }
    response = _post(settings, "/chat/completions", payload)
    body = response.json()
    content = body["choices"][0]["message"]["content"]
    usage = body.get("usage", {})
    print(
        f"    [{model}] tokens: {usage.get('prompt_tokens', '?')} entrada / "
        f"{usage.get('completion_tokens', '?')} saída"
    )
    try:
        return _extract_json(content)
    except (json.JSONDecodeError, ValueError) as error:
        raise OpenRouterError(f"Modelo {model} não retornou JSON válido: {error}") from error


def text_to_speech(settings: Settings, text: str, voice: str, instructions: str = "") -> bytes:
    """Sintetiza um turno de fala e retorna os bytes de áudio."""
    payload: dict[str, Any] = {
        "model": settings.tts_model,
        "input": text,
        "voice": voice,
        "response_format": settings.tts_format,
    }
    if instructions:
        payload["instructions"] = instructions
    response = _post(settings, "/audio/speech", payload)
    content_type = response.headers.get("Content-Type", "")
    if "json" in content_type:
        raise OpenRouterError(f"TTS retornou JSON em vez de áudio: {response.text[:300]}")
    if len(response.content) < 512:
        raise OpenRouterError("TTS retornou resposta vazia ou curta demais.")
    return response.content
