"""Auditoria de silêncio e artefato consultado pelo revisor de chunks."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy.audio_audit import audit_segment, audit_segments, read_audio_audit  # noqa: E402


class AudioAuditTest(unittest.TestCase):
    @patch("audiofy.audio_audit.media_duration_seconds", return_value=30.0)
    @patch("audiofy.audio_audit.run_tool")
    def test_silencio_longo_vira_critico_com_intervalo_exato(self, run_tool, _duration):
        run_tool.return_value = SimpleNamespace(
            stderr=("silence_start: 10.0\nsilence_end: 16.5 | silence_duration: 6.5\n")
        )

        result = audit_segment(Path("006_narrador.wav"))

        self.assertEqual(result.severity, "critical")
        self.assertEqual(result.longest_silence_seconds, 6.5)
        self.assertEqual(result.silences[0].start_seconds, 10.0)
        self.assertAlmostEqual(result.silence_ratio, 6.5 / 30, places=4)
        self.assertIn("silencedetect=noise=-45dB:d=1.5", run_tool.call_args.args[1])
        self.assertFalse(run_tool.call_args.kwargs["check"])

    @patch("audiofy.audio_audit.audit_segment")
    def test_persiste_resumo_atomico_e_rele_documento(self, audit_segment_mock):
        from audiofy.audio_audit import SegmentAudioAudit

        audit_segment_mock.side_effect = [
            SegmentAudioAudit("001.wav", 10, 0, 0, 0, "ok", ()),
            SegmentAudioAudit("002.wav", 10, 6, 0.6, 6, "critical", ()),
        ]
        progress = []
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            document = audit_segments(
                directory,
                [directory / "001.wav", directory / "002.wav"],
                on_progress=progress.append,
            )
            persisted = json.loads((directory / "audio-audit.json").read_text())
            loaded = read_audio_audit(directory)

        self.assertEqual(progress, [1, 2])
        self.assertEqual(document["summary"]["critical"], 1)
        self.assertEqual(persisted["summary"], loaded["summary"])

    def test_documento_invalido_nao_e_exposto(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audio-audit.json"
            path.write_text("{}", encoding="utf-8")
            self.assertIsNone(read_audio_audit(path.parent))


if __name__ == "__main__":
    unittest.main()
