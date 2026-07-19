"""Estimativas empíricas de duração/custo e fallback de preço do TTS.

As médias usam totais ponderados, nunca a média simples de episódios com tamanhos
diferentes. Custos realizados são persistidos em ``metrics.json`` pelo pipeline.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import EPISODES_DIR

_PILOT_WORDS = 2_155
_PILOT_DURATION_SECONDS = 781.704
_PILOT_COST_USD = 0.624287

# Preços por milhão de tokens e taxa documentada pelo Google. Esse mapa é
# apenas fallback quando o OpenRouter não disponibiliza o custo da geração.
_TTS_TOKEN_PRICING = {
    "google/gemini-3.1-flash-tts-preview": {
        "input_per_million": 1.0,
        "output_per_million": 20.0,
        "audio_tokens_per_second": 25.0,
    },
}


@dataclass(frozen=True)
class EpisodeEstimate:
    duration_minutes: float
    duration_min_minutes: float
    duration_max_minutes: float
    speaking_rate_wpm: float
    cost_usd: float
    cost_min_usd: float
    cost_max_usd: float
    sample_count: int


@dataclass(frozen=True)
class EpisodeMetrics:
    source_words: int
    script_words: int
    duration_seconds: float
    cost_usd: float
    cost_exact: bool
    tts_model: str
    profile_name: str
    generation_mode: str = "adaptation"
    generated_at: str = ""
    cost_source: str = "generation_ids"
    background_music: str | None = None
    background_volume: float | None = None
    verified_at: str = ""
    verification_version: int = 0

    def write(self, directory: Path) -> Path:
        target = directory / "metrics.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(target)
        return target


def read_episode_metrics(directory: Path) -> EpisodeMetrics | None:
    path = directory / "metrics.json"
    if not path.is_file():
        return None
    try:
        return EpisodeMetrics(**json.loads(path.read_text(encoding="utf-8")))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _load_samples(
    root: Path,
    tts_model: str,
    profile_name: str | None = None,
    generation_mode: str | None = None,
) -> list[dict]:
    samples: list[dict] = []
    if not root.is_dir():
        return samples
    for path in root.glob("*/metrics.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            words = int(data.get("source_words", 0))
            duration = float(data.get("duration_seconds", 0))
            cost = float(data.get("cost_usd", 0))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        same_profile = profile_name is None or data.get("profile_name") == profile_name
        # Artefatos anteriores à leitura fiel não gravavam o campo; todos eram adaptação.
        sample_mode = data.get("generation_mode", "adaptation")
        same_mode = generation_mode is None or sample_mode == generation_mode
        if (
            words > 0
            and duration > 0
            and cost > 0
            and same_profile
            and same_mode
            and math.isfinite(duration)
            and math.isfinite(cost)
            and data.get("tts_model") == tts_model
        ):
            samples.append({"words": words, "duration": duration, "cost": cost})
    return samples


def estimate_episode(
    source_words: int,
    tts_model: str,
    episodes_root: Path = EPISODES_DIR,
    profile_name: str | None = None,
    generation_mode: str | None = None,
) -> EpisodeEstimate:
    """Calcula média ponderada do mesmo modelo e histórico compatível.

    A interface informa ``generation_mode`` e usa todos os perfis daquele formato. Isso evita
    confundir a proporção texto/roteiro de podcasts com a leitura literal e não descarta episódios
    reais só porque o preset mudou. ``profile_name`` permanece para integrações legadas.
    """
    if source_words <= 0:
        raise ValueError("A estimativa exige uma contagem positiva de palavras.")
    samples = _load_samples(episodes_root, tts_model, profile_name, generation_mode)
    if not samples:
        samples = [
            {
                "words": _PILOT_WORDS,
                "duration": _PILOT_DURATION_SECONDS,
                "cost": _PILOT_COST_USD,
            }
        ]
        sample_count = 0
    else:
        sample_count = len(samples)

    total_words = sum(sample["words"] for sample in samples)
    total_minutes = sum(sample["duration"] for sample in samples) / 60
    total_cost = sum(sample["cost"] for sample in samples)
    speaking_rate = total_words / total_minutes
    duration = source_words / speaking_rate
    cost = source_words * total_cost / total_words

    sample_rates = [sample["words"] / (sample["duration"] / 60) for sample in samples]
    cost_rates = [sample["cost"] / sample["words"] for sample in samples]
    duration_min = source_words / max(sample_rates)
    duration_max = source_words / min(sample_rates)
    cost_min = source_words * min(cost_rates)
    cost_max = source_words * max(cost_rates)
    if len(samples) == 1:
        duration_min, duration_max = duration * 0.85, duration * 1.15
        cost_min, cost_max = cost * 0.80, cost * 1.20

    return EpisodeEstimate(
        duration_minutes=duration,
        duration_min_minutes=duration_min,
        duration_max_minutes=duration_max,
        speaking_rate_wpm=speaking_rate,
        cost_usd=cost,
        cost_min_usd=cost_min,
        cost_max_usd=cost_max,
        sample_count=sample_count,
    )


def estimate_tts_cost(settings, text: str, instructions: str, duration_seconds: float) -> float:
    """Fallback por tabela oficial; custo por geração continua sendo preferido."""
    pricing = _TTS_TOKEN_PRICING.get(settings.tts_model)
    if not pricing or duration_seconds <= 0:
        return 0.0
    input_tokens = max(1.0, len(text + instructions) / 4)
    output_tokens = duration_seconds * pricing["audio_tokens_per_second"]
    return (
        input_tokens * pricing["input_per_million"] + output_tokens * pricing["output_per_million"]
    ) / 1_000_000
