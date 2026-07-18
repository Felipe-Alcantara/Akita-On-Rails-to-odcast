"""Testes do diagnóstico compartilhado de ambiente."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy.setup import SetupCheck, apply_setup, inspect_setup, setup_report  # noqa: E402


class SetupReportTest(unittest.TestCase):
    @patch("audiofy.setup.shutil.which")
    def test_node_e_npm_sao_diagnosticados_sem_bloquear_a_cli(self, which):
        which.return_value = None

        checks = {check.key: check for check in inspect_setup()}

        self.assertFalse(checks["node"].ok)
        self.assertFalse(checks["node"].required)
        self.assertFalse(checks["npm"].ok)
        self.assertFalse(checks["npm"].required)

    @patch("audiofy.setup.inspect_setup")
    def test_opcional_ausente_nao_bloqueia_ambiente(self, inspect_setup):
        inspect_setup.return_value = [
            SetupCheck("required", "Obrigatório", True, True, ""),
            SetupCheck("optional", "Opcional", False, False, ""),
        ]
        self.assertTrue(setup_report()["ready"])

    @patch("audiofy.setup.inspect_setup")
    def test_obrigatorio_ausente_bloqueia_ambiente(self, inspect_setup):
        inspect_setup.return_value = [
            SetupCheck("required", "Obrigatório", False, True, "corrija"),
        ]
        self.assertFalse(setup_report()["ready"])

    @patch("audiofy.setup.inspect_setup")
    def test_apply_cria_env_sem_instalar_o_que_ja_existe(self, inspect_setup):
        checks = [
            SetupCheck("requests", "requests", True, True, ""),
            SetupCheck("questionary", "questionary", True, True, ""),
            SetupCheck("rich", "rich", True, True, ""),
            SetupCheck("akita-articles", "akita", True, True, ""),
        ]
        inspect_setup.return_value = checks
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.example").write_text("OPENROUTER_API_KEY=\n", encoding="utf-8")
            with patch("audiofy.setup.PROJECT_ROOT", root):
                result = apply_setup()
            self.assertTrue((root / ".env").is_file())
        self.assertEqual(result["actions"][0]["name"], ".env")

    @patch("audiofy.setup._install_system")
    @patch("audiofy.setup.inspect_setup")
    def test_apply_instala_git_e_ffmpeg_ausentes(self, inspect_setup, install_system):
        inspect_setup.return_value = [
            SetupCheck("git", "Git", False, True, ""),
            SetupCheck("ffmpeg", "FFmpeg", False, True, ""),
            SetupCheck("akita-articles", "akita", True, True, ""),
        ]
        install_system.side_effect = lambda tool: {"name": tool, "ok": True, "detail": ""}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.example").write_text("OPENROUTER_API_KEY=\n", encoding="utf-8")
            with patch("audiofy.setup.PROJECT_ROOT", root):
                result = apply_setup()
        self.assertEqual([a["name"] for a in result["actions"][:2]], ["git", "ffmpeg"])

    @patch("audiofy.setup._install")
    @patch("audiofy.setup.inspect_setup")
    def test_dependencias_ausentes_usam_arquivo_fixado(self, inspect_setup, install):
        inspect_setup.return_value = [
            SetupCheck("requests", "requests", False, True, ""),
            SetupCheck("questionary", "questionary", True, True, ""),
            SetupCheck("rich", "rich", True, True, ""),
            SetupCheck("akita-articles", "akita", True, True, ""),
        ]
        install.return_value = {"name": "dependências Python", "ok": True, "detail": ""}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".env.example").write_text("OPENROUTER_API_KEY=\n", encoding="utf-8")
            (root / "requirements.txt").write_text("requests==2.34.2\n", encoding="utf-8")
            with patch("audiofy.setup.PROJECT_ROOT", root):
                apply_setup()

        install.assert_called_once_with("dependências Python", "-r", str(root / "requirements.txt"))

    @patch("audiofy.setup._run")
    @patch("audiofy.setup.npm_command", return_value=["npm"])
    @patch("audiofy.setup.inspect_setup")
    def test_setup_instala_desktop_pelo_lockfile(self, inspect_setup, _npm, run):
        inspect_setup.return_value = [
            SetupCheck("npm", "npm", True, False, ""),
            SetupCheck("electron-deps", "Electron", False, False, ""),
        ]
        run.return_value = (True, "instalação concluída")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            electron = root / "electron"
            electron.mkdir()
            (electron / "package-lock.json").write_text("{}", encoding="utf-8")
            (root / ".env.example").write_text("OPENROUTER_API_KEY=\n", encoding="utf-8")
            with patch("audiofy.setup.PROJECT_ROOT", root):
                result = apply_setup()

        run.assert_called_once_with(
            ["npm", "ci", "--no-fund", "--no-audit"],
            cwd=electron,
        )
        self.assertTrue(result["actions"][0]["ok"])

    @patch("audiofy.setup._run")
    def test_pip_bloqueado_tenta_break_system_packages(self, run):
        from audiofy.setup import _install

        run.side_effect = [
            (False, "error: externally-managed-environment"),
            (True, "instalação concluída"),
        ]
        result = _install("pacotes", "rich")
        self.assertTrue(result["ok"])
        self.assertIn("--break-system-packages", run.call_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
