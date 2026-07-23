"""Adaptador OpenRouter: chat JSON com custo por chamada, TTS, catálogo e uso da conta.

Custo em tempo real:
- chat: a resposta traz `usage.cost` exato em US$;
- TTS: o cabeçalho `X-Generation-Id` liga o áudio binário ao custo individual consultado
  em `/generation`, sem misturar consumo de outras chaves da conta.
"""

from __future__ import annotations

import json
import math
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
    "Zephyr": "brilhante",
    "Puck": "animada",
    "Charon": "informativa",
    "Kore": "firme",
    "Fenrir": "empolgada",
    "Leda": "jovem",
    "Orus": "firme",
    "Aoede": "leve",
    "Callirrhoe": "tranquila",
    "Autonoe": "brilhante",
    "Enceladus": "sussurrada",
    "Iapetus": "clara",
    "Umbriel": "tranquila",
    "Algieba": "suave",
    "Despina": "suave",
    "Erinome": "clara",
    "Algenib": "rouca",
    "Rasalgethi": "informativa",
    "Laomedeia": "animada",
    "Achernar": "macia",
    "Alnilam": "firme",
    "Schedar": "uniforme",
    "Gacrux": "madura",
    "Pulcherrima": "expressiva",
    "Achird": "amigável",
    "Zubenelgenubi": "casual",
    "Vindemiatrix": "gentil",
    "Sadachbia": "vivaz",
    "Sadaltager": "erudita",
    "Sulafat": "calorosa",
}

# Vozes do Kokoro 82M (modelo leve e ultra-econômico).
# Subconjunto curado: PT-BR completo + EN americano; o modelo tem 54 vozes
# no total, mas o catálogo aqui inclui as mais úteis para o projeto.
KOKORO_VOICES: dict[str, str] = {
    # PT-BR
    "pf_dora": "feminina (pt-BR)",
    "pm_alex": "masculina (pt-BR)",
    "pm_santa": "masculina festiva (pt-BR)",
    # EN — americano (femininas)
    "af_heart": "brilhante (en)",
    "af_alloy": "neutra (en)",
    "af_aoede": "leve (en)",
    "af_bella": "suave (en)",
    "af_jessica": "clara (en)",
    "af_kore": "firme (en)",
    "af_nicole": "macia (en)",
    "af_nova": "animada (en)",
    "af_river": "tranquila (en)",
    "af_sarah": "calorosa (en)",
    "af_sky": "jovem (en)",
    # EN — americano (masculinas)
    "am_adam": "firme (en)",
    "am_echo": "ressonante (en)",
    "am_eric": "clara (en)",
    "am_fenrir": "empolgada (en)",
    "am_liam": "madura (en)",
    "am_michael": "neutra (en)",
    "am_onyx": "profunda (en)",
    "am_puck": "animada (en)",
    # EN — britânico
    "bf_emma": "suave (en-GB)",
    "bm_daniel": "clara (en-GB)",
    "bm_george": "madura (en-GB)",
}


class OpenRouterError(RuntimeError):
    """Falha controlada da integração, classificada para retry seguro."""

    def __init__(
        self, message: str, *, retryable: bool = False, status_code: int | None = None
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code


@dataclass(frozen=True)
class ChatResult:
    data: Any  # JSON decodificado da resposta do modelo
    cost_usd: float
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True)
class SpeechResult:
    audio: bytes
    generation_id: str | None


