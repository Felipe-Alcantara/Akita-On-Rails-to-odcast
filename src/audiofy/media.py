"""Leitura portátil de metadados de áudio usados pelo pipeline e auditorias."""

from __future__ import annotations

import wave
from pathlib import Path

from .runtime.process import run_tool

FFPROBE_TIMEOUT_SECONDS = 120


def media_duration_seconds(path: Path) -> float:
    """Obtém a duração real de WAV/MP3 sem confiar no tamanho do arquivo."""
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as audio:
            framerate = audio.getframerate()
            if framerate <= 0:
                raise ValueError(f"WAV com taxa de amostragem inválida: {path.name}")
            return audio.getnframes() / framerate
    result = run_tool(
        "ffprobe",
        [
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        timeout=FFPROBE_TIMEOUT_SECONDS,
    )
    raw = result.stdout.strip()
    try:
        return float(raw)
    except ValueError as error:
        raise ValueError(
            f"ffprobe não retornou a duração de {path.name}: {raw[:100] or 'vazio'}"
        ) from error
