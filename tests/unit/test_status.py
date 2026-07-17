"""Testes do rastreador de geração: status.json, custo acumulado e abort."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy.runtime.status import GenerationAborted, GenerationTracker  # noqa: E402


class GenerationTrackerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self._tmp.name)
        self.tracker = GenerationTracker(self.directory, episode_id="ep-teste")

    def tearDown(self):
        self._tmp.cleanup()

    def _read(self) -> dict:
        return json.loads((self.directory / "status.json").read_text(encoding="utf-8"))

    def test_estado_inicial(self):
        self.tracker.stage("cobertura")
        data = self._read()
        self.assertEqual(data["episode_id"], "ep-teste")
        self.assertEqual(data["stage"], "cobertura")
        self.assertEqual(data["state"], "rodando")
        self.assertEqual(data["cost_usd"], 0.0)

    def test_progresso_e_custo(self):
        self.tracker.stage("tts", total=10)
        self.tracker.advance(3)
        self.tracker.add_cost(0.05)
        self.tracker.add_cost(0.02)
        data = self._read()
        self.assertEqual(data["progress"], {"current": 3, "total": 10})
        self.assertAlmostEqual(data["cost_usd"], 0.07)

    def test_finalizacao(self):
        self.tracker.stage("montagem")
        self.tracker.finish("concluido")
        self.assertEqual(self._read()["state"], "concluido")

    def test_abort_via_arquivo(self):
        self.tracker.stage("tts", total=5)
        (self.directory / "ABORT").touch()
        with self.assertRaises(GenerationAborted):
            self.tracker.checkpoint()
        self.assertEqual(self._read()["state"], "abortado")

    def test_checkpoint_sem_abort_passa(self):
        self.tracker.stage("tts", total=5)
        self.tracker.checkpoint()  # não deve levantar

    def test_load_de_outro_processo(self):
        self.tracker.stage("tts", total=5)
        self.tracker.advance(2)
        data = GenerationTracker.load(self.directory)
        self.assertEqual(data["progress"]["current"], 2)

    def test_load_sem_status(self):
        self.assertIsNone(GenerationTracker.load(Path(self._tmp.name) / "vazio"))


if __name__ == "__main__":
    unittest.main()
