"""Testes do reparo seletivo de segmentos com silêncio problemático."""

import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy.artifacts import final_audio_filename, segment_audio_filename  # noqa: E402
from audiofy.audio_audit import AUDIT_FILE  # noqa: E402
from audiofy.pipeline import _segment_fingerprint, repair_episode  # noqa: E402
from audiofy.presenters import Presenter  # noqa: E402
from audiofy.providers.openrouter import SpeechResult  # noqa: E402
from audiofy.runtime.status import GenerationTracker  # noqa: E402
from audiofy.sources.base import ContentItem  # noqa: E402


def _settings():
    return SimpleNamespace(
        presenters=[Presenter("ana", "Kore", "natural")],
        tts_model="vendor/tts",
        tts_format="pcm",
        tts_sample_rate=24_000,
        tts_retry_attempts=2,
        tts_retry_base_seconds=0,
        tts_retry_max_seconds=0,
    )


def _valid_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = b"\x00\x00" * 300
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24_000)
        audio.writeframes(pcm)


def _item(item_id: str = "ep-001") -> ContentItem:
    return ContentItem(
        item_id=item_id,
        title="Teste de reparo",
        url="",
        published_at="2026-01-01",
        text="Conteúdo original do teste.",
        words=5,
        attribution="teste",
    )


def _segment_name(directory: Path, index: int, total: int) -> str:
    return segment_audio_filename(
        "conteudo", directory.name.replace("__", "/"), "adaptation", index, total, "ana", "wav"
    )


def _setup_episode(directory: Path, total: int = 3, bad_indices: tuple = (2,)):
    """Prepara um episódio com script, segments.json, audio-audit.json e WAVs."""
    settings = _settings()
    segments_dir = directory / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)

    # Script
    turns = [{"speaker": "ana", "text": f"Turno {i}."} for i in range(1, total + 1)]
    (directory / "script.json").write_text(
        json.dumps({"turns": turns}, ensure_ascii=False), encoding="utf-8"
    )

    # Segments.json e WAVs
    manifest = {"version": 2, "source_key": "conteudo", "segments": {}}
    audit_segments = []
    for i in range(1, total + 1):
        name = _segment_name(directory, i, total)
        wav_path = segments_dir / name
        _valid_wav(wav_path)
        # Fingerprint real para que o cache funcione corretamente
        instructions = "Fala natural de podcast em português brasileiro, tom natural."
        fp = _segment_fingerprint(settings, f"Turno {i}.", "Kore", instructions)
        manifest["segments"][name] = {
            "fingerprint": fp,
            "bytes": wav_path.stat().st_size,
            "kind": "chunk",
            "chunk_index": i,
            "chunk_total": total,
            "speaker": "ana",
        }
        severity = "critical" if i in bad_indices else "ok"
        audit_segments.append({
            "file": name,
            "duration_seconds": 5.0,
            "silence_seconds": 5.0 if severity != "ok" else 0.0,
            "silence_ratio": 1.0 if severity != "ok" else 0.0,
            "longest_silence_seconds": 5.0 if severity != "ok" else 0.0,
            "severity": severity,
            "silences": [],
        })

    (directory / "segments.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )

    # Audio audit
    bad_count = len(bad_indices)
    audit = {
        "version": 1,
        "summary": {
            "segments": total,
            "ok": total - bad_count,
            "warnings": 0,
            "critical": bad_count,
        },
        "segments": audit_segments,
    }
    (directory / AUDIT_FILE).write_text(
        json.dumps(audit, ensure_ascii=False), encoding="utf-8"
    )

    # MP3 final (dummy)
    final_name = final_audio_filename("conteudo", directory.name.replace("__", "/"), "adaptation")
    (directory / final_name).write_bytes(b"\xff\xfb\x90\x00" * 100)

    # Status anterior (simula geração concluída)
    GenerationTracker.mark_starting(directory, directory.name.replace("__", "/"), resume=True)
    tracker = GenerationTracker(directory, directory.name.replace("__", "/"))
    tracker.finish("concluido")


class RepairEpisodeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self._tmp.name) / "ep-001"
        self.directory.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    @patch("audiofy.pipeline.openrouter.generation_cost_usd", return_value=0.01)
    @patch("audiofy.pipeline.openrouter.text_to_speech")
    @patch("audiofy.pipeline.audit_segments")
    @patch("audiofy.pipeline._assemble")
    @patch("audiofy.pipeline.episode_dir")
    def test_repair_regenera_somente_segmentos_bugados(
        self, episode_dir_mock, assemble_mock, audit_mock, tts_mock, _cost_mock
    ):
        _setup_episode(self.directory, total=3, bad_indices=(2,))
        episode_dir_mock.return_value = self.directory
        tts_mock.return_value = SpeechResult(b"\x00\x00" * 300, "gen-repair")
        final_path = self.directory / "repaired.mp3"
        assemble_mock.return_value = final_path
        final_path.write_bytes(b"\xff\xfb\x90\x00" * 50)
        audit_mock.return_value = {
            "version": 1,
            "summary": {"segments": 3, "ok": 3, "warnings": 0, "critical": 0},
            "segments": [],
        }

        result = repair_episode(
            _settings(), _item("ep-001"), source_key="conteudo"
        )

        # TTS chamado apenas 1 vez (o segmento 2 que era critical)
        self.assertEqual(tts_mock.call_count, 1)
        self.assertEqual(result, final_path)

    @patch("audiofy.pipeline.episode_dir")
    def test_repair_sem_auditoria_falha(self, episode_dir_mock):
        self.directory.mkdir(exist_ok=True)
        episode_dir_mock.return_value = self.directory

        with self.assertRaises(FileNotFoundError):
            repair_episode(_settings(), _item("ep-001"))

    @patch("audiofy.pipeline.episode_dir")
    def test_repair_sem_problemas_retorna_mp3_existente(self, episode_dir_mock):
        _setup_episode(self.directory, total=3, bad_indices=())
        episode_dir_mock.return_value = self.directory

        result = repair_episode(
            _settings(), _item("ep-001"), source_key="conteudo"
        )

        # Retorna o MP3 existente sem chamar TTS
        self.assertTrue(result.is_file())

    @patch("audiofy.pipeline.openrouter.generation_cost_usd", return_value=0.01)
    @patch("audiofy.pipeline.openrouter.text_to_speech")
    @patch("audiofy.pipeline.audit_segments")
    @patch("audiofy.pipeline._assemble")
    @patch("audiofy.pipeline.episode_dir")
    def test_repair_preserva_segmentos_bons(
        self, episode_dir_mock, assemble_mock, audit_mock, tts_mock, _cost_mock
    ):
        _setup_episode(self.directory, total=5, bad_indices=(2, 4))
        episode_dir_mock.return_value = self.directory
        tts_mock.return_value = SpeechResult(b"\x00\x00" * 300, "gen-fix")
        final_path = self.directory / "repaired.mp3"
        assemble_mock.return_value = final_path
        final_path.write_bytes(b"\xff\xfb\x90\x00" * 50)
        audit_mock.return_value = {
            "version": 1,
            "summary": {"segments": 5, "ok": 5, "warnings": 0, "critical": 0},
            "segments": [],
        }

        repair_episode(_settings(), _item("ep-001"), source_key="conteudo")

        # Somente 2 segmentos regenerados (indices 2 e 4)
        self.assertEqual(tts_mock.call_count, 2)


if __name__ == "__main__":
    unittest.main()
