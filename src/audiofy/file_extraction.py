"""Extração de texto de arquivos locais por código, sem custo de IA.

Ordem de prioridade deliberada: bibliotecas Python puras primeiro (pypdf,
python-docx, ebooklib), OCR local (Tesseract) para imagens e PDFs escaneados,
e somente quando nada disso funciona o chamador decide se aciona um modelo
de IA — arquivos grandes (livros, centenas de páginas) tornariam a via de IA
lenta e cara, então ela nunca é automática.
"""

from __future__ import annotations

import html
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

MAX_FILE_BYTES = 200 * 1024 * 1024
_TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".text"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
SUPPORTED_SUFFIXES = {".pdf", ".docx", ".epub"} | _TEXT_SUFFIXES | _IMAGE_SUFFIXES

# Menos que isso por página indica PDF escaneado (só imagens, sem camada de texto).
_MIN_CHARS_PER_PAGE = 20
_MIN_TOTAL_CHARS = 120


@dataclass(frozen=True)
class ExtractionResult:
    """Resultado da extração: texto pronto ou o motivo de precisar de outra via."""

    title: str
    text: str
    method: str  # "pypdf" | "python-docx" | "ebooklib" | "plain-text" | "tesseract-ocr"
    # Quando needs_fallback=True, text está vazio e reason explica o que faltou.
    needs_fallback: bool = False
    reason: str = ""


def ocr_available() -> bool:
    """OCR local exige o binário Tesseract e a ponte pytesseract."""
    if not shutil.which("tesseract"):
        return False
    try:
        import pytesseract  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return False
    return True


def _ocr_languages() -> str:
    """Usa português quando o traineddata existe; caso contrário o padrão do Tesseract."""
    import pytesseract

    try:
        available = set(pytesseract.get_languages(config=""))
    except Exception:
        return "eng"
    wanted = [lang for lang in ("por", "eng") if lang in available]
    return "+".join(wanted) if wanted else "eng"


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _title_from_path(path: Path) -> str:
    return re.sub(r"[-_]+", " ", path.stem).strip() or path.stem


def extract_file(path: Path) -> ExtractionResult:
    """Extrai texto do arquivo pela melhor via local disponível."""
    if not path.is_file():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")
    size = path.stat().st_size
    if size == 0:
        raise ValueError("O arquivo está vazio.")
    if size > MAX_FILE_BYTES:
        raise ValueError("O arquivo excede o limite de 200 MiB.")
    suffix = path.suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        return _extract_plain_text(path)
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix == ".docx":
        return _extract_docx(path)
    if suffix == ".epub":
        return _extract_epub(path)
    if suffix in _IMAGE_SUFFIXES:
        return _extract_image(path)
    raise ValueError(
        f"Formato '{suffix}' não suportado. Aceitos: PDF, DOCX, EPUB, TXT/MD e imagens."
    )


def _extract_plain_text(path: Path) -> ExtractionResult:
    raw = path.read_bytes()
    # UTF-16 só entra na disputa com BOM: sem ele, qualquer texto de bytes pares
    # "decodifica" em ideogramas silenciosamente e venceria o latin-1 legítimo.
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        candidates = ("utf-16", "utf-8", "latin-1")
    else:
        candidates = ("utf-8", "latin-1")
    for encoding in candidates:
        try:
            text = raw.decode(encoding)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:  # latin-1 nunca falha; inalcançável, mas defensivo.
        text = raw.decode("utf-8", errors="replace")
    text = _normalize(text)
    if not text:
        raise ValueError("O arquivo de texto está vazio.")
    return ExtractionResult(_title_from_path(path), text, "plain-text")


_PAGE_NUMBER_RE = re.compile(r"\d+")
# Rodapé de diagramação é uma linha curta; frases de texto corrido são mais
# longas. O teto mantém fora da detecção uma abertura padronizada de capítulo,
# que se repetiria entre páginas mas é conteúdo que o ouvinte quer escutar.
_MAX_RUNNING_LINE_CHARS = 90
# Linha terminada em ponto final é frase, não marca de página.
_SENTENCE_END_RE = re.compile(r"[.!?][\"'”’)\]]*$")


