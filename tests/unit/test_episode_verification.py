"""Testes da recalibração local de episódios concluídos."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy.episode_verification import verify_episode  # noqa: E402
from audiofy.estimates import EpisodeMetrics, read_episode_metrics  # noqa: E402


class EpisodeVerificationTest(unittest.TestCase):
    @patch("audiofy.episode_verification.audit_segments")
    @patch("audiofy.episode_verification.media_duration_seconds", return_value=12.5)
    def test_recalcula_observavel_preserva_custo_e_documenta_fonte_ausente(
        self, _duration, audit_segments
    ):
        audit_segments.return_value = {
            "summary": {"segments": 1, "critical": 0, "warnings": 1, "ok": 0}
        }
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "episode.mp3").write_bytes(b"mp3")
            segments = directory / "segments"
            segments.mkdir()
            (segments / "001.wav").write_bytes(b"wav")
            (directory / "script.json").write_text(
                json.dumps({"turns": [{"text": "quatro palavras no roteiro"}]}),
                encoding="utf-8",
            )
            EpisodeMetrics(
                source_words=10,
                script_words=2,
                duration_seconds=9.0,
                cost_usd=1.23,
                cost_exact=False,
                tts_model="tts",
                profile_name="perfil",
                cost_source="reconstruido",
            ).write(directory)

            result = verify_episode(directory, verified_at="2026-07-19T00:00:00-03:00")
            metrics = read_episode_metrics(directory)

        self.assertEqual(metrics.script_words, 4)
        self.assertEqual(metrics.duration_seconds, 12.5)
        self.assertEqual(metrics.cost_usd, 1.23)
        self.assertEqual(metrics.verification_version, 1)
        self.assertEqual(result["checks"]["source_words"]["status"], "indisponivel")
        self.assertEqual(result["checks"]["cost"]["status"], "preservado")

    @patch("audiofy.episode_verification.audit_segments")
    @patch("audiofy.episode_verification.media_duration_seconds", return_value=20.0)
    def test_reconhece_leitura_fiel_e_atualiza_contagem_da_fonte(self, _duration, audit_segments):
        audit_segments.return_value = {
            "summary": {"segments": 1, "critical": 0, "warnings": 0, "ok": 1}
        }
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "episode.mp3").write_bytes(b"mp3")
            segments = directory / "segments"
            segments.mkdir()
            (segments / "001.wav").write_bytes(b"wav")
            (directory / "narration-script.json").write_text(
                json.dumps({"turns": [{"text": "texto integral"}]}), encoding="utf-8"
            )
            EpisodeMetrics(
                source_words=1,
                script_words=1,
                duration_seconds=1,
                cost_usd=0.5,
                cost_exact=True,
                tts_model="tts",
                profile_name="perfil",
            ).write(directory)

            result = verify_episode(directory, source_words=2)
            metrics = read_episode_metrics(directory)

        self.assertEqual(metrics.source_words, 2)
        self.assertEqual(metrics.generation_mode, "verbatim")
        self.assertFalse(result["checks"]["source_words"]["matches"])
        self.assertFalse(result["checks"]["generation_mode"]["matches"])


if __name__ == "__main__":
    unittest.main()
