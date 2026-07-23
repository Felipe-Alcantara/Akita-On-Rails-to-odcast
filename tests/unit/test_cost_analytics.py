"""Testes do módulo de análise de custos de geração."""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy.cost_analytics import (
    CostAnalytics,
    EpisodeMetrics,
    format_analytics_report,
    load_episode_metrics,
)


class EpisodeMetricsTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now()
        self.episode = EpisodeMetrics(
            episode_dir=Path("/test/ep1"),
            source_words=2000,
            script_words=1800,
            duration_seconds=600.0,
            cost_usd=0.5,
            generated_at=self.now,
            verified_at=self.now + timedelta(seconds=120),
            tts_model="google/gemini-3.1-flash-tts-preview",
            profile_name="padrao",
        )

    def test_duration_minutes(self):
        self.assertEqual(self.episode.duration_minutes, 10.0)

    def test_cost_per_second(self):
        self.assertAlmostEqual(self.episode.cost_per_second, 0.5 / 600.0, places=6)

    def test_cost_per_minute(self):
        self.assertAlmostEqual(self.episode.cost_per_minute, 0.5 / 10.0, places=6)

    def test_cost_per_word(self):
        self.assertAlmostEqual(self.episode.cost_per_word, 0.5 / 1800.0, places=6)

    def test_zero_duration_cost_per_second(self):
        ep = EpisodeMetrics(
            episode_dir=Path("/test"),
            source_words=0,
            script_words=0,
            duration_seconds=0.0,
            cost_usd=0.0,
            generated_at=self.now,
        )
        self.assertEqual(ep.cost_per_second, 0.0)
        self.assertEqual(ep.cost_per_minute, 0.0)


class CostAnalyticsTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now()
        self.episodes = [
            EpisodeMetrics(
                episode_dir=Path(f"/test/ep{i}"),
                source_words=2000,
                script_words=1800,
                duration_seconds=600.0,
                cost_usd=0.5,
                generated_at=self.now - timedelta(days=14 - i * 7),
                verified_at=self.now - timedelta(days=14 - i * 7, seconds=-120),
                tts_model="google/gemini-3.1-flash-tts-preview",
                profile_name="padrao",
            )
            for i in range(3)
        ]
        self.analytics = CostAnalytics(episodes=self.episodes)

    def test_total_episodes(self):
        self.assertEqual(self.analytics.total_episodes, 3)

    def test_total_cost_usd(self):
        self.assertAlmostEqual(self.analytics.total_cost_usd, 1.5, places=6)

    def test_total_duration_seconds(self):
        self.assertAlmostEqual(self.analytics.total_duration_seconds, 1800.0, places=6)

    def test_total_duration_minutes(self):
        self.assertAlmostEqual(self.analytics.total_duration_minutes, 30.0, places=6)

    def test_total_duration_hours(self):
        self.assertAlmostEqual(self.analytics.total_duration_hours, 0.5, places=6)

    def test_total_script_words(self):
        self.assertEqual(self.analytics.total_script_words, 5400)

    def test_total_source_words(self):
        self.assertEqual(self.analytics.total_source_words, 6000)

    def test_average_cost_per_second(self):
        expected = 1.5 / 1800.0
        self.assertAlmostEqual(self.analytics.average_cost_per_second, expected, places=6)

    def test_average_cost_per_minute(self):
        expected = (1.5 / 1800.0) * 60
        self.assertAlmostEqual(self.analytics.average_cost_per_minute, expected, places=6)

    def test_average_cost_per_word(self):
        expected = 1.5 / 5400
        self.assertAlmostEqual(self.analytics.average_cost_per_word, expected, places=6)

    def test_average_cost_per_episode(self):
        self.assertAlmostEqual(self.analytics.average_cost_per_episode, 0.5, places=6)

    def test_average_duration_seconds(self):
        self.assertAlmostEqual(self.analytics.average_duration_seconds, 600.0, places=6)

    def test_average_duration_minutes(self):
        self.assertAlmostEqual(self.analytics.average_duration_minutes, 10.0, places=6)

    def test_cost_by_model(self):
        by_model = self.analytics.cost_by_model()
        self.assertEqual(by_model["google/gemini-3.1-flash-tts-preview"], 1.5)

    def test_cost_by_model_unknown(self):
        episodes = [
            EpisodeMetrics(
                episode_dir=Path("/test/ep1"),
                source_words=1000,
                script_words=900,
                duration_seconds=300.0,
                cost_usd=0.1,
                generated_at=self.now,
                tts_model=None,
            ),
            EpisodeMetrics(
                episode_dir=Path("/test/ep2"),
                source_words=1000,
                script_words=900,
                duration_seconds=300.0,
                cost_usd=0.2,
                generated_at=self.now,
                tts_model="other/model",
            ),
        ]
        analytics = CostAnalytics(episodes=episodes)
        by_model = analytics.cost_by_model()
        self.assertEqual(by_model["desconhecido"], 0.1)
        self.assertEqual(by_model["other/model"], 0.2)

    def test_cost_by_profile(self):
        by_profile = self.analytics.cost_by_profile()
        self.assertEqual(by_profile["padrao"], 1.5)

    def test_episodes_by_week(self):
        by_week = self.analytics.episodes_by_week()
        self.assertGreater(len(by_week), 0)
        self.assertTrue(all(count >= 1 for count in by_week.values()))
        total_eps = sum(by_week.values())
        self.assertEqual(total_eps, 3)

    def test_cost_by_week(self):
        by_week = self.analytics.cost_by_week()
        self.assertGreater(len(by_week), 0)
        self.assertTrue(all(cost >= 0.0 for cost in by_week.values()))
        total_cost = sum(by_week.values())
        self.assertAlmostEqual(total_cost, 1.5, places=6)

    def test_median_cost_per_minute(self):
        median = self.analytics.median_cost_per_minute()
        self.assertGreater(median, 0.0)

    def test_percentile_duration_seconds(self):
        p50 = self.analytics.percentile_duration_seconds(50)
        self.assertAlmostEqual(p50, 600.0, places=1)

    def test_percentile_duration_seconds_empty(self):
        analytics = CostAnalytics(episodes=[])
        p50 = analytics.percentile_duration_seconds(50)
        self.assertEqual(p50, 0.0)

    def test_estimate_total_cost(self):
        estimated = self.analytics.estimate_total_cost(600.0)
        self.assertGreater(estimated, 0.0)

    def test_estimate_total_cost_by_words(self):
        estimated = self.analytics.estimate_total_cost_by_words(1000)
        self.assertGreater(estimated, 0.0)

    def test_estimate_generation_time(self):
        estimated = self.analytics.estimate_generation_time(600.0)
        self.assertGreaterEqual(estimated, 0.0)

    def test_empty_analytics(self):
        empty = CostAnalytics(episodes=[])
        self.assertEqual(empty.total_episodes, 0)
        self.assertEqual(empty.total_cost_usd, 0.0)
        self.assertEqual(empty.total_duration_seconds, 0.0)
        self.assertEqual(empty.average_cost_per_episode, 0.0)


