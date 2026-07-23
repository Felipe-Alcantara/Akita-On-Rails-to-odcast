"""Análise de custos de geração de conteúdo de áudio.

Coleta métricas (custo, duração, data) de todos os episódios gerados,
calcula estatísticas agregadas e fornece estimativas para futuras gerações.
"""

from __future__ import annotations

import json
import statistics as stats_module
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class EpisodeMetrics:
    """Métricas de um episódio individual."""

    episode_dir: Path
    source_words: int
    script_words: int
    duration_seconds: float
    cost_usd: float
    generated_at: datetime
    verified_at: datetime | None = None
    tts_model: str | None = None
    profile_name: str | None = None

    @property
    def duration_minutes(self) -> float:
        return self.duration_seconds / 60.0

    @property
    def cost_per_second(self) -> float:
        if self.duration_seconds <= 0:
            return 0.0
        return self.cost_usd / self.duration_seconds

    @property
    def cost_per_minute(self) -> float:
        if self.duration_seconds <= 0:
            return 0.0
        return self.cost_per_second * 60.0

    @property
    def cost_per_word(self) -> float:
        if self.script_words <= 0:
            return 0.0
        return self.cost_usd / self.script_words


@dataclass
class CostAnalytics:
    """Análise agregada de custos de geração."""

    episodes: list[EpisodeMetrics]

    @property
    def total_episodes(self) -> int:
        return len(self.episodes)

    @property
    def total_cost_usd(self) -> float:
        return sum(e.cost_usd for e in self.episodes)

    @property
    def total_duration_seconds(self) -> float:
        return sum(e.duration_seconds for e in self.episodes)

    @property
    def total_duration_minutes(self) -> float:
        return self.total_duration_seconds / 60.0

    @property
    def total_duration_hours(self) -> float:
        return self.total_duration_minutes / 60.0

    @property
    def total_script_words(self) -> int:
        return sum(e.script_words for e in self.episodes)

    @property
    def total_source_words(self) -> int:
        return sum(e.source_words for e in self.episodes)

    @property
    def average_cost_per_second(self) -> float:
        if self.total_duration_seconds <= 0:
            return 0.0
        return self.total_cost_usd / self.total_duration_seconds

    @property
    def average_cost_per_minute(self) -> float:
        return self.average_cost_per_second * 60.0

    @property
    def average_cost_per_word(self) -> float:
        if self.total_script_words <= 0:
            return 0.0
        return self.total_cost_usd / self.total_script_words

    @property
    def average_cost_per_episode(self) -> float:
        if self.total_episodes == 0:
            return 0.0
        return self.total_cost_usd / self.total_episodes

    @property
    def average_duration_seconds(self) -> float:
        if self.total_episodes == 0:
            return 0.0
        return self.total_duration_seconds / self.total_episodes

    @property
    def average_duration_minutes(self) -> float:
        return self.average_duration_seconds / 60.0

    def cost_by_model(self) -> dict[str, float]:
        """Custo total por modelo TTS."""
        by_model: dict[str, float] = {}
        for ep in self.episodes:
            model = ep.tts_model or "desconhecido"
            by_model[model] = by_model.get(model, 0.0) + ep.cost_usd
        return by_model

    def cost_by_profile(self) -> dict[str, float]:
        """Custo total por perfil de configuração."""
        by_profile: dict[str, float] = {}
        for ep in self.episodes:
            profile = ep.profile_name or "desconhecido"
            by_profile[profile] = by_profile.get(profile, 0.0) + ep.cost_usd
        return by_profile

    def episodes_by_week(self) -> dict[str, int]:
        """Contar episódios gerados por semana (ISO 8601)."""
        by_week: dict[str, int] = {}
        for ep in self.episodes:
            week_key = ep.generated_at.strftime("%Y-W%V")
            by_week[week_key] = by_week.get(week_key, 0) + 1
        return by_week

    def cost_by_week(self) -> dict[str, float]:
        """Custo total por semana (ISO 8601)."""
        by_week: dict[str, float] = {}
        for ep in self.episodes:
            week_key = ep.generated_at.strftime("%Y-W%V")
            by_week[week_key] = by_week.get(week_key, 0.0) + ep.cost_usd
        return by_week

    def median_cost_per_minute(self) -> float:
        """Mediana do custo por minuto entre episódios."""
        if not self.episodes:
            return 0.0
        costs = [e.cost_per_minute for e in self.episodes if e.duration_seconds > 0]
        return stats_module.median(costs) if costs else 0.0

    def percentile_duration_seconds(self, percentile: int) -> float:
        """Percentil de duração entre episódios."""
        if not self.episodes:
            return 0.0
        durations = sorted([e.duration_seconds for e in self.episodes])
        idx = int(len(durations) * percentile / 100)
        return durations[min(idx, len(durations) - 1)]

    def estimate_total_cost(self, total_duration_seconds: float) -> float:
        """Estimar custo para uma duração de áudio dado a média histórica."""
        return total_duration_seconds * self.average_cost_per_second

    def estimate_total_cost_by_words(self, script_words: int) -> float:
        """Estimar custo para um número de palavras dado a média histórica."""
        return script_words * self.average_cost_per_word

    def estimate_generation_time(self, duration_seconds: float) -> float:
        """Estimar tempo de geração (simplificado: proporção de duração)."""
        if self.total_duration_seconds <= 0:
            return 0.0
        avg_gen_time = sum(
            (ep.verified_at - ep.generated_at).total_seconds()
            for ep in self.episodes
            if ep.verified_at
        ) / sum(1 for ep in self.episodes if ep.verified_at)
        seconds_ratio = duration_seconds / self.average_duration_seconds
        return avg_gen_time * seconds_ratio


