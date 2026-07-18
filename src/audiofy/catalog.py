"""Catálogo de modelos do OpenRouter com cache local e escolha empresa → modelo.

Portado do padrão do Openia: a lista vem da API ao vivo, é cacheada em
`.audiofy/models-cache.json` por 24h e é navegada em dois passos —
primeiro a empresa (prefixo do id), depois o modelo com preço por linha.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass

from .config import STATE_DIR, Settings

_CACHE_PATH = STATE_DIR / "models-cache.json"
_CACHE_TTL_SECONDS = 24 * 3600


@dataclass(frozen=True)
class Model:
    id: str
    name: str
    prompt_price: float  # US$ por milhão de tokens de entrada
    completion_price: float  # US$ por milhão de tokens de saída
    output_modalities: tuple[str, ...] = ("text",)

    @property
    def vendor(self) -> str:
        return self.id.split("/", 1)[0]

    @property
    def price_line(self) -> str:
        return f"US$ {self.prompt_price:.2f}/M entrada · US$ {self.completion_price:.2f}/M saída"


def _parse(payload: dict) -> list[Model]:
    models = []
    for item in payload.get("data", []):
        pricing = item.get("pricing", {})
        models.append(
            Model(
                id=item.get("id", ""),
                name=item.get("name", ""),
                prompt_price=float(pricing.get("prompt", 0) or 0) * 1_000_000,
                completion_price=float(pricing.get("completion", 0) or 0) * 1_000_000,
                output_modalities=tuple(
                    item.get("architecture", {}).get("output_modalities", ["text"])
                ),
            )
        )
    return sorted(models, key=lambda m: m.id)


def load_models(settings: Settings, force_refresh: bool = False) -> list[Model]:
    """Modelos do catálogo, do cache quando fresco, da API quando não."""
    if not force_refresh and _CACHE_PATH.is_file():
        cached = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        if time.time() - cached.get("fetched_at", 0) < _CACHE_TTL_SECONDS:
            return [
                Model(**{**m, "output_modalities": tuple(m["output_modalities"])})
                for m in cached["models"]
            ]
    from .providers.openrouter import _request

    payload = _request(settings, "GET", "/models").json()
    models = _parse(payload)
    _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CACHE_PATH.write_text(
        json.dumps(
            {"fetched_at": time.time(), "models": [asdict(m) for m in models]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return models


def vendors(models: list[Model]) -> list[str]:
    return sorted({m.vendor for m in models})


def models_of(
    models: list[Model], vendor: str, modality: str | tuple[str, ...] | None = None
) -> list[Model]:
    hits = [m for m in models if m.vendor == vendor]
    if modality:
        modalities = (modality,) if isinstance(modality, str) else modality
        hits = [m for m in hits if set(modalities) & set(m.output_modalities)]
    return hits
