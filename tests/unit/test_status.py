"""Testes do rastreador de geração: status.json, custo acumulado e abort."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_escrita_substitui_status_existente_sem_tmp_fixo(self):
        self.tracker.stage("tts", total=2)
        self.tracker.advance(1)

        self.assertEqual(self._read()["progress"]["current"], 1)
        self.assertFalse((self.directory / "status.json.tmp").exists())
        self.assertEqual(list(self.directory.glob(".status.json.*.tmp")), [])

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
            segment=3,
            next_attempt=2,
            max_attempts=5,
            delay_seconds=4,
            error="falha temporária",
        )
        retry = self._read()["retry"]
        self.assertEqual(retry["segment"], 3)
        self.assertEqual(retry["attempt"], 2)
        self.assertEqual(retry["max_attempts"], 5)

        self.tracker.advance(3)
        self.assertIsNone(self._read()["retry"])

    def test_origem_da_chave_e_persistida_e_atualizada_sem_segredo(self):
        tracker = GenerationTracker(
            self.directory,
            episode_id="ep-teste",
            key_source="ambiente",
        )
        self.assertEqual(self._read()["key_source"], "ambiente")

        tracker.using_key("trabalho")

        self.assertEqual(self._read()["key_source"], "trabalho")
        self.assertNotIn("sk-or-", self._read()["key_source"])

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

        GenerationTracker.mark_starting(self.directory, "ep-teste", key_source="ambiente")
        data = self._read()

        self.assertEqual(data["state"], "rodando")
        self.assertEqual(data["stage"], "iniciando")
        self.assertEqual(data["progress"], {"current": 66, "total": 92})
        self.assertEqual(data["cost_usd"], 0.85)
        self.assertIsNone(data["last_error"])
        self.assertEqual(data["key_source"], "ambiente")

    def test_abort_pedido_durante_inicializacao_chega_ao_worker(self):
        self.tracker.finish("falhou")
        GenerationTracker.mark_starting(self.directory, "ep-teste")
        GenerationTracker.request_abort(self.directory)

        worker = GenerationTracker(self.directory, "ep-teste")
        with self.assertRaises(GenerationAborted):
            worker.checkpoint()

        self.assertEqual(self._read()["state"], "abortado")

    def test_abort_ativo_encerra_worker_e_marca_estado_final(self):
        self.tracker.stage("tts", total=5, current=2)

        with patch("audiofy.runtime.process.terminate_process", return_value=True) as terminate:
            accepted, stopped = GenerationTracker.abort_running(self.directory)

        self.assertTrue(accepted)
        self.assertTrue(stopped)
        terminate.assert_called_once_with(
            self._read()["pid"],
            expected_fragments=("audiofy.bridge", "run-generation", "ep-teste"),
        )
        self.assertEqual(self._read()["state"], "abortado")
        self.assertFalse(self._read()["cost_exact"])
        self.assertFalse((self.directory / "ABORT").exists())

    def test_abort_mantem_fallback_cooperativo_se_worker_nao_pode_ser_encerrado(self):
        self.tracker.stage("tts", total=5, current=2)

        with patch("audiofy.runtime.process.terminate_process", return_value=False):
            accepted, stopped = GenerationTracker.abort_running(self.directory)

        data = self._read()
        self.assertTrue(accepted)
        self.assertFalse(stopped)
        self.assertEqual(data["state"], "rodando")
        self.assertIsNotNone(data["abort_requested_at"])
        self.assertTrue((self.directory / "ABORT").is_file())


class ReconcileTest(unittest.TestCase):
    """Um 'rodando' cujo worker morreu não pode ficar pendurado na interface."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_status(self, **overrides):
        import time

        data = {
            "episode_id": "ep",
            "pid": None,
            "state": "rodando",
            "stage": "iniciando",
            "progress": {"current": 0, "total": 0},
            "cost_usd": 0.0,
            "cost_exact": True,
            "started_at": time.time(),
            "run_started_at": time.time(),
            "updated_at": time.time(),
            "resume_count": 0,
            "retry": None,
            "last_error": None,
        }
        data.update(overrides)
        (self.directory / "status.json").write_text(json.dumps(data), encoding="utf-8")
        return data

    def test_worker_morto_vira_falhou(self):
        with patch("audiofy.runtime.process.pid_alive", return_value=False):
            self._write_status(pid=99999, stage="tts")
            data = GenerationTracker.reconcile(self.directory)
        self.assertEqual(data["state"], "falhou")
        self.assertIn("generation.log", data["last_error"])
        self.assertEqual(GenerationTracker.load(self.directory)["state"], "falhou")

    def test_worker_vivo_permanece_rodando(self):
        with patch("audiofy.runtime.process.pid_alive", return_value=True):
            self._write_status(pid=1234, stage="tts")
            data = GenerationTracker.reconcile(self.directory)
        self.assertEqual(data["state"], "rodando")

    def test_iniciando_ha_muito_tempo_sem_pid_vira_falhou(self):
        self._write_status(pid=None, stage="iniciando", run_started_at=1.0)  # passado distante
        data = GenerationTracker.reconcile(self.directory)
        self.assertEqual(data["state"], "falhou")
        self.assertIn("não iniciou", data["last_error"])

    def test_iniciando_recente_e_tolerado(self):
        self._write_status(pid=None, stage="iniciando")
        data = GenerationTracker.reconcile(self.directory)
        self.assertEqual(data["state"], "rodando")

    def test_estados_finais_nao_sao_tocados(self):
        self._write_status(state="concluido", pid=99999)
        data = GenerationTracker.reconcile(self.directory)
        self.assertEqual(data["state"], "concluido")

    def test_sem_status_retorna_none(self):
        self.assertIsNone(GenerationTracker.reconcile(self.directory))


if __name__ == "__main__":
    unittest.main()