def load_episode_metrics(episodes_dir: Path) -> list[EpisodeMetrics]:
    """Carregar métricas de todos os episódios em um diretório.

    Procura por `metrics.json` em cada subdiretório de episódios.
    Ignora episódios sem arquivo de métricas (não foi gerado ou corrompido).
    """
    metrics_list: list[EpisodeMetrics] = []

    if not episodes_dir.exists():
        return metrics_list

    for ep_dir in sorted(episodes_dir.iterdir()):
        if not ep_dir.is_dir():
            continue

        metrics_file = ep_dir / "metrics.json"
        if not metrics_file.exists():
            continue

        try:
            with metrics_file.open(encoding="utf-8") as f:
                data = json.load(f)

            generated_at = datetime.fromisoformat(data["generated_at"])
            verified_at = None
            if data.get("verified_at"):
                verified_at = datetime.fromisoformat(data["verified_at"])

            metrics = EpisodeMetrics(
                episode_dir=ep_dir,
                source_words=data.get("source_words", 0),
                script_words=data.get("script_words", 0),
                duration_seconds=data.get("duration_seconds", 0.0),
                cost_usd=data.get("cost_usd", 0.0),
                generated_at=generated_at,
                verified_at=verified_at,
                tts_model=data.get("tts_model"),
                profile_name=data.get("profile_name"),
            )
            metrics_list.append(metrics)
        except (json.JSONDecodeError, KeyError, ValueError):
            continue

    return metrics_list


def format_analytics_report(analytics: CostAnalytics) -> str:
    """Formatar análise de custos como relatório legível."""
    lines = [
        "┌─ 📊 ANÁLISE DE CUSTOS DE GERAÇÃO ─────────────────────────┐",
        "",
        f"  Episódios: {analytics.total_episodes}",
        f"  Duração total: {analytics.total_duration_hours:.1f}h ({analytics.total_duration_minutes:.0f}m)",
        f"  Palavras: {analytics.total_script_words:,} (roteiro) / {analytics.total_source_words:,} (origem)",
        "",
        "💰 CUSTOS",
        f"  Total: US$ {analytics.total_cost_usd:.4f}",
        f"  Por episódio: US$ {analytics.average_cost_per_episode:.4f}",
        f"  Por segundo: US$ {analytics.average_cost_per_second:.6f}",
        f"  Por minuto: US$ {analytics.average_cost_per_minute:.4f}",
        f"  Por palavra: US$ {analytics.average_cost_per_word:.6f}",
        f"  Mediana por minuto: US$ {analytics.median_cost_per_minute():.4f}",
        "",
        "⏱️  DURAÇÃO",
        f"  Média por episódio: {analytics.average_duration_minutes:.1f}m ({analytics.average_duration_seconds:.0f}s)",
        f"  Percentil 50%: {analytics.percentile_duration_seconds(50):.0f}s ({analytics.percentile_duration_seconds(50)/60:.1f}m)",
        f"  Percentil 75%: {analytics.percentile_duration_seconds(75):.0f}s ({analytics.percentile_duration_seconds(75)/60:.1f}m)",
        f"  Percentil 90%: {analytics.percentile_duration_seconds(90):.0f}s ({analytics.percentile_duration_seconds(90)/60:.1f}m)",
    ]

    models = analytics.cost_by_model()
    if models:
        lines.extend(["", "🎤 CUSTOS POR MODELO TTS"])
        for model, cost in sorted(models.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  {model}: US$ {cost:.4f}")

    profiles = analytics.cost_by_profile()
    if profiles:
        lines.extend(["", "⚙️  CUSTOS POR PERFIL"])
        for profile, cost in sorted(profiles.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  {profile}: US$ {cost:.4f}")

    cost_weeks = analytics.cost_by_week()
    episode_weeks = analytics.episodes_by_week()
    if cost_weeks:
        lines.extend(["", "📅 CUSTOS POR SEMANA"])
        for week in sorted(cost_weeks.keys(), reverse=True)[:4]:
            eps = episode_weeks.get(week, 0)
            cost = cost_weeks.get(week, 0.0)
            lines.append(f"  {week}: US$ {cost:.4f} ({eps} eps)")

    lines.append("")
    lines.append("📈 ESTIMATIVAS (baseadas na média histórica)")
    lines.append("")

    est_cost_10min = analytics.estimate_total_cost(600)
    est_cost_30min = analytics.estimate_total_cost(1800)
    est_cost_1h = analytics.estimate_total_cost(3600)
    lines.extend([
        f"  10 minutos: US$ {est_cost_10min:.4f}",
        f"  30 minutos: US$ {est_cost_30min:.4f}",
        f"  1 hora: US$ {est_cost_1h:.4f}",
        "",
    ])

    est_1000 = analytics.estimate_total_cost_by_words(1000)
    est_5000 = analytics.estimate_total_cost_by_words(5000)
    lines.extend([
        f"  1.000 palavras: US$ {est_1000:.4f}",
        f"  5.000 palavras: US$ {est_5000:.4f}",
        "",
    ])

    lines.append("└──────────────────────────────────────────────────────────┘")

    return "\n".join(lines)
