"""Auditoria objetiva de silêncio nos chunks de voz gerados."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .media import media_duration_seconds
from .runtime.process import run_tool

AUDIT_FILE = "audio-audit.json"
SILENCE_THRESHOLD_DB = -45
MIN_SILENCE_SECONDS = 1.5
WARNING_SILENCE_SECONDS = 2.5
CRITICAL_SILENCE_SECONDS = 5.0
CRITICAL_SILENCE_RATIO = 0.35
_AUDIT_TIMEOUT_SECONDS = 300
_SILENCE_EVENT = re.compile(r"silence_end:\s*([0-9.]+)\s*\|\s*silence_duration:\s*([0-9.]+)")


@dataclass(frozen=True)
class SilenceSpan:
    start_seconds: float
    end_seconds: float
    duration_seconds: float


@dataclass(frozen=True)
class SegmentAudioAudit:
    file: str
    duration_seconds: float
    silence_seconds: float
    silence_ratio: float
    longest_silence_seconds: float
    severity: str
    silences: tuple[SilenceSpan, ...]


def _parse_silences(stderr: str) -> tuple[SilenceSpan, ...]:
    spans: list[SilenceSpan] = []
    for match in _SILENCE_EVENT.finditer(stderr):
        end = float(match.group(1))
        duration = float(match.group(2))
        spans.append(
            SilenceSpan(
                start_seconds=round(max(0.0, end - duration), 3),
                end_seconds=round(end, 3),
                duration_seconds=round(duration, 3),
            )
        )
    return tuple(spans)


def audit_segment(path: Path) -> SegmentAudioAudit:
    """Mede silêncio perceptível em um chunk sem alterar o áudio."""
    duration = media_duration_seconds(path)
    completed = run_tool(
        "ffmpeg",
        [
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            f"silencedetect=noise={SILENCE_THRESHOLD_DB}dB:d={MIN_SILENCE_SECONDS}",
            "-f",
            "null",
            "-",
        ],
        timeout=_AUDIT_TIMEOUT_SECONDS,
        check=False,
    )
    silences = _parse_silences(completed.stderr)
    silence_seconds = sum(span.duration_seconds for span in silences)
    longest = max((span.duration_seconds for span in silences), default=0.0)
    ratio = min(1.0, silence_seconds / duration) if duration > 0 else 1.0
    if longest >= CRITICAL_SILENCE_SECONDS or ratio >= CRITICAL_SILENCE_RATIO:
        severity = "critical"
    elif longest >= WARNING_SILENCE_SECONDS:
        severity = "warning"
    else:
        severity = "ok"
    return SegmentAudioAudit(
        file=path.name,
        duration_seconds=round(duration, 3),
        silence_seconds=round(silence_seconds, 3),
        silence_ratio=round(ratio, 4),
        longest_silence_seconds=round(longest, 3),
        severity=severity,
        silences=silences,
    )


def audit_segments(
    directory: Path,
    segments: list[Path],
    on_progress: Callable[[int], None] | None = None,
) -> dict:
    """Audita chunks, persiste resultado atômico e retorna o documento completo."""
    results: list[SegmentAudioAudit] = []
    for index, segment in enumerate(segments, start=1):
        results.append(audit_segment(segment))
        if on_progress:
            on_progress(index)
    critical = sum(result.severity == "critical" for result in results)
    warnings = sum(result.severity == "warning" for result in results)
    document = {
        "version": 1,
        "audited_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "policy": {
            "threshold_db": SILENCE_THRESHOLD_DB,
            "minimum_silence_seconds": MIN_SILENCE_SECONDS,
            "warning_silence_seconds": WARNING_SILENCE_SECONDS,
            "critical_silence_seconds": CRITICAL_SILENCE_SECONDS,
            "critical_silence_ratio": CRITICAL_SILENCE_RATIO,
        },
        "summary": {
            "segments": len(results),
            "ok": len(results) - critical - warnings,
            "warnings": warnings,
            "critical": critical,
        },
        "segments": [asdict(result) for result in results],
    }
    target = directory / AUDIT_FILE
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(target)
    return document


def read_audio_audit(directory: Path) -> dict | None:
    path = directory / AUDIT_FILE
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(document.get("segments"), list) or not isinstance(
        document.get("summary"), dict
    ):
        return None
    return document
