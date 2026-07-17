"""Fonte de conteúdo: artigos do AkitaOnRails, via módulo akita-articles.

O módulo vive em https://github.com/Felipe-Alcantara/akita-articles.
Instalação: `pip install git+https://github.com/Felipe-Alcantara/akita-articles`
(o Setup do start_app.py faz isso). Para desenvolvimento local, um clone
irmão `../akita-articles` também é aceito.
"""

from __future__ import annotations

import sys
from pathlib import Path

from ..config import PROJECT_ROOT
from .base import ContentItem, ContentSource, ItemSummary

_SIBLING = PROJECT_ROOT.parent / "akita-articles" / "src"
if _SIBLING.is_dir() and str(_SIBLING) not in sys.path:
    sys.path.insert(0, str(_SIBLING))

try:
    import akita_articles as _akita
except ImportError as _error:  # pragma: no cover - depende do ambiente
    _akita = None
    _IMPORT_ERROR = _error


def _require_module():
    if _akita is None:
        raise RuntimeError(
            "Módulo akita-articles não instalado. Rode o Setup do menu ou: "
            "pip install git+https://github.com/Felipe-Alcantara/akita-articles"
        ) from _IMPORT_ERROR
    return _akita


class AkitaSource(ContentSource):
    key = "akita"
    name = "Akita on Rails"
    description = "Artigos do blog AkitaOnRails.com (CC BY-NC-SA 4.0)"

    def sync(self) -> str:
        return _require_module().sync()

    def is_ready(self) -> bool:
        if _akita is None:
            return False
        from akita_articles.config import default_repo_dir
        return (default_repo_dir() / "content").is_dir()

    def list_items(self) -> list[ItemSummary]:
        return [
            ItemSummary(ref.article_id, ref.title, ref.date)
            for ref in _require_module().list_articles()
        ]

    def search(self, query: str) -> list[ItemSummary]:
        return [
            ItemSummary(ref.article_id, ref.title, ref.date)
            for ref in _require_module().search(query)
        ]

    def get_item(self, item_id: str) -> ContentItem:
        article = _require_module().get_article(item_id)
        ref = article.ref
        return ContentItem(
            item_id=ref.article_id,
            title=ref.title,
            url=ref.canonical_url,
            published_at=ref.date,
            text=article.text,
            words=article.analysis.words,
            attribution=(
                f'Baseado no artigo "{ref.title}", de Fabio Akita, publicado em '
                f"AkitaOnRails.com ({ref.canonical_url}), sob CC BY-NC-SA 4.0. "
                f"Esta adaptação é distribuída sob CC BY-NC-SA 4.0."
            ),
        )
