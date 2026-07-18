"""Fonte genérica de conteúdo: qualquer URL ou texto colado.

Os itens vivem como Markdown com frontmatter em `data/inbox/`. É a fonte que
torna o Audiofy independente de qualquer blog específico: cole um texto, ou
aponte uma URL e o extrator puxa o texto principal da página (heurística
leve, sem dependências — para páginas complexas, cole o texto direto).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

from ..config import DATA_DIR
from ..security import validate_identifier, validate_public_url
from .base import ContentItem, ContentSource, ItemSummary

_INBOX_DIR = DATA_DIR / "inbox"
_SKIP_TAGS = {
    "script",
    "style",
    "nav",
    "header",
    "footer",
    "aside",
    "noscript",
    "form",
    "svg",
    "iframe",
}
_BLOCK_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre"}
_MAX_CONTENT_BYTES = 5 * 1024 * 1024
_MAX_REDIRECTS = 5


def slugify(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.lower())
    ascii_text = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-") or "conteudo"


class _MainTextParser(HTMLParser):
    """Extrai título e blocos de texto, priorizando <article>/<main>."""

    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self._in_title = False
        self._skip_depth = 0
        self._container_depth = 0
        self._block: list[str] = []
        self.blocks: list[tuple[bool, str]] = []  # (dentro de article/main, texto)

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in ("article", "main"):
            self._container_depth += 1

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in ("article", "main"):
            self._container_depth = max(0, self._container_depth - 1)
        elif tag in _BLOCK_TAGS:
            text = " ".join("".join(self._block).split())
            self._block = []
            if text:
                self.blocks.append((self._container_depth > 0, text))

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._skip_depth == 0:
            self._block.append(data)


def extract_main_text(html: str) -> tuple[str, str]:
    """Retorna (título, texto principal) de um HTML."""
    parser = _MainTextParser()
    parser.feed(html)
    inside = [text for in_main, text in parser.blocks if in_main]
    chosen = inside if inside else [text for _, text in parser.blocks if len(text) > 60]
    return parser.title.strip(), "\n\n".join(chosen)


class CustomSource(ContentSource):
    key = "custom"
    name = "Conteúdo próprio"
    description = "Qualquer URL ou texto colado (data/inbox/)"

    def __init__(self, inbox_dir: Path | None = None) -> None:
        self.inbox_dir = inbox_dir or _INBOX_DIR

    # ── Escrita ──────────────────────────────────────────────────────────

    def add_text(self, title: str, text: str, url: str = "") -> str:
        """Guarda um conteúdo colado e retorna o item_id."""
        title = " ".join(str(title).split())
        url = " ".join(str(url).split())
        if not title or len(title) > 300:
            raise ValueError("O título é obrigatório e pode ter no máximo 300 caracteres.")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("O conteúdo não pode ser vazio.")
        if len(text.encode("utf-8")) > _MAX_CONTENT_BYTES:
            raise ValueError("O conteúdo excede o limite de 5 MiB.")
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        base = f"{today}-{slugify(title)}"
        item_id, counter = base, 2
        while (self.inbox_dir / f"{item_id}.md").exists():
            item_id, counter = f"{base}-{counter}", counter + 1
        (self.inbox_dir / f"{item_id}.md").write_text(
            f"---\ntitle: {title}\nurl: {url}\ndate: {today}\n---\n\n{text}\n",
            encoding="utf-8",
        )
        return item_id

    def add_url(self, url: str) -> str:
        """Baixa uma página, extrai o texto principal e guarda como item."""
        import requests

        current = validate_public_url(url)
        headers = {"User-Agent": "Mozilla/5.0 (Audiofy Content AI)"}
        for redirect_count in range(_MAX_REDIRECTS + 1):
            response = requests.get(
                current,
                timeout=60,
                headers=headers,
                allow_redirects=False,
                stream=True,
            )
            response.raise_for_status()
            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get("location")
                response.close()
                if not location:
                    raise ValueError("A página redirecionou sem informar o destino.")
                if redirect_count == _MAX_REDIRECTS:
                    raise ValueError("A página excedeu o limite de redirecionamentos.")
                current = validate_public_url(urljoin(current, location))
                continue
            try:
                declared = int(response.headers.get("content-length", 0) or 0)
            except (TypeError, ValueError):
                declared = 0
            if declared > _MAX_CONTENT_BYTES:
                response.close()
                raise ValueError("A página excede o limite de 5 MiB.")
            body = bytearray()
            for chunk in response.iter_content(64 * 1024):
                body.extend(chunk)
                if len(body) > _MAX_CONTENT_BYTES:
                    response.close()
                    raise ValueError("A página excede o limite de 5 MiB.")
            encoding = response.encoding or "utf-8"
            response.close()
            try:
                html = body.decode(encoding, errors="replace")
            except LookupError:
                html = body.decode("utf-8", errors="replace")
            break
        title, text = extract_main_text(html)
        if len(text) < 200:
            raise ValueError(
                "Não consegui extrair texto suficiente dessa página; cole o conteúdo manualmente."
            )
        return self.add_text(title or current, text, url=current)

    # ── Contrato ContentSource ───────────────────────────────────────────

    def sync(self) -> str:
        return "local"

    def is_ready(self) -> bool:
        return True

    def _parse(self, path: Path) -> tuple[dict, str]:
        raw = path.read_text(encoding="utf-8", errors="replace")
        match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", raw, re.DOTALL)
        meta: dict[str, str] = {}
        if match:
            for line in match.group(1).splitlines():
                key, _, value = line.partition(":")
                meta[key.strip()] = value.strip()
            raw = raw[match.end() :]
        return meta, raw.strip()

    def list_items(self) -> list[ItemSummary]:
        if not self.inbox_dir.is_dir():
            return []
        items = []
        for path in self.inbox_dir.glob("*.md"):
            meta, _ = self._parse(path)
            items.append(
                ItemSummary(
                    item_id=path.stem,
                    title=meta.get("title", path.stem),
                    published_at=meta.get("date", ""),
                )
            )
        return sorted(items, key=lambda i: i.item_id, reverse=True)

    def search(self, query: str) -> list[ItemSummary]:
        terms = query.lower().split()
        return [
            item
            for item in self.list_items()
            if all(term in f"{item.item_id} {item.title}".lower() for term in terms)
        ]

    def get_item(self, item_id: str) -> ContentItem:
        item_id = validate_identifier(item_id, "ID do conteúdo")
        path = self.inbox_dir / f"{item_id}.md"
        if not path.is_file():
            raise LookupError(f"Conteúdo '{item_id}' não existe em {self.inbox_dir}.")
        meta, text = self._parse(path)
        url = meta.get("url", "")
        origin = f" Original: {url}." if url else ""
        return ContentItem(
            item_id=item_id,
            title=meta.get("title", item_id),
            url=url,
            published_at=meta.get("date", ""),
            text=text,
            words=len(text.split()),
            attribution=(
                f'Baseado no conteúdo "{meta.get("title", item_id)}".{origin} '
                f"Adaptação em áudio gerada com inteligência artificial. "
                f"Verifique os direitos do conteúdo original antes de publicar."
            ),
        )
