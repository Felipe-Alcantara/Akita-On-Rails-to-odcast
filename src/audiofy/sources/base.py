"""Contrato de uma fonte de conteúdo.

O pipeline não conhece nenhuma fonte específica: ele opera sobre `ContentItem`.
Adicionar uma fonte nova (outro blog, feed, pasta de arquivos, Notion…) é
implementar `ContentSource` e registrá-la em `sources/__init__.py` — o núcleo
permanece fechado para modificação (Open/Closed).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ContentItem:
    """Unidade de conteúdo pronta para virar episódio."""

    item_id: str  # estável dentro da fonte (vira o nome da pasta do episódio)
    title: str
    url: str
    published_at: str
    text: str  # corpo em Markdown/texto, sem metadados
    words: int
    attribution: str  # frase de atribuição/licença exigida na publicação


@dataclass(frozen=True)
class ItemSummary:
    item_id: str
    title: str
    published_at: str


class ContentSource(ABC):
    key: str = ""
    name: str = ""
    description: str = ""

    @abstractmethod
    def sync(self) -> str:
        """Baixa/atualiza a fonte. Retorna um identificador de versão."""

    @abstractmethod
    def list_items(self) -> list[ItemSummary]:
        """Itens disponíveis, mais recentes primeiro."""

    @abstractmethod
    def search(self, query: str) -> list[ItemSummary]:
        """Busca itens; a semântica fica a cargo da fonte."""

    @abstractmethod
    def get_item(self, item_id: str) -> ContentItem:
        """Carrega o item completo; LookupError se não existir."""

    @abstractmethod
    def is_ready(self) -> bool:
        """True se a fonte está sincronizada e pronta para listar."""
