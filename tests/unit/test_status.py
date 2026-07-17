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
        self.assertTrue(data["cost_exact"])

    def test_fallback_de_preco_marca_total_como_aproximado(self):
        self.tracker.add_cost(0.03, exact=False)

        data = self._read()

        self.assertEqual(data["cost_usd"], 0.03)
        self.assertFalse(data["cost_exact"])

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

    def test_nova_execucao_preserva_custo_e_registra_retomada(self):
        self.tracker.stage("tts", total=5)
        self.tracker.advance(2)
        self.tracker.add_cost(0.35)

        resumed = GenerationTracker(self.directory, episode_id="ep-teste")
        resumed.stage("tts", total=5, current=2)
        data = self._read()

        self.assertEqual(data["cost_usd"], 0.35)
        self.assertEqual(data["resume_count"], 1)
        self.assertEqual(data["progress"], {"current": 2, "total": 5})

    def test_status_de_retry_e_limpo_ao_avancar(self):
        self.tracker.stage("tts", total=5, current=2)
        self.tracker.retrying(
            segment=3, next_attempt=2, max_attempts=5,
            delay_seconds=4, error="falha temporária",
        )
        retry = self._read()["retry"]
        self.assertEqual(retry["segment"], 3)
        self.assertEqual(retry["attempt"], 2)
        self.assertEqual(retry["max_attempts"], 5)

        self.tracker.advance(3)
        self.assertIsNone(self._read()["retry"])

    def test_execucao_forcada_inicia_novo_custo(self):
        self.tracker.stage("tts", total=2)
        self.tracker.add_cost(0.35)

        fresh = GenerationTracker(self.directory, episode_id="ep-teste", resume=False)
        fresh.stage("cobertura")
        data = self._read()

        self.assertEqual(data["cost_usd"], 0.0)
        self.assertEqual(data["resume_count"], 0)

    def test_marca_inicio_antes_do_worker_preservando_checkpoint(self):
        self.tracker.stage("tts", total=92)
        self.tracker.advance(66)
        self.tracker.add_cost(0.85)
        self.tracker.finish("falhou", error="erro anterior")

        GenerationTracker.mark_starting(self.directory, "ep-teste")
        data = self._read()

        self.assertEqual(data["state"], "rodando")
        self.assertEqual(data["stage"], "iniciando")
        self.assertEqual(data["progress"], {"current": 66, "total": 92})
        self.assertEqual(data["cost_usd"], 0.85)
        self.assertIsNone(data["last_error"])

    def test_abort_pedido_durante_inicializacao_chega_ao_worker(self):
        self.tracker.finish("falhou")
        GenerationTracker.mark_starting(self.directory, "ep-teste")
        GenerationTracker.request_abort(self.directory)

        worker = GenerationTracker(self.directory, "ep-teste")
        with self.assertRaises(GenerationAborted):
            worker.checkpoint()

        self.assertEqual(self._read()["state"], "abortado")


if __name__ == "__main__":
    unittest.main()
