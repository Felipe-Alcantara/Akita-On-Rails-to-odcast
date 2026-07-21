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
            for profile, cost in (("gemini-duo-economico", 0.5), ("gemini-duo", 1.5)):
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

            estimate = estimate_episode(
                2_000, "google/tts", root, profile_name="gemini-duo-economico"
            )

        self.assertEqual(estimate.sample_count, 1)
        self.assertEqual(estimate.cost_usd, 1.0)

    def test_formato_usa_todos_os_perfis_compativeis_sem_misturar_leitura(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            samples = [
                ("gemini-duo", "adaptation", 0.4),
                ("gemini-duo-economico", "adaptation", 0.6),
                ("narrador", "verbatim", 0.2),
            ]
            for profile, mode, cost in samples:
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
                            "generation_mode": mode,
                        }
                    ),
                    encoding="utf-8",
                )

            adaptation = estimate_episode(2_000, "google/tts", root, generation_mode="adaptation")
            verbatim = estimate_episode(2_000, "google/tts", root, generation_mode="verbatim")

        self.assertEqual(adaptation.sample_count, 2)
        self.assertEqual(adaptation.cost_usd, 1.0)
        self.assertEqual(verbatim.sample_count, 1)
        self.assertEqual(verbatim.cost_usd, 0.4)

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

    def _write(self, directory, *, words, seconds, cost, mode="adaptation"):
        directory.mkdir()
        (directory / "metrics.json").write_text(
            json.dumps(
                {
                    "source_words": words,
                    "duration_seconds": seconds,
                    "cost_usd": cost,
                    "tts_model": "google/tts",
                    "generation_mode": mode,
                }
            ),
            encoding="utf-8",
        )

    def test_modo_com_uma_amostra_usa_a_variancia_real_do_tts(self):
        # reflexive tem 1 amostra; adaptation tem duas bem diferentes. A faixa do
        # reflexive deve refletir essa dispersão real, não um ±15% arbitrário.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root / "a1", words=1_000, seconds=600, cost=0.40, mode="adaptation")
            self._write(root / "a2", words=1_000, seconds=300, cost=1.20, mode="adaptation")
            self._write(root / "r1", words=1_000, seconds=600, cost=0.80, mode="reflexive")

            reflexive = estimate_episode(2_000, "google/tts", root, generation_mode="reflexive")

        self.assertEqual(reflexive.sample_count, 1)
        # A dispersão de custo do histórico (0.40 vs 1.20 por 1000 palavras) é ampla,
        # então a faixa passa bem dos ±20% fixos anteriores.
        spread = (reflexive.cost_max_usd - reflexive.cost_min_usd) / (2 * reflexive.cost_usd)
        self.assertGreater(spread, 0.20)

    def test_sem_historico_do_tts_cai_para_a_faixa_padrao(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write(root / "r1", words=1_000, seconds=600, cost=0.80, mode="reflexive")

            reflexive = estimate_episode(2_000, "google/tts", root, generation_mode="reflexive")

        self.assertEqual(reflexive.sample_count, 1)
        self.assertAlmostEqual(reflexive.cost_min_usd, reflexive.cost_usd * 0.80, places=4)
        self.assertAlmostEqual(reflexive.cost_max_usd, reflexive.cost_usd * 1.20, places=4)
        self.assertAlmostEqual(
            reflexive.duration_min_minutes, reflexive.duration_minutes * 0.85, places=4
        )


if __name__ == "__main__":
    unittest.main()
