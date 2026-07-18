"""Testes do lançamento do app desktop pela porta de entrada."""

import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import start_app  # noqa: E402
from audiofy import setup  # noqa: E402

_WHICH = {"npm": "C:/nodejs/npm.cmd", "node": "C:/nodejs/node.exe"}


class NpmCommandTest(unittest.TestCase):
    def test_windows_prefere_node_com_npm_cli(self):
        with (
            patch.object(setup.shutil, "which", side_effect=_WHICH.get),
            patch.object(setup.sys, "platform", "win32"),
            patch.object(Path, "is_file", return_value=True),
        ):
            command = start_app._npm_command()
        self.assertEqual(command[0], "C:/nodejs/node.exe")
        self.assertTrue(command[1].endswith("npm-cli.js"))

    def test_windows_sem_npm_cli_usa_caminho_completo_do_npm(self):
        with (
            patch.object(setup.shutil, "which", side_effect=_WHICH.get),
            patch.object(setup.sys, "platform", "win32"),
            patch.object(Path, "is_file", return_value=False),
        ):
            self.assertEqual(start_app._npm_command(), ["C:/nodejs/npm.cmd"])

    def test_posix_usa_npm_do_path(self):
        with (
            patch.object(setup.shutil, "which", side_effect={"npm": "/usr/bin/npm"}.get),
            patch.object(setup.sys, "platform", "linux"),
        ):
            self.assertEqual(start_app._npm_command(), ["/usr/bin/npm"])


class DesktopLaunchTest(unittest.TestCase):
    def _launch(self, platform: str, electron: Path | None) -> dict:
        """Executa do_desktop com dependências simuladas e retorna a chamada do Popen."""
        calls = {}

        def popen(command, **kwargs):
            calls["command"] = command
            calls["kwargs"] = kwargs

        with (
            patch.object(start_app, "_npm_command", return_value=["C:/nodejs/npm.cmd"]),
            patch.object(start_app, "_electron_executable", return_value=electron),
            patch.object(start_app.subprocess, "Popen", side_effect=popen),
            patch.object(start_app.subprocess, "DETACHED_PROCESS", 8, create=True),
            patch.object(start_app.subprocess, "CREATE_NEW_PROCESS_GROUP", 512, create=True),
            patch.object(start_app.sys, "platform", platform),
            patch.object(Path, "is_dir", return_value=True),
        ):
            start_app.do_desktop()
        return calls

    def test_prefere_o_binario_real_do_electron(self):
        calls = self._launch("win32", Path("C:/app/electron.exe"))
        self.assertEqual(calls["command"], [str(Path("C:/app/electron.exe")), "."])

    def test_sem_binario_usa_npm_start(self):
        calls = self._launch("win32", None)
        self.assertEqual(calls["command"], ["C:/nodejs/npm.cmd", "start"])

    def test_windows_desanexa_sem_start_new_session(self):
        calls = self._launch("win32", None)
        self.assertNotIn("start_new_session", calls["kwargs"])
        self.assertIn("creationflags", calls["kwargs"])

    def test_posix_mantem_start_new_session(self):
        calls = self._launch("linux", None)
        self.assertTrue(calls["kwargs"]["start_new_session"])

    def test_exporta_interpretador_para_o_electron(self):
        calls = self._launch("win32", None)
        self.assertEqual(calls["kwargs"]["env"]["AUDIOFY_PYTHON"], sys.executable)

    def test_primeira_instalacao_usa_lockfile(self):
        completed = Mock(returncode=0, stderr="", stdout="")
        with (
            patch.object(start_app, "_npm_command", return_value=["npm"]),
            patch.object(Path, "is_dir", return_value=False),
            patch.object(start_app.subprocess, "run", return_value=completed) as run,
            patch.object(start_app, "_electron_executable", return_value=None),
            patch.object(start_app.subprocess, "Popen"),
        ):
            start_app.do_desktop()

        self.assertEqual(run.call_args.args[0][:2], ["npm", "ci"])


class ElectronExecutableTest(unittest.TestCase):
    def test_le_o_binario_de_path_txt(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "node_modules" / "electron"
            (package / "dist").mkdir(parents=True)
            (package / "path.txt").write_text("electron\n", encoding="utf-8")
            (package / "dist" / "electron").write_text("", encoding="utf-8")
            found = start_app._electron_executable(Path(tmp))
            self.assertEqual(found, package / "dist" / "electron")

    def test_sem_path_txt_retorna_none(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(start_app._electron_executable(Path(tmp)))


class MainMenuQualityTest(unittest.TestCase):
    def test_listagem_paginda_usa_selecao_da_tui(self):
        source = Mock()
        source.list_items.return_value = [
            Mock(published_at="2026-01-01", title="Um"),
            Mock(published_at="2026-01-02", title="Dois"),
            Mock(published_at="2026-01-03", title="Três"),
        ]
        terminal = Mock()
        terminal.choose.return_value = "stop"

        with (
            patch.object(start_app, "ensure_synced"),
            patch.object(start_app, "get_source", return_value=source),
            patch.object(start_app, "_tui", return_value=terminal),
        ):
            start_app.do_list(page_size=2)

        terminal.choose.assert_called_once()
        self.assertIn("Exibidos 2 de 3", terminal.choose.call_args.args[0])

    def test_configuracao_reune_as_acoes_obrigatorias(self):
        terminal = Mock()
        terminal.choose.return_value = "back"

        with patch.object(start_app, "_tui", return_value=terminal):
            start_app.do_configure()

        labels = [label for label, _value in terminal.choose.call_args.args[1]]
        self.assertTrue(any("Chaves" in label for label in labels))
        self.assertTrue(any("Perfis" in label for label in labels))

    def test_status_consulta_o_ambiente_real(self):
        settings = SimpleNamespace(
            api_key="chave-configurada",
            profile_name="padrao",
            text_provider="openrouter",
            text_model="modelo-texto",
            audit_model="modelo-auditoria",
            tts_model="modelo-tts",
            presenters=[],
        )
        source = Mock()
        source.name = "Fonte local"
        source.is_ready.return_value = False
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env").write_text("", encoding="utf-8")
            output = StringIO()
            with (
                patch.object(start_app, "PROJECT_ROOT", root),
                patch.object(start_app, "EPISODES_DIR", root / "episodes"),
                patch.object(start_app, "Settings", return_value=settings),
                patch.object(start_app, "get_source", return_value=source),
                patch.object(start_app, "_running_generations", return_value=[]),
                patch.object(start_app.sys, "prefix", root / "venv"),
                patch.object(start_app.sys, "base_prefix", root / "python"),
                patch("audiofy.config.api_key_source", return_value="teste"),
                patch(
                    "audiofy.setup.inspect_setup",
                    return_value=[setup.SetupCheck("node", "Node.js", True, False, "opcional")],
                ),
                redirect_stdout(output),
            ):
                start_app.do_status()

        rendered = output.getvalue()
        self.assertIn("Ambiente virtual ativo", rendered)
        self.assertIn("Arquivo .env presente", rendered)
        self.assertIn("Node.js disponível", rendered)
        self.assertIn("Chave configurada (teste)", rendered)


if __name__ == "__main__":
    unittest.main()
