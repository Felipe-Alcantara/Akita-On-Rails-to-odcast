"""Sincronização e listagem de artigos do repositório oficial do blog.

O repositório é um site Hugo com artigos em:
    content/AAAA/MM/DD/slug-do-artigo/index.md
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import SOURCE_REPO_DIR, SOURCE_REPO_URL


@dataclass
class ArticleRef:
    article_id: str  # "AAAA-MM-DD/slug"
    path: Path
    title: str
    date: str
    draft: bool

    @property
    def canonical_url(self) -> str:
        year, month, day = self.date.split("-")
        slug = self.article_id.split("/", 1)[1]
        return f"https://akitaonrails.com/{year}/{month}/{day}/{slug}/"


def sync_repo() -> str:
    """Clona ou atualiza o repositório oficial. Retorna o commit atual."""
    if (SOURCE_REPO_DIR / ".git").is_dir():
        subprocess.run(
            ["git", "-C", str(SOURCE_REPO_DIR), "pull", "--ff-only"],
            check=True, capture_output=True, text=True,
        )
    else:
        SOURCE_REPO_DIR.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "clone", "--depth", "1", SOURCE_REPO_URL, str(SOURCE_REPO_DIR)],
            check=True, text=True,
        )
    result = subprocess.run(
        ["git", "-C", str(SOURCE_REPO_DIR), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(markdown: str) -> dict[str, str]:
    """Extrai chaves simples (title, date, draft) do frontmatter YAML.

    Parser mínimo proposital: cobre o formato usado pelo blog sem depender de PyYAML.
    Chaves com estruturas aninhadas são ignoradas.
    """
    match = _FRONTMATTER_RE.match(markdown)
    if not match:
        return {}
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line or line.startswith((" ", "\t", "-", "#")) or ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip().lower()] = value.strip().strip("'\"")
    return meta


def strip_frontmatter(markdown: str) -> str:
    return _FRONTMATTER_RE.sub("", markdown, count=1)


def list_articles(include_drafts: bool = False) -> list[ArticleRef]:
    """Lista os artigos em português, mais recentes primeiro."""
    content_dir = SOURCE_REPO_DIR / "content"
    if not content_dir.is_dir():
        raise RuntimeError(
            "Repositório do blog ainda não sincronizado. Use a opção de sincronizar primeiro."
        )
    articles: list[ArticleRef] = []
    for index_md in content_dir.glob("[0-9]*/[0-9]*/[0-9]*/*/index.md"):
        rel = index_md.relative_to(content_dir)
        year, month, day, slug = rel.parts[:4]
        meta = parse_frontmatter(index_md.read_text(encoding="utf-8", errors="replace"))
        draft = meta.get("draft", "false").lower() == "true"
        if draft and not include_drafts:
            continue
        articles.append(
            ArticleRef(
                article_id=f"{year}-{month}-{day}/{slug}",
                path=index_md,
                title=meta.get("title", slug),
                date=f"{year}-{month}-{day}",
                draft=draft,
            )
        )
    articles.sort(key=lambda a: a.article_id, reverse=True)
    return articles
