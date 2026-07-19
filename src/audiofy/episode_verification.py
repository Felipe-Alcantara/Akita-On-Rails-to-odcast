"""Verifica artefatos concluídos e recalcula somente medidas observáveis.

Custos históricos não são inventados a partir de manifestos incompletos: a rotina preserva o
valor registrado e documenta se ele era exato ou reconstruído. Duração, palavras do roteiro e
silêncio, por outro lado, são medidos novamente nos artefatos locais.
"""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

from .audio_audit import audit_segments
from .estimates import read_episode_metrics
from .media import media_duration_seconds

_AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
_VERIFICATION_VERSION = 1


def _save_json(path: Path, data: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _turns(directory: Path) -> tuple[str, list[dict]]:
    for filename, mode in (("narration-script.json", "verbatim"), ("script.json", "adaptation")):
        path = directory / filename
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        turns = data.get("turns") if isinstance(data, dict) else None
        if not isinstance(turns, list):
            raise ValueError(f"{filename} não contém uma lista de turnos.")
        return mode, [turn for turn in turns if isinstance(turn, dict)]
    raise FileNotFoundError("O episódio não tem roteiro auditável.")


def verify_episode(
    directory: Path,
    *,
    source_words: int | None = None,
    verified_at: str | None = None,
) -> dict:
    """Recalcula métricas locais, audita chunks e grava ``verification.json``."""
    metrics = read_episode_metrics(directory)
    if metrics is None:
        raise FileNotFoundError("O episódio não tem metrics.json válido.")
    final_audio = directory / "episode.mp3"
    if not final_audio.is_file():
        raise FileNotFoundError("O episódio não tem episode.mp3.")

    mode, turns = _turns(directory)
    script_words = sum(len(str(turn.get("text", "")).split()) for turn in turns)
    duration_seconds = media_duration_seconds(final_audio)
    segments_directory = directory / "segments"
    segments = sorted(
        path
        for path in segments_directory.iterdir()
        if path.is_file() and path.suffix.lower() in _AUDIO_EXTENSIONS
    )
    if not segments:
        raise FileNotFoundError("O episódio não tem chunks de áudio.")
    audio_audit = audit_segments(directory, segments)
    timestamp = verified_at or datetime.now().astimezone().isoformat(timespec="seconds")

    source_check = {
        "status": "indisponivel" if source_words is None else "verificado",
        "metrics_words": metrics.source_words,
        "source_words": source_words,
        "matches": None if source_words is None else metrics.source_words == source_words,
    }
    verification = {
        "version": _VERIFICATION_VERSION,
        "verified_at": timestamp,
        "episode": directory.name,
        "checks": {
            "source_words": source_check,
            "script_words": {
                "metrics_words": metrics.script_words,
                "measured_words": script_words,
                "matches": metrics.script_words == script_words,
            },
            "duration": {
                "metrics_seconds": metrics.duration_seconds,
                "measured_seconds": duration_seconds,
                "difference_seconds": round(duration_seconds - metrics.duration_seconds, 6),
            },
            "cost": {
                "usd": metrics.cost_usd,
                "exact": metrics.cost_exact,
                "source": metrics.cost_source,
                "status": "preservado",
            },
            "generation_mode": {
                "metrics_mode": metrics.generation_mode,
                "artifact_mode": mode,
                "matches": metrics.generation_mode == mode,
            },
            "audio": audio_audit["summary"],
        },
    }
    recalculated = replace(
        metrics,
        source_words=source_words if source_words is not None else metrics.source_words,
        script_words=script_words,
        duration_seconds=duration_seconds,
        generation_mode=mode,
        verified_at=timestamp,
        verification_version=_VERIFICATION_VERSION,
    )
    _save_json(directory / "metrics.json", asdict(recalculated))
    _save_json(directory / "verification.json", verification)
    return verification
