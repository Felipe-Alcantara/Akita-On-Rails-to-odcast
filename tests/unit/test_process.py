"""Testes da execução portátil de processos (Windows vs POSIX, timeouts, PATH)."""

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy.runtime import process  # noqa: E402
from audiofy.runtime.process import (  # noqa: E402
    ToolNotFoundError,
    detached_flags,
    launch_detached,
    pid_alive,
    process_command,
    resolve_tool,
    run_tool,
    terminate_process,
)


class DetachedFlagsTest(unittest.TestCase):
    def test_windows_usa_creationflags_sem_start_new_session(self):
        with (
            patch.object(process.sys, "platform", "win32"),
            patch.object(process.subprocess, "DETACHED_PROCESS", 8, create=True),
            patch.object(process.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, create=True),
        ):
            flags = detached_flags()
        self.assertNotIn("start_new_session", flags)
        self.assertEqual(flags["creationflags"], 8 | 512)

    def test_posix_usa_start_new_session(self):
        with patch.object(process.sys, "platform", "linux"):
            self.assertEqual(detached_flags(), {"start_new_session": True})


class ResolveToolTest(unittest.TestCase):
    def test_resolve_retorna_caminho_absoluto(self):
        with patch.object(process.shutil, "which", return_value="/usr/bin/ffmpeg"):
            self.assertEqual(resolve_tool("ffmpeg"), "/usr/bin/ffmpeg")

    def test_ferramenta_ausente_gera_erro_claro(self):
        with patch.object(process.shutil, "which", return_value=None):
            with self.assertRaises(ToolNotFoundError) as ctx:
                resolve_tool("ffmpeg")
        self.assertIn("ffmpeg", str(ctx.exception))
        self.assertIn("PATH", str(ctx.exception))


class RunToolTest(unittest.TestCase):
    def test_run_tool_sempre_passa_timeout(self):
        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(command, 0, "", "")

        with (
            patch.object(process.shutil, "which", return_value="/usr/bin/ffprobe"),
            patch.object(process.subprocess, "run", side_effect=fake_run),
        ):
            run_tool("ffprobe", ["-version"], timeout=30)
        self.assertEqual(captured["command"][0], "/usr/bin/ffprobe")
        self.assertEqual(captured["kwargs"]["timeout"], 30)
        self.assertTrue(captured["kwargs"]["check"])

    def test_run_tool_ferramenta_ausente_nao_chama_subprocess(self):
        with (
            patch.object(process.shutil, "which", return_value=None),
            patch.object(process.subprocess, "run") as run,
        ):
            with self.assertRaises(ToolNotFoundError):
                run_tool("ffmpeg", [], timeout=30)
        run.assert_not_called()


class PidAliveTest(unittest.TestCase):
    def test_processo_atual_esta_vivo(self):
        import os

        self.assertTrue(pid_alive(os.getpid()))

    def test_pid_inexistente_esta_morto(self):
        # PIDs muito altos não existem em máquinas normais; se existir, o teste
        # usa um processo encerrado de verdade para garantir determinismo.
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        self.assertFalse(pid_alive(dead.pid))

    def test_pid_invalido_e_morto_sem_excecao(self):
        self.assertFalse(pid_alive(0))
        self.assertFalse(pid_alive(-1))
        self.assertFalse(pid_alive(None))


class TerminateProcessTest(unittest.TestCase):
    def test_posix_encerra_o_grupo_do_worker_e_confirma(self):
        with (
            patch.object(process.sys, "platform", "linux"),
            patch.object(process.os, "getpid", return_value=10),
            patch.object(process.os, "getpgid", return_value=20),
            patch.object(process.os, "getpgrp", return_value=10),
            patch.object(process, "pid_alive", side_effect=[True, False]),
            patch.object(process.os, "killpg") as kill_group,
        ):
            self.assertTrue(terminate_process(20, grace_seconds=0))
        kill_group.assert_called_once_with(20, process.signal.SIGTERM)

    def test_nunca_encerra_o_proprio_processo(self):
        with (
            patch.object(process.os, "getpid", return_value=20),
            patch.object(process.os, "kill") as kill,
        ):
            self.assertFalse(terminate_process(20))
        kill.assert_not_called()

    def test_pid_que_ja_terminou_e_considerado_cancelado(self):
        with (
            patch.object(process.os, "getpid", return_value=10),
            patch.object(process, "pid_alive", return_value=False),
            patch.object(process.os, "kill") as kill,
        ):
            self.assertTrue(terminate_process(20))
        kill.assert_not_called()

    def test_windows_encerra_a_arvore_com_taskkill(self):
        completed = subprocess.CompletedProcess([], 0, "", "")
        with (
            patch.object(process.sys, "platform", "win32"),
            patch.object(process.os, "getpid", return_value=10),
            patch.object(process, "pid_alive", side_effect=[True, False]),
            patch.object(process.subprocess, "run", return_value=completed) as run,
        ):
            self.assertTrue(terminate_process(20))
        self.assertEqual(run.call_args.args[0], ["taskkill", "/PID", "20", "/T", "/F"])

    def test_recusa_pid_cujo_comando_nao_e_o_worker_esperado(self):
        with (
            patch.object(process.os, "getpid", return_value=10),
            patch.object(process, "pid_alive", return_value=True),
            patch.object(process, "process_command", return_value="python outro-programa"),
            patch.object(process.os, "kill") as kill,
        ):
            stopped = terminate_process(20, expected_fragments=("audiofy.bridge", "episodio"))
        self.assertFalse(stopped)
        kill.assert_not_called()

    def test_le_comando_do_processo_atual(self):
        import os

        command = process_command(os.getpid())
        self.assertIsNotNone(command)
        self.assertIn("python", command.lower())


class LaunchDetachedTest(unittest.TestCase):
    def _launch(self, platform, log_handle=None):
        captured = {}

        def fake_popen(args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return object()

        with (
            patch.object(process.sys, "platform", platform),
            patch.object(process.subprocess, "DETACHED_PROCESS", 8, create=True),
            patch.object(process.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, create=True),
            patch.object(process.subprocess, "Popen", side_effect=fake_popen),
        ):
            launch_detached(
                ["python", "-m", "x"], cwd="/tmp", env={"A": "B"}, log_handle=log_handle
            )
        return captured

    def test_windows_desanexa_com_creationflags(self):
        captured = self._launch("win32")
        self.assertIn("creationflags", captured["kwargs"])
        self.assertNotIn("start_new_session", captured["kwargs"])

    def test_posix_desanexa_com_start_new_session(self):
        captured = self._launch("linux")
        self.assertTrue(captured["kwargs"]["start_new_session"])

    def test_sem_log_descarta_saida(self):
        captured = self._launch("linux")
        self.assertEqual(captured["kwargs"]["stdout"], subprocess.DEVNULL)
        self.assertEqual(captured["kwargs"]["stderr"], subprocess.DEVNULL)

    def test_com_log_redireciona_stderr_para_stdout(self):
        sentinel = object()
        captured = self._launch("linux", log_handle=sentinel)
        self.assertIs(captured["kwargs"]["stdout"], sentinel)
        self.assertEqual(captured["kwargs"]["stderr"], subprocess.STDOUT)


if __name__ == "__main__":
    unittest.main()
