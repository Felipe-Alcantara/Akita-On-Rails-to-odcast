"""Normalização de volume por segmento: medição, limiar e aplicação."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy.volume_norm import (  # noqa: E402
    LoudnessInfo,
    _parse_loudnorm_json,
    measure_loudness,
    normalize_segments,
)

_FFMPEG_JSON_OUTPUT = """
[Parsed_loudnorm_0 @ 0x55f0c0]
{
\t"input_i" : "-25.01",
\t"input_tp" : "-8.54",
\t"input_lra" : "4.66",
\t"input_thresh" : "-35.24",
\t"output_i" : "-16.00",
\t"output_tp" : "-1.50",
\t"output_lra" : "3.35",
\t"output_thresh" : "-26.23",
\t"normalization_type" : "dynamic",
\t"target_offset" : "0.00"
}
"""


class ParseLoudnormJsonTest(unittest.TestCase):
    def test_extrai_medicao_do_stderr_do_ffmpeg(self):
        info = _parse_loudnorm_json(_FFMPEG_JSON_OUTPUT)
        self.assertIsNotNone(info)
        self.assertAlmostEqual(info.integrated_lufs, -25.01)
        self.assertAlmostEqual(info.true_peak_dbfs, -8.54)
        self.assertAlmostEqual(info.lra, 4.66)
        self.assertAlmostEqual(info.threshold_lufs, -35.24)

    def test_retorna_none_sem_json_no_stderr(self):
        self.assertIsNone(_parse_loudnorm_json("sem json aqui"))

    def test_retorna_none_com_json_incompleto(self):
        self.assertIsNone(_parse_loudnorm_json('{"input_i": "-20"}'))


class MeasureLoudnessTest(unittest.TestCase):
    @patch("audiofy.volume_norm.run_tool")
    def test_chama_ffmpeg_com_loudnorm_print_format(self, run_tool):
        run_tool.return_value = SimpleNamespace(stderr=_FFMPEG_JSON_OUTPUT)

        info = measure_loudness(Path("chunk.wav"))

        self.assertIsNotNone(info)
        self.assertAlmostEqual(info.integrated_lufs, -25.01)
        args = run_tool.call_args.args[1]
        self.assertIn("loudnorm", " ".join(args))
        self.assertIn("print_format=json", " ".join(args))

    @patch("audiofy.volume_norm.run_tool")
    def test_retorna_none_quando_ffmpeg_nao_produz_json(self, run_tool):
        run_tool.return_value = SimpleNamespace(stderr="erro qualquer")
        self.assertIsNone(measure_loudness(Path("chunk.wav")))


class NormalizeSegmentsTest(unittest.TestCase):
    @patch("audiofy.volume_norm._apply_loudnorm")
    @patch("audiofy.volume_norm.measure_loudness")
    @patch("audiofy.volume_norm.media_duration_seconds", return_value=5.0)
    def test_normaliza_chunk_abaixo_do_limiar(self, _dur, measure, apply):
        measure.return_value = LoudnessInfo(-25.0, -8.0, 4.0, -35.0)
        progress = []

        results = normalize_segments(
            [Path("001.wav")],
            target_lufs=-16.0,
            threshold_lufs=3.0,
            on_progress=progress.append,
        )

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].normalized)
        self.assertEqual(results[0].reason, "normalized")
        self.assertAlmostEqual(results[0].original_lufs, -25.0)
        apply.assert_called_once()
        self.assertEqual(progress, [1])

    @patch("audiofy.volume_norm._apply_loudnorm")
    @patch("audiofy.volume_norm.measure_loudness")
    @patch("audiofy.volume_norm.media_duration_seconds", return_value=5.0)
    def test_nao_normaliza_chunk_proximo_do_alvo(self, _dur, measure, apply):
        measure.return_value = LoudnessInfo(-17.0, -3.0, 5.0, -27.0)

        results = normalize_segments(
            [Path("001.wav")],
            target_lufs=-16.0,
            threshold_lufs=3.0,
        )

        self.assertFalse(results[0].normalized)
        self.assertEqual(results[0].reason, "ok")
        apply.assert_not_called()

    @patch("audiofy.volume_norm.measure_loudness")
    @patch("audiofy.volume_norm.media_duration_seconds", return_value=0.2)
    def test_pula_chunk_muito_curto(self, _dur, measure):
        results = normalize_segments([Path("001.wav")])

        self.assertFalse(results[0].normalized)
        self.assertEqual(results[0].reason, "too_short")
        measure.assert_not_called()

    @patch("audiofy.volume_norm._apply_loudnorm")
    @patch("audiofy.volume_norm.measure_loudness")
    @patch("audiofy.volume_norm.media_duration_seconds", return_value=5.0)
    def test_lote_misto_normaliza_somente_os_baixos(self, _dur, measure, apply):
        measure.side_effect = [
            LoudnessInfo(-15.5, -2.0, 5.0, -25.0),  # próximo do alvo
            LoudnessInfo(-28.0, -10.0, 3.0, -38.0),  # muito baixo
            LoudnessInfo(-17.0, -4.0, 6.0, -27.0),  # aceitável
        ]

        results = normalize_segments(
            [Path("001.wav"), Path("002.wav"), Path("003.wav")],
            target_lufs=-16.0,
            threshold_lufs=3.0,
        )

        normalized = [r for r in results if r.normalized]
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0].file, "002.wav")
        apply.assert_called_once()

    @patch("audiofy.volume_norm.measure_loudness", return_value=None)
    @patch("audiofy.volume_norm.media_duration_seconds", return_value=5.0)
    def test_falha_de_medicao_nao_interrompe_o_lote(self, _dur, _measure):
        results = normalize_segments([Path("001.wav")])

        self.assertFalse(results[0].normalized)
        self.assertEqual(results[0].reason, "measurement_failed")


if __name__ == "__main__":
    unittest.main()