def _request(
    settings: Settings, method: str, endpoint: str, payload: dict[str, Any] | None = None
) -> requests.Response:
    headers = {"Authorization": f"Bearer {settings.require_api_key()}", **_HEADERS_EXTRA}
    last_error: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = requests.request(
                method,
                f"{OPENROUTER_BASE_URL}{endpoint}",
                json=payload,
                headers=headers,
                timeout=_TIMEOUT,
            )
            if response.status_code in (408, 425, 429, 500, 502, 503, 504):
                raise OpenRouterError(
                    f"HTTP {response.status_code} (transitório)",
                    retryable=True,
                    status_code=response.status_code,
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
                    retryable=provider_rejected,
                    status_code=response.status_code,
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


def text_to_speech(
    settings: Settings, text: str, voice: str, instructions: str = ""
) -> SpeechResult:
    """Sintetiza uma fala e preserva o ID necessário para auditar seu custo."""
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
    return SpeechResult(
        audio=response.content,
        generation_id=response.headers.get("X-Generation-Id") or None,
    )


def generation_cost_usd(settings: Settings, generation_id: str) -> float:
    """Retorna o custo faturado de uma geração individual."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", generation_id or ""):
        raise ValueError("generation_id inválido")
    endpoint = f"/generation?id={generation_id}"
    last_error: OpenRouterError | None = None
    # O registro pode aparecer alguns instantes depois do stream binário do TTS.
    for attempt in range(4):
        try:
            body = _request(settings, "GET", endpoint).json()
            data = body.get("data") or {}
            if not isinstance(data, dict):
                raise OpenRouterError("A geração retornou metadados inválidos.")
            value = data.get("total_cost", data.get("usage"))
            if value is None:
                raise OpenRouterError("A geração não informou custo.")
            cost = float(value)
            if not math.isfinite(cost) or cost < 0:
                raise OpenRouterError("A geração informou custo inválido.")
            return cost
        except OpenRouterError as error:
            last_error = error
            if error.status_code != 404 or attempt == 3:
                raise
            time.sleep(0.5 * (attempt + 1))
    raise last_error or OpenRouterError("Custo da geração indisponível.")


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
    """Créditos comprados, uso acumulado e saldo restante da conta."""
    data = _request(settings, "GET", "/credits").json().get("data", {})
    return AccountBalance(
        total_credits=float(data.get("total_credits", 0.0) or 0.0),
        total_usage=float(data.get("total_usage", 0.0) or 0.0),
    )


@dataclass(frozen=True)
class KeyLimit:
    """Uso e limite próprios da chave que autenticou a requisição."""

    label: str
    usage: float
    usage_monthly: float
    limit: float | None
    remaining: float | None
    reset: str | None


def current_key_limit(settings: Settings) -> KeyLimit:
    """Consulta o limite da chave ativa, que é independente do saldo da conta."""
    data = _request(settings, "GET", "/key").json().get("data", {})

    def optional_float(name: str) -> float | None:
        value = data.get(name)
        return None if value is None else float(value)

    return KeyLimit(
        label=str(data.get("label", "") or ""),
        usage=float(data.get("usage", 0.0) or 0.0),
        usage_monthly=float(data.get("usage_monthly", 0.0) or 0.0),
        limit=optional_float("limit"),
        remaining=optional_float("limit_remaining"),
        reset=data.get("limit_reset"),
    )


def check_api_key(settings: Settings) -> tuple[bool, str]:
    """Valida a chave contra a API; retorna (ok, motivo/resumo)."""
    try:
        key = current_key_limit(settings)
        label = f" {key.label}" if key.label else ""
        if key.limit is None:
            detail = "sem limite próprio"
        elif key.remaining is None:
            detail = f"limite US$ {key.limit:.2f}"
        else:
            detail = f"limite US$ {key.limit:.2f}, restante US$ {key.remaining:.2f}"
        reset = f", renovação {key.reset}" if key.reset else ""
        available = key.remaining is None or key.remaining > 0
        availability = "válida" if available else "válida, mas com limite esgotado"
        return available, (
            f"chave{label} {availability} — {detail} "
            f"(uso mensal US$ {key.usage_monthly:.2f}{reset})"
        )
    except (OpenRouterError, RuntimeError) as error:
        return False, str(error)


def check_api_key_value(api_key: str) -> tuple[bool, str]:
    """Verifica uma chave específica sem alterar a seleção persistida nem expor seu valor."""
    if not api_key:
        return False, "nenhuma chave disponível nessa origem"
    return check_api_key(Settings(api_key=api_key))


def list_tts_models(settings: Settings) -> list[dict[str, Any]]:
    """Modelos com saída de áudio disponíveis no catálogo do OpenRouter."""
    # O catálogo distingue modelos que sintetizam fala (``speech``) de modelos
    # multimodais/musicais que apenas declaram saída ``audio``.
    body = _request(settings, "GET", "/models?output_modalities=speech").json()
    models = []
    for model in body.get("data", []):
        pricing = model.get("pricing", {})
        models.append(
            {
                "id": model.get("id", ""),
                "name": model.get("name", ""),
                "prompt_price": pricing.get("prompt", ""),
                "completion_price": pricing.get("completion", ""),
                "supported_voices": model.get("supported_voices") or [],
            }
        )
    return sorted(models, key=lambda m: m["id"])
