"""Normalização de volume por segmento antes da montagem final.

O TTS pode gerar chunks com intensidades bem diferentes — trechos de sussurro,
diálogos enérgicos e narrações neutras ficam visivelmente desnivelados quando
concatenados. O ``loudnorm`` na montagem final atenua o problema, mas como é um
filtro de passagem única sobre o stream inteiro, diferenças locais grandes
sobrevivem.

Este módulo mede cada segmento individualmente (LUFS integrado + pico real) e
equaliza apenas os que estão abaixo de um limiar, aplicando ``loudnorm`` em
duas passagens (medição → normalização linear). Segmentos já no nível-alvo
permanecem intactos.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .media import media_duration_seconds
from .runtime.process import run_tool

# O TTS Gemini gera WAVs de duração variável; chunks curtíssimos não têm
# conteúdo estatístico suficiente para o loudnorm e podem distorcer.
_MIN_DURATION_SECONDS = 0.5

_LOUDNORM_TIMEOUT = 300

# Diferença mínima (LUFS) entre o nível medido e o alvo para justificar
# a re-codificação. Abaixo disto, o custo de I/O supera o ganho audível.
DEFAULT_THRESHOLD_LUFS = 3.0
DEFAULT_TARGET_LUFS = -16.0
DEFAULT_TRUE_PEAK = -1.5
DEFAULT_LRA = 11.0

_LOUDNORM_JSON_RE = re.compile(
    r"\{[^{}]*\"input_i\"[^{}]*\"target_offset\"[^{}]*\}",
    re.DOTALL,
)


@dataclass(frozen=True)
class LoudnessInfo:
    """Medição de intensidade de um segmento de áudio."""

    integrated_lufs: float
    true_peak_dbfs: float
    lra: float
    threshold_lufs: float


@dataclass(frozen=True)
class NormResult:
    """Resultado da normalização de um segmento."""

    file: str
    original_lufs: float
    normalized: bool
    reason: str  # "ok" | "normalized" | "too_short" | "measurement_failed"


def measure_loudness(path: Path) -> LoudnessInfo | None:
    """Mede LUFS integrado, pico real e LRA de um segmento WAV/MP3.

    Retorna ``None`` quando o FFmpeg não produz a saída esperada (chunk vazio,
    formato não reconhecido, etc.) — o chamador decide o que fazer.
    """
    completed = run_tool(
        "ffmpeg",
        [
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            (
                f"loudnorm=I={DEFAULT_TARGET_LUFS}:TP={DEFAULT_TRUE_PEAK}"
                f":LRA={DEFAULT_LRA}:print_format=json"
            ),
            "-f",
            "null",
            "-",
        ],
        timeout=_LOUDNORM_TIMEOUT,
        check=False,
    )
    return _parse_loudnorm_json(completed.stderr)


def _parse_loudnorm_json(stderr: str) -> LoudnessInfo | None:
    """Extrai o bloco JSON que o filtro ``loudnorm`` imprime em *stderr*."""
    match = _LOUDNORM_JSON_RE.search(stderr)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return LoudnessInfo(
            integrated_lufs=float(data["input_i"]),
            true_peak_dbfs=float(data["input_tp"]),
            lra=float(data["input_lra"]),
            threshold_lufs=float(data["input_thresh"]),
        )
    except (KeyError, ValueError, TypeError):
        return None


def _apply_loudnorm(
    path: Path,
    measurement: LoudnessInfo,
    target_lufs: float = DEFAULT_TARGET_LUFS,
    true_peak: float = DEFAULT_TRUE_PEAK,
    lra: float = DEFAULT_LRA,
) -> None:
    """Aplica ``loudnorm`` linear em duas passagens, sobrescrevendo o segmento."""
    temporary = path.with_suffix(path.suffix + ".norm.tmp")
    try:
        run_tool(
            "ffmpeg",
            [
                "-y",
                "-hide_banner",
                "-nostats",
                "-i",
                str(path),
                "-af",
                (
                    f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={lra}"
                    f":measured_I={measurement.integrated_lufs}"
                    f":measured_TP={measurement.true_peak_dbfs}"
                    f":measured_LRA={measurement.lra}"
                    f":measured_thresh={measurement.threshold_lufs}"
                    ":linear=true"
                ),
                str(temporary),
            ],
            timeout=_LOUDNORM_TIMEOUT,
        )
        if not temporary.is_file() or temporary.stat().st_size < 100:
            raise ValueError("O FFmpeg não gerou saída válida na normalização.")
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def normalize_segments(
    segments: list[Path],
    target_lufs: float = DEFAULT_TARGET_LUFS,
    threshold_lufs: float = DEFAULT_THRESHOLD_LUFS,
    on_progress: Callable[[int], None] | None = None,
) -> list[NormResult]:
    """Equaliza segmentos com volume abaixo do alvo.

    Apenas segmentos com LUFS integrado inferior a ``target_lufs - threshold_lufs``
    são re-codificados; os demais permanecem inalterados.

    Retorna um relatório por segmento para log e diagnóstico.
    """
    results: list[NormResult] = []
    for index, segment in enumerate(segments, 1):
        result = _normalize_one(segment, target_lufs, threshold_lufs)
        results.append(result)
        if on_progress:
            on_progress(index)
    return results


def _normalize_one(
    path: Path,
    target_lufs: float,
    threshold_lufs: float,
) -> NormResult:
    """Mede e, se necessário, normaliza um único segmento."""
    duration = media_duration_seconds(path)
    if duration < _MIN_DURATION_SECONDS:
        return NormResult(path.name, 0.0, False, "too_short")

    measurement = measure_loudness(path)
    if measurement is None:
        return NormResult(path.name, 0.0, False, "measurement_failed")

    distance = target_lufs - measurement.integrated_lufs
    if distance < threshold_lufs:
        return NormResult(path.name, measurement.integrated_lufs, False, "ok")

    _apply_loudnorm(path, measurement, target_lufs)
    return NormResult(path.name, measurement.integrated_lufs, True, "normalized")