def _repeated_line_signature(line: str) -> str:
    """Assinatura da linha ignorando números, para casar rodapés que só mudam a página.

    Retorna vazio quando a linha não tem cara de cabeçalho/rodapé, o que a mantém
    fora da detecção por repetição.
    """
    collapsed = " ".join(line.split())
    if (
        not collapsed
        or len(collapsed) > _MAX_RUNNING_LINE_CHARS
        or _SENTENCE_END_RE.search(collapsed)
    ):
        return ""
    return _PAGE_NUMBER_RE.sub("#", collapsed)


def _strip_running_headers(pages: list[str]) -> list[str]:
    """Remove cabeçalhos e rodapés que se repetem ao longo do documento.

    Diagramadores repetem título, nome do arquivo e numeração em toda página.
    Esse texto não é conteúdo: lido em voz alta vira ruído e, quando um trecho
    fica só com ele, o TTS chega a não devolver áudio nenhum. A detecção é por
    repetição — as bordas de cada página que aparecem em muitas páginas saem.
    """
    if len(pages) < 4:
        return pages

    def edge_positions(total: int) -> set[int]:
        """Bordas da página: até 2 linhas de cada ponta, nunca a página toda.

        Se as duas bordas se encostassem, o miolo — que é conteúdo — entraria na
        conta e poderia ser removido junto com o cabeçalho.
        """
        if total <= 1:
            return {0} if total == 1 else set()
        margin = 1 if total < 6 else 2
        return set(range(margin)) | set(range(total - margin, total))

    edge_counts: dict[str, int] = {}
    for page in pages:
        lines = [line for line in page.splitlines() if line.strip()]
        for position in edge_positions(len(lines)):
            signature = _repeated_line_signature(lines[position])
            if signature:
                edge_counts[signature] = edge_counts.get(signature, 0) + 1
    threshold = max(3, len(pages) // 3)
    running = {signature for signature, count in edge_counts.items() if count >= threshold}
    if not running:
        return pages
    cleaned: list[str] = []
    for page in pages:
        lines = page.splitlines()
        borders = edge_positions(len(lines))
        keep = [
            line
            for position, line in enumerate(lines)
            if not (position in borders and _repeated_line_signature(line) in running)
        ]
        cleaned.append("\n".join(keep))
    return cleaned


def _extract_pdf(path: Path) -> ExtractionResult:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise RuntimeError(
            "A biblioteca pypdf não está instalada; rode Instalar/corrigir em Configurações."
        ) from error
    try:
        reader = PdfReader(path)
    except Exception as error:
        raise ValueError(f"Não consegui abrir o PDF: {error}") from error
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as error:
            raise ValueError("O PDF é protegido por senha.") from error
    pages = [page.extract_text() or "" for page in reader.pages]
    text = _normalize("\n\n".join(_strip_running_headers(pages)))
    title = ""
    if reader.metadata and reader.metadata.title:
        title = str(reader.metadata.title).strip()
    title = title or _title_from_path(path)
    # Camada de texto ausente/ínfima = PDF escaneado; texto "extraído" seria lixo.
    if len(text) < max(_MIN_TOTAL_CHARS, _MIN_CHARS_PER_PAGE * len(pages)):
        if ocr_available():
            return _ocr_pdf(path, title, reader)
        return ExtractionResult(
            title,
            "",
            "pypdf",
            needs_fallback=True,
            reason=(
                "O PDF parece ser escaneado (sem camada de texto) e o OCR local "
                "(Tesseract) não está instalado."
            ),
        )
    return ExtractionResult(title, text, "pypdf")


def _ocr_pdf(path: Path, title: str, reader) -> ExtractionResult:
    """OCR página a página de um PDF escaneado usando as imagens embutidas."""
    import io

    import pytesseract
    from PIL import Image

    languages = _ocr_languages()
    texts: list[str] = []
    for page in reader.pages:
        for image_file in page.images:
            try:
                with Image.open(io.BytesIO(image_file.data)) as image:
                    texts.append(pytesseract.image_to_string(image, lang=languages))
            except Exception:  # página sem imagem legível não derruba o restante
                continue
    text = _normalize("\n\n".join(texts))
    if len(text) < _MIN_TOTAL_CHARS:
        return ExtractionResult(
            title,
            "",
            "tesseract-ocr",
            needs_fallback=True,
            reason="O OCR local não reconheceu texto suficiente nas páginas do PDF.",
        )
    return ExtractionResult(title, text, "tesseract-ocr")


def _extract_docx(path: Path) -> ExtractionResult:
    try:
        from docx import Document
    except ImportError as error:
        raise RuntimeError(
            "A biblioteca python-docx não está instalada; rode Instalar/corrigir em Configurações."
        ) from error
    try:
        document = Document(str(path))
    except Exception as error:
        raise ValueError(f"Não consegui abrir o DOCX: {error}") from error
    parts = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" — ".join(cells))
    text = _normalize("\n\n".join(part for part in parts if part.strip()))
    if len(text) < _MIN_TOTAL_CHARS:
        return ExtractionResult(
            _title_from_path(path),
            "",
            "python-docx",
            needs_fallback=True,
            reason="O DOCX não contém texto extraível (pode ser só imagens).",
        )
    title = (document.core_properties.title or "").strip() or _title_from_path(path)
    return ExtractionResult(title, text, "python-docx")


