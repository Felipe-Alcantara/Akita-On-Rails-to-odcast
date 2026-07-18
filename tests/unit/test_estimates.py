"""Médias empíricas e fallback de preço para estimativas honestas."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy.estimates import estimate_episode, estimate_tts_cost  # noqa: E402


class EpisodeEstimateTest(unittest.TestCase):
    def test_media_ponderada_e_faixa_usam_episodios_concluidos(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = [
                {
                    "source_words": 2_155,
                    "duration_seconds": 781.704,
                    "cost_usd": 0.624287,
                    "tts_model": "google/tts",
                },
                {
                    "source_words": 2_771,
                    "duration_seconds": 1_192.512,
                    "cost_usd": 1.191272,
                    "tts_model": "google/tts",
                },
            ]
            for index, sample in enumerate(samples):
                directory = root / str(index)
                directory.mkdir()
                (directory / "metrics.json").write_text(json.dumps(sample), encoding="utf-8")

            estimate = estimate_episode(2_771, "google/tts", root)

        self.assertEqual(estimate.sample_count, 2)
        self.assertAlmostEqual(estimate.speaking_rate_wpm, 149.71, places=2)
        self.assertAlmostEqual(estimate.duration_minutes, 18.51, places=2)
        self.assertAlmostEqual(estimate.cost_usd, 1.02, places=2)
        self.assertAlmostEqual(estimate.cost_min_usd, 0.80, places=2)
        self.assertAlmostEqual(estimate.cost_max_usd, 1.19, places=2)

    def test_fallback_gemini_usa_preco_e_tokens_de_audio_oficiais(self):
        cost = estimate_tts_cost(
            SimpleNamespace(tts_model="google/gemini-3.1-flash-tts-preview"),
            text="fala curta",
            instructions="tom natural",
            duration_seconds=60,
        )

        self.assertGreater(cost, 0.030)
        self.assertLess(cost, 0.031)

    def test_perfil_diferente_nao_entra_na_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for profile, cost in (("economico", 0.5), ("padrao", 1.5)):
                directory = root / profile
                directory.mkdir()
                (directory / "metrics.json").write_text(
                    json.dumps(
                        {
                            "source_words": 1_000,
                            "duration_seconds": 600,
                            "cost_usd": cost,
                            "tts_model": "google/tts",
                            "profile_name": profile,
                        }
                    ),
                    encoding="utf-8",
                )

            estimate = estimate_episode(2_000, "google/tts", root, profile_name="economico")

        self.assertEqual(estimate.sample_count, 1)
        self.assertEqual(estimate.cost_usd, 1.0)

    def test_amostra_sem_custo_real_nao_distorce_a_media(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "incompleto"
            directory.mkdir()
            (directory / "metrics.json").write_text(
                json.dumps(
                    {
                        "source_words": 1_000,
                        "duration_seconds": 600,
                        "cost_usd": 0,
                        "tts_model": "google/tts",
                    }
                ),
                encoding="utf-8",
            )

            estimate = estimate_episode(2_155, "google/tts", root)

        self.assertEqual(estimate.sample_count, 0)
        self.assertAlmostEqual(estimate.cost_usd, 0.624287)


if __name__ == "__main__":
    unittest.main()
