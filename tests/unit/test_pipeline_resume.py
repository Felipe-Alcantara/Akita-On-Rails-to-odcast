"""Regressões da síntese retomável e idempotente por segmento."""

import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy.pipeline import _assemble, _synthesize_turns, _wait_for_retry  # noqa: E402
from audiofy.presenters import Presenter  # noqa: E402
from audiofy.providers.openrouter import OpenRouterError, SpeechResult  # noqa: E402
from audiofy.runtime.status import GenerationAborted, GenerationTracker  # noqa: E402


def _settings(max_attempts: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        presenters=[Presenter("ana", "Kore", "natural")],
        tts_model="vendor/tts",
        tts_format="pcm",
        tts_sample_rate=24_000,
        tts_retry_attempts=max_attempts,
        tts_retry_base_seconds=0,
        tts_retry_max_seconds=0,
    )


def _valid_wav(path: Path) -> bytes:
    pcm = b"\x00\x00" * 300
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24_000)
        audio.writeframes(pcm)
    return pcm


class ResumableSynthesisTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self._tmp.name)
        self.tracker = GenerationTracker(self.directory, "episodio")

    def tearDown(self):
        self._tmp.cleanup()

    @patch("audiofy.pipeline.openrouter.generation_cost_usd", return_value=0.012)
    @patch("audiofy.pipeline.openrouter.text_to_speech")
    def test_retomada_pula_segmento_pronto_e_repete_apenas_o_que_falhou(
        self, text_to_speech, _generation_cost
    ):
        segments = self.directory / "segments"
        segments.mkdir()
        first = segments / "001_ana.wav"
        _valid_wav(first)
        original = first.read_bytes()
        text_to_speech.side_effect = [
            OpenRouterError("Provider returned 400", retryable=True),
            SpeechResult(b"\x00\x00" * 300, "gen-2"),
        ]

        paths = _synthesize_turns(
            _settings(), self.directory,
            [{"speaker": "ana", "text": "já pronto"},
             {"speaker": "ana", "text": "retomar daqui"}],
            self.tracker,
        )

        self.assertEqual(text_to_speech.call_count, 2)
        self.assertEqual(first.read_bytes(), original)
        self.assertTrue(paths[1].is_file())
        status = GenerationTracker.load(self.directory)
        self.assertEqual(status["progress"], {"current": 2, "total": 2})
        self.assertIsNone(status["retry"])
        manifest = json.loads((self.directory / "segments.json").read_text(encoding="utf-8"))
        self.assertEqual(set(manifest["segments"]), {"001_ana.wav", "002_ana.wav"})
        self.assertEqual(manifest["segments"]["002_ana.wav"]["generation_id"], "gen-2")
        self.assertEqual(manifest["segments"]["002_ana.wav"]["cost_usd"], 0.012)
        self.assertEqual(status["cost_usd"], 0.012)

    @patch("audiofy.pipeline.openrouter.generation_cost_usd")
    @patch("audiofy.pipeline.openrouter.text_to_speech")
    def test_limite_de_tentativas_preserva_o_ultimo_checkpoint(
        self, text_to_speech, _generation_cost
    ):
        segments = self.directory / "segments"
        segments.mkdir()
        _valid_wav(segments / "001_ana.wav")
        text_to_speech.side_effect = OpenRouterError("indisponível", retryable=True)

        with self.assertRaisesRegex(OpenRouterError, "indisponível"):
            _synthesize_turns(
                _settings(max_attempts=2), self.directory,
                [{"speaker": "ana", "text": "preservado"},
                 {"speaker": "ana", "text": "falha"}],
                self.tracker,
            )

        self.assertEqual(text_to_speech.call_count, 2)
        self.assertTrue((segments / "001_ana.wav").is_file())
        self.assertFalse((segments / "002_ana.wav").exists())
        self.assertFalse((segments / "002_ana.wav.tmp").exists())
        status = GenerationTracker.load(self.directory)
        self.assertEqual(status["progress"], {"current": 1, "total": 2})

    @patch("audiofy.pipeline.openrouter.generation_cost_usd")
    @patch("audiofy.pipeline.openrouter.text_to_speech")
    def test_erro_permanente_nao_e_repetido(self, text_to_speech, _generation_cost):
        text_to_speech.side_effect = OpenRouterError("chave inválida", retryable=False)

        with self.assertRaisesRegex(OpenRouterError, "chave inválida"):
            _synthesize_turns(
                _settings(max_attempts=5), self.directory,
                [{"speaker": "ana", "text": "fala"}], self.tracker,
            )

        text_to_speech.assert_called_once()

    @patch("audiofy.pipeline.openrouter.generation_cost_usd", return_value=0.01)
    @patch("audiofy.pipeline.openrouter.text_to_speech",
           return_value=SpeechResult(b"\x00\x00" * 300, "gen-1"))
    def test_manifesto_invalida_audio_quando_modelo_muda(
        self, text_to_speech, _generation_cost
    ):
        turns = [{"speaker": "ana", "text": "mesma fala"}]
        first_settings = _settings()
        _synthesize_turns(first_settings, self.directory, turns, self.tracker)
        original_calls = text_to_speech.call_count

        changed_settings = _settings()
        changed_settings.tts_model = "vendor/tts-novo"
        resumed = GenerationTracker(self.directory, "episodio")
        _synthesize_turns(changed_settings, self.directory, turns, resumed)

        self.assertEqual(text_to_speech.call_count, original_calls + 1)

    @patch("audiofy.pipeline.estimate_tts_cost", return_value=0.02)
    @patch("audiofy.pipeline.openrouter.generation_cost_usd",
           side_effect=OpenRouterError("metadado atrasado"))
    @patch("audiofy.pipeline.openrouter.text_to_speech",
           return_value=SpeechResult(b"\x00\x00" * 300, "gen-atrasada"))
    def test_fallback_local_nao_consulta_conta_global_e_marca_aproximacao(
        self, _text_to_speech, _generation_cost, estimate_cost
    ):
        _synthesize_turns(
            _settings(), self.directory,
            [{"speaker": "ana", "text": "fala"}], self.tracker,
        )

        status = GenerationTracker.load(self.directory)
        manifest = json.loads((self.directory / "segments.json").read_text(encoding="utf-8"))
        entry = manifest["segments"]["001_ana.wav"]
        self.assertEqual(status["cost_usd"], 0.02)
        self.assertFalse(status["cost_exact"])
        self.assertFalse(entry["cost_exact"])
        estimate_cost.assert_called_once()

    def test_abort_interrompe_espera_antes_do_proximo_retry(self):
        self.tracker.stage("tts", total=2, current=1)
        GenerationTracker.request_abort(self.directory)

        with self.assertRaises(GenerationAborted):
            _wait_for_retry(30, self.tracker)

        self.assertEqual(GenerationTracker.load(self.directory)["state"], "abortado")


class AtomicAssemblyTest(unittest.TestCase):
    @patch("audiofy.pipeline.subprocess.run")
    def test_mp3_so_substitui_final_depois_do_ffmpeg(self, run):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            segment = directory / "001.wav"
            _valid_wav(segment)
            old = directory / "episode.mp3"
            old.write_bytes(b"versao-anterior")

            def create_output(arguments, **_kwargs):
                self.assertEqual(old.read_bytes(), b"versao-anterior")
                Path(arguments[-1]).write_bytes(b"versao-nova")

            run.side_effect = create_output
            result = _assemble(
                directory, [segment],
                SimpleNamespace(title="Episódio", attribution="Fonte"),
            )

            self.assertEqual(result, old)
            self.assertEqual(old.read_bytes(), b"versao-nova")
            self.assertFalse((directory / "episode.tmp.mp3").exists())


if __name__ == "__main__":
    unittest.main()