_EPUB_TAG_RE = re.compile(r"<[^>]+>")
_EPUB_BLOCK_RE = re.compile(
    r"</(?:p|div|h[1-6]|li|blockquote|section|article)>|<br\s*/?>", re.IGNORECASE
)


def _epub_html_to_text(markup: str) -> str:
    markup = re.sub(
        r"<(?:script|style)[^>]*>.*?</(?:script|style)>",
        "",
        markup,
        flags=re.DOTALL | re.IGNORECASE,
    )
    markup = _EPUB_BLOCK_RE.sub("\n\n", markup)
    return html.unescape(_EPUB_TAG_RE.sub("", markup))


def _extract_epub(path: Path) -> ExtractionResult:
    try:
        from ebooklib import ITEM_DOCUMENT, epub
    except ImportError as error:
        raise RuntimeError(
            "A biblioteca ebooklib não está instalada; rode Instalar/corrigir em Configurações."
        ) from error
    try:
        book = epub.read_epub(str(path), options={"ignore_ncx": True})
    except Exception as error:
        raise ValueError(f"Não consegui abrir o EPUB: {error}") from error
    chapters = [
        _epub_html_to_text(item.get_content().decode("utf-8", errors="replace"))
        for item in book.get_items_of_type(ITEM_DOCUMENT)
    ]
    text = _normalize("\n\n".join(chapters))
    if len(text) < _MIN_TOTAL_CHARS:
        return ExtractionResult(
            _title_from_path(path),
            "",
            "ebooklib",
            needs_fallback=True,
            reason="O EPUB não contém texto extraível.",
        )
    title = (book.get_metadata("DC", "title") or [("", {})])[0][0] or _title_from_path(path)
    return ExtractionResult(str(title).strip() or _title_from_path(path), text, "ebooklib")


def _extract_image(path: Path) -> ExtractionResult:
    title = _title_from_path(path)
    if not ocr_available():
        return ExtractionResult(
            title,
            "",
            "tesseract-ocr",
            needs_fallback=True,
            reason=(
                "Ler texto de imagem exige o OCR local (Tesseract), que não está "
                "instalado. Veja Diagnóstico/Setup em Configurações."
            ),
        )
    import pytesseract
    from PIL import Image

    try:
        with Image.open(path) as image:
            text = _normalize(pytesseract.image_to_string(image, lang=_ocr_languages()))
    except Exception as error:
        raise ValueError(f"Não consegui processar a imagem: {error}") from error
    if len(text) < _MIN_TOTAL_CHARS:
        return ExtractionResult(
            title,
            "",
            "tesseract-ocr",
            needs_fallback=True,
            reason="O OCR local não reconheceu texto suficiente na imagem.",
        )
    return ExtractionResult(title, text, "tesseract-ocr")
