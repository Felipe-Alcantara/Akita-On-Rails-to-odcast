"""Adaptador OpenRouter: chat JSON com custo por chamada, TTS, catálogo e uso da conta.

Custo em tempo real:
- chat: o payload pede `usage.include`, e a resposta traz `usage.cost` exato em US$;
- TTS: a resposta é binária e não carrega custo; o pipeline acompanha pelo delta de
  `total_usage` da conta (endpoint /credits), uma aproximação honesta documentada no README.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

import requests

from ..config import OPENROUTER_BASE_URL, Settings

_HEADERS_EXTRA = {
    "HTTP-Referer": "https://github.com/Felipe-Alcantara/Audiofy-Content-AI",
    "X-Title": "Audiofy Content AI",
}

_MAX_RETRIES = 3
_TIMEOUT = 300

# Vozes do Gemini TTS (documentação oficial do modelo), com o caráter descrito
# pelo provedor. A lista é referência para configuração; a API não a expõe.
GEMINI_VOICES: dict[str, str] = {
    "Zephyr": "brilhante", "Puck": "animada", "Charon": "informativa",
    "Kore": "firme", "Fenrir": "empolgada", "Leda": "jovem",
    "Orus": "firme", "Aoede": "leve", "Callirrhoe": "tranquila",
    "Autonoe": "brilhante", "Enceladus": "sussurrada", "Iapetus": "clara",
    "Umbriel": "tranquila", "Algieba": "suave", "Despina": "suave",
    "Erinome": "clara", "Algenib": "rouca", "Rasalgethi": "informativa",
    "Laomedeia": "animada", "Achernar": "macia", "Alnilam": "firme",
    "Schedar": "uniforme", "Gacrux": "madura", "Pulcherrima": "expressiva",
    "Achird": "amigável", "Zubenelgenubi": "casual", "Vindemiatrix": "gentil",
    "Sadachbia": "vivaz", "Sadaltager": "erudita", "Sulafat": "calorosa",
}


class OpenRouterError(RuntimeError):
    """Falha controlada da integração, classificada para retry seguro."""

    def __init__(self, message: str, *, retryable: bool = False,
                 status_code: int | None = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


@dataclass(frozen=True)
class ChatResult:
    data: Any  # JSON decodificado da resposta do modelo
    cost_usd: float
    prompt_tokens: int
    completion_tokens: int


def _request(settings: Settings, method: str, endpoint: str,
             payload: dict[str, Any] | None = None) -> requests.Response:
    headers = {"Authorization": f"Bearer {settings.require_api_key()}", **_HEADERS_EXTRA}
    last_error: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = requests.request(
                method, f"{OPENROUTER_BASE_URL}{endpoint}", json=payload,
                headers=headers, timeout=_TIMEOUT,
            )
            if response.status_code in (408, 425, 429, 500, 502, 503, 504):
                raise OpenRouterError(
                    f"HTTP {response.status_code} (transitório)",
                    retryable=True, status_code=response.status_code,
                )
            if response.status_code != 200:
                # Não logar o corpo integral: pode ecoar conteúdo ou detalhes do provedor.
                provider_rejected = (
                    endpoint == "/audio/speech"
                    and response.status_code == 400
                    and "Provider returned 400" in response.text
                )
                raise OpenRouterError(
                    f"HTTP {response.status_code} em {endpoint}: {response.text[:300]}",
                    retryable=provider_rejected, status_code=response.status_code,
                )
            return response
        except requests.RequestException as error:
            last_error = error
            # No TTS, o pipeline controla a tentativa por fala e a expõe no status.
            if endpoint == "/audio/speech":
                raise OpenRouterError(
                    f"Falha de rede em {endpoint}: {error}", retryable=True
                ) from error
        except OpenRouterError as error:
            last_error = error
            if not error.retryable or endpoint == "/audio/speech":
                raise
        if attempt < _MAX_RETRIES:
            time.sleep(2**attempt)
    raise OpenRouterError(
        f"Falha após {_MAX_RETRIES} tentativas em {endpoint}: {last_error}",
        retryable=True,
        status_code=getattr(last_error, "status_code", None),
    )


def _extract_json(text: str) -> Any:
    """Aceita JSON puro ou cercado por ```json ... ```."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=0)
    return json.loads(text[start:])


def chat_json(settings: Settings, model: str, system: str, user: str) -> ChatResult:
    """Chat que exige resposta JSON; retorna o dado decodificado e o custo exato."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.4,
        "usage": {"include": True},
    }
    body = _request(settings, "POST", "/chat/completions", payload).json()
    content = body["choices"][0]["message"]["content"]
    usage = body.get("usage", {})
    try:
        data = _extract_json(content)
    except (json.JSONDecodeError, ValueError) as error:
        raise OpenRouterError(f"Modelo {model} não retornou JSON válido: {error}") from error
    return ChatResult(
        data=data,
        cost_usd=float(usage.get("cost", 0.0) or 0.0),
        prompt_tokens=int(usage.get("prompt_tokens", 0) or 0),
        completion_tokens=int(usage.get("completion_tokens", 0) or 0),
    )


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
    response = _request(settings, "POST", "/audio/speech", payload)
    content_type = response.headers.get("Content-Type", "")
    if "json" in content_type:
        raise OpenRouterError(
            f"TTS retornou JSON em vez de áudio: {response.text[:300]}", retryable=True
        )
    if len(response.content) < 512:
        raise OpenRouterError("TTS retornou resposta vazia ou curta demais.", retryable=True)
    return response.content


def account_usage_usd(settings: Settings) -> float:
    """Uso acumulado da conta em US$ (endpoint /credits)."""
    body = _request(settings, "GET", "/credits").json()
    return float(body.get("data", {}).get("total_usage", 0.0) or 0.0)


@dataclass(frozen=True)
class AccountBalance:
    total_credits: float
    total_usage: float

    @property
    def remaining(self) -> float:
        return self.total_credits - self.total_usage


def account_balance(settings: Settings) -> AccountBalance:
    """Créditos comprados, uso acumulado e saldo restante da chave ativa."""
    data = _request(settings, "GET", "/credits").json().get("data", {})
    return AccountBalance(
        total_credits=float(data.get("total_credits", 0.0) or 0.0),
        total_usage=float(data.get("total_usage", 0.0) or 0.0),
    )


def check_api_key(settings: Settings) -> tuple[bool, str]:
    """Valida a chave contra a API; retorna (ok, motivo/resumo)."""
    try:
        balance = account_balance(settings)
        return True, (f"chave válida — saldo US$ {balance.remaining:.2f} "
                      f"(uso acumulado US$ {balance.total_usage:.2f})")
    except (OpenRouterError, RuntimeError) as error:
        return False, str(error)


def list_tts_models(settings: Settings) -> list[dict[str, str]]:
    """Modelos com saída de áudio disponíveis no catálogo do OpenRouter."""
    # O catálogo distingue modelos que sintetizam fala (``speech``) de modelos
    # multimodais/musicais que apenas declaram saída ``audio``.
    body = _request(settings, "GET", "/models?output_modalities=speech").json()
    models = []
    for model in body.get("data", []):
        pricing = model.get("pricing", {})
        models.append({
            "id": model.get("id", ""),
            "name": model.get("name", ""),
            "prompt_price": pricing.get("prompt", ""),
            "completion_price": pricing.get("completion", ""),
        })
    return sorted(models, key=lambda m: m["id"])
