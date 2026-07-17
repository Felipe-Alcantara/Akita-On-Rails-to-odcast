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
    resolve_tool,
    run_tool,
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
            launch_detached(["python", "-m", "x"], cwd="/tmp", env={"A": "B"},
                            log_handle=log_handle)
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
