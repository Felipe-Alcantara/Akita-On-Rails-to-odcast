"""Registro de fontes de conteúdo disponíveis (Open/Closed).

Para adicionar uma fonte: implemente `ContentSource` em um módulo novo e
acrescente uma instância em `_SOURCES`. Nada mais no núcleo muda.
"""

from __future__ import annotations

from .akita import AkitaSource
from .base import ContentSource
from .custom import CustomSource

_SOURCES: list[ContentSource] = [
    CustomSource(),
    AkitaSource(),
]


def available_sources() -> list[ContentSource]:
    return list(_SOURCES)


def get_source(key: str) -> ContentSource:
    for source in _SOURCES:
        if source.key == key:
            return source
    raise LookupError(
        f"Fonte '{key}' não registrada. Disponíveis: {', '.join(s.key for s in _SOURCES)}"
    )
