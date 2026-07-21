"""Exportação para o modo NotebookLM — o caminho barato.

O NotebookLM pessoal não tem API, mas gera Audio Overviews de ótima qualidade
dentro da assinatura Google (custo marginal zero). O Audiofy prepara o pacote:
a fonte pronta para upload e as instruções de foco, para o episódio manter o
espírito de cobertura integral do pipeline. O usuário gera e baixa o áudio
manualmente e pode guardá-lo na pasta do episódio.
"""

from __future__ import annotations

import json
from pathlib import Path

from .artifacts import artifact_prefix, source_document_filename
from .languages import prompt_label
from .pipeline import episode_dir
from .sources.base import ContentItem

# Só os pontos que não podem faltar entram no guia; o "contextual" ficaria ruído.
_MATRIX_CRITICALITY = ("critica", "importante")
_COVERAGE_FILENAME = "cobertura-para-o-notebooklm.md"

INSTRUCTIONS_TEMPLATE = """# Como gerar este episódio no NotebookLM (custo zero na assinatura)

1. Abra https://notebooklm.google.com e crie um notebook novo.
2. Adicione o arquivo `{source_file}` desta pasta como fonte.
3. Em "Audio Overview" → "Personalizar", cole o foco abaixo.
4. Gere, ouça e baixe o áudio.
5. Salve o arquivo baixado nesta pasta do episódio como `{final_audio_file}`.

Limites do plano (verificados no plano técnico): gratuito ≈ 3 áudios/dia;
Google AI Plus ≈ 6/dia; AI Pro tem limites maiores.

## Foco sugerido para o Audio Overview

> Cubra o conteúdo INTEGRALMENTE, em {language_label}: todas as teses,
> argumentos, exemplos, números, ressalvas e conclusões do autor — não apenas
> um resumo. Não invente fatos nem atribua ao autor o que ele não disse.
> Explique trechos de código pela finalidade, sem soletrar sintaxe.
> Abra citando o título e o autor e encerre com a atribuição:
> {attribution}

## Aviso de fidelidade

O NotebookLM é definido pelo Google como "resumo aprofundado" e NÃO garante
cobertura integral. Para episódios auditáveis (matriz de cobertura + auditoria),
use o pipeline normal do Audiofy. Este modo é o caminho rápido e barato.
"""


def _load_coverage_matrix(episode: Path) -> list[dict]:
    """Lê a matriz de cobertura do episódio, se o pipeline já a gerou."""
    path = episode / "coverage.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return []
    items = data.get("items") if isinstance(data, dict) else None
    return items if isinstance(items, list) else []


def _format_coverage_guide(items: list[dict]) -> str:
    """Transforma a matriz em um checklist legível para colar no NotebookLM.

    O NotebookLM não garante cobertura integral; entregar a lista dos pontos
    críticos e importantes que o pipeline extraiu do conteúdo dá a ele um guia
    concreto do que precisa aparecer no áudio, em vez de um resumo livre.
    """
    essential = [
        item
        for item in items
        if isinstance(item, dict)
        and item.get("criticality") in _MATRIX_CRITICALITY
        and isinstance(item.get("statement"), str)
        and item["statement"].strip()
    ]
    if not essential:
        return ""
    lines = [
        "# Pontos que o áudio precisa cobrir",
        "",
        "Extraídos pela matriz de cobertura do Audiofy. Cole esta lista junto do foco",
        "para orientar o NotebookLM a não deixar de fora nada essencial.",
        "",
    ]
    for item in essential:
        statement = " ".join(item["statement"].split())
        lines.append(f"- {statement}")
    return "\n".join(lines) + "\n"


def export_notebooklm_pack(
    item: ContentItem, source_key: str = "conteudo", language: str = "pt-BR"
) -> Path:
    """Escreve o pacote NotebookLM na pasta do episódio e retorna o caminho."""
    episode = episode_dir(item.item_id, language)
    pack_dir = episode / "notebooklm"
    pack_dir.mkdir(parents=True, exist_ok=True)
    source_file = source_document_filename(source_key, item.item_id)
    final_audio_file = (
        f"{artifact_prefix(source_key, item.item_id, 'notebooklm')}__audio-completo.mp3"
    )
    language_label = prompt_label(language)
    (pack_dir / source_file).write_text(
        f"# {item.title}\n\nFonte: {item.url}\n\n---\n\n{item.text}\n",
        encoding="utf-8",
    )
    coverage_guide = _format_coverage_guide(_load_coverage_matrix(episode))
    coverage_note = ""
    if coverage_guide:
        (pack_dir / _COVERAGE_FILENAME).write_text(coverage_guide, encoding="utf-8")
        coverage_note = (
            f"\n\n## Guia de cobertura (opcional, recomendado)\n\n"
            f"O arquivo `{_COVERAGE_FILENAME}` lista os pontos essenciais que o pipeline\n"
            f"do Audiofy extraiu deste conteúdo. Cole-o junto do foco acima para orientar\n"
            f"o NotebookLM a não deixar de fora nada crítico."
        )
    else:
        # Uma pasta reaproveitada pode ter o guia de uma exportação anterior; se a
        # matriz sumiu, o guia velho não pode ficar prometendo cobertura que saiu.
        (pack_dir / _COVERAGE_FILENAME).unlink(missing_ok=True)
    (pack_dir / "instrucoes.md").write_text(
        INSTRUCTIONS_TEMPLATE.format(
            attribution=item.attribution,
            source_file=source_file,
            final_audio_file=final_audio_file,
            language_label=language_label,
        )
        + coverage_note
        + "\n",
        encoding="utf-8",
    )
    return pack_dir
