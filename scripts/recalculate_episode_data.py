#!/usr/bin/env python3
"""Recalcula métricas observáveis e auditoria de todos os episódios concluídos."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from audiofy.config import EPISODES_DIR  # noqa: E402
from audiofy.episode_verification import verify_episode  # noqa: E402


def _known_source_words(directory: Path) -> int | None:
    """Resolve somente fontes locais; ausência nunca dispara sincronização ou rede."""
    from audiofy.sources.custom import CustomSource

    custom_path = PROJECT_ROOT / "data" / "inbox" / f"{directory.name}.md"
    if custom_path.is_file():
        return CustomSource(custom_path.parent).get_item(directory.name).words
    if "__" in directory.name:
        from audiofy.sources.akita import AkitaSource

        source = AkitaSource()
        if source.is_ready():
            return source.get_item(directory.name.replace("__", "/", 1)).words
    return None


def recalculate_all(root: Path) -> list[dict]:
    results = []
    for directory in sorted(path for path in root.iterdir() if path.is_dir()):
        if not (directory / "episode.mp3").is_file():
            continue
        verification = verify_episode(
            directory,
            source_words=_known_source_words(directory),
        )
        summary = verification["checks"]["audio"]
        results.append(verification)
        print(
            f"✔ {directory.name}: {summary['segments']} chunks, "
            f"{summary['critical']} críticos, {summary['warnings']} avisos"
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=EPISODES_DIR)
    args = parser.parse_args()
    if not args.root.is_dir():
        parser.error(f"Diretório de episódios inexistente: {args.root}")
    results = recalculate_all(args.root)
    print(f"\n{len(results)} episódio(s) recalculado(s) sem chamadas de rede.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
