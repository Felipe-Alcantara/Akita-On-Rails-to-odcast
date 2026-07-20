"""Exportação para o modo NotebookLM — o caminho barato.

O NotebookLM pessoal não tem API, mas gera Audio Overviews de ótima qualidade
dentro da assinatura Google (custo marginal zero). O Audiofy prepara o pacote:
a fonte pronta para upload e as instruções de foco, para o episódio manter o
espírito de cobertura integral do pipeline. O usuário gera e baixa o áudio
manualmente e pode guardá-lo na pasta do episódio.
"""

from __future__ import annotations

from pathlib import Path

from .artifacts import artifact_prefix, source_document_filename
from .pipeline import episode_dir
from .sources.base import ContentItem

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


def export_notebooklm_pack(item: ContentItem, source_key: str = "conteudo",
                           language: str = "pt-BR") -> Path:
    """Escreve o pacote NotebookLM na pasta do episódio e retorna o caminho."""
    pack_dir = episode_dir(item.item_id, language) / "notebooklm"
    pack_dir.mkdir(parents=True, exist_ok=True)
    source_file = source_document_filename(source_key, item.item_id)
    final_audio_file = (
        f"{artifact_prefix(source_key, item.item_id, 'notebooklm')}__audio-completo.mp3"
    )
    language_label = "English" if language == "en" else "português brasileiro"
    (pack_dir / source_file).write_text(
        f"# {item.title}\n\nFonte: {item.url}\n\n---\n\n{item.text}\n",
        encoding="utf-8",
    )
    (pack_dir / "instrucoes.md").write_text(
        INSTRUCTIONS_TEMPLATE.format(
            attribution=item.attribution,
            source_file=source_file,
            final_audio_file=final_audio_file,
            language_label=language_label,
        ),
        encoding="utf-8",
    )
    return pack_dir