class LoadEpisodeMetricsTest(unittest.TestCase):
    def test_load_valid_metrics(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            episodes_dir = Path(tmpdir) / "episodes"
            episodes_dir.mkdir()

            ep_dir = episodes_dir / "2026-07-01-test"
            ep_dir.mkdir()

            metrics_data = {
                "source_words": 2000,
                "script_words": 1800,
                "duration_seconds": 600.0,
                "cost_usd": 0.5,
                "generated_at": "2026-07-01T12:00:00",
                "verified_at": "2026-07-01T12:02:00",
                "tts_model": "google/gemini-3.1-flash-tts-preview",
                "profile_name": "padrao",
            }
            metrics_file = ep_dir / "metrics.json"
            with metrics_file.open("w") as f:
                json.dump(metrics_data, f)

            metrics = load_episode_metrics(episodes_dir)
            self.assertEqual(len(metrics), 1)
            self.assertEqual(metrics[0].source_words, 2000)
            self.assertEqual(metrics[0].script_words, 1800)
            self.assertAlmostEqual(metrics[0].duration_seconds, 600.0, places=1)
            self.assertAlmostEqual(metrics[0].cost_usd, 0.5, places=4)

    def test_load_missing_metrics(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            episodes_dir = Path(tmpdir) / "episodes"
            episodes_dir.mkdir()

            ep_dir = episodes_dir / "2026-07-01-test"
            ep_dir.mkdir()

            metrics = load_episode_metrics(episodes_dir)
            self.assertEqual(len(metrics), 0)

    def test_load_corrupted_metrics(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            episodes_dir = Path(tmpdir) / "episodes"
            episodes_dir.mkdir()

            ep_dir = episodes_dir / "2026-07-01-test"
            ep_dir.mkdir()

            metrics_file = ep_dir / "metrics.json"
            with metrics_file.open("w") as f:
                f.write("invalid json {]")

            metrics = load_episode_metrics(episodes_dir)
            self.assertEqual(len(metrics), 0)

    def test_load_missing_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            episodes_dir = Path(tmpdir) / "episodes"
            episodes_dir.mkdir()

            ep_dir = episodes_dir / "2026-07-01-test"
            ep_dir.mkdir()

            metrics_data = {
                "source_words": 2000,
                "generated_at": "2026-07-01T12:00:00",
            }
            metrics_file = ep_dir / "metrics.json"
            with metrics_file.open("w") as f:
                json.dump(metrics_data, f)

            metrics = load_episode_metrics(episodes_dir)
            self.assertEqual(len(metrics), 1)
            self.assertEqual(metrics[0].script_words, 0)
            self.assertEqual(metrics[0].duration_seconds, 0.0)

    def test_load_nonexistent_directory(self):
        nonexistent = Path("/nonexistent/episodes")
        metrics = load_episode_metrics(nonexistent)
        self.assertEqual(len(metrics), 0)


class FormatAnalyticsReportTest(unittest.TestCase):
    def test_report_format(self):
        now = datetime.now()
        episodes = [
            EpisodeMetrics(
                episode_dir=Path(f"/test/ep{i}"),
                source_words=2000,
                script_words=1800,
                duration_seconds=600.0,
                cost_usd=0.5,
                generated_at=now,
                verified_at=now + timedelta(seconds=120),
                tts_model="google/gemini-3.1-flash-tts-preview",
                profile_name="padrao",
            )
            for i in range(2)
        ]
        analytics = CostAnalytics(episodes=episodes)
        report = format_analytics_report(analytics)

        self.assertIn("ANÁLISE DE CUSTOS", report)
        self.assertIn("US$", report)
        self.assertIn("Episódios:", report)
        self.assertIn("Duração total:", report)

    def test_report_empty(self):
        analytics = CostAnalytics(episodes=[])
        report = format_analytics_report(analytics)
        self.assertIn("ANÁLISE DE CUSTOS", report)
        self.assertIn("Episódios: 0", report)


if __name__ == "__main__":
    unittest.main()
