"""Testes do provedor de texto por assinatura (CLIs locais)."""

import sys
import tempfile
import unittest
import subprocess
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy.providers import subscription  # noqa: E402
from audiofy.providers.subscription import (  # noqa: E402
    SUBSCRIPTION_CLIS,
    SubscriptionError,
    available_clis,
    chat_json,
    configured_model,
    get_cli,
    run_cli,
)


class RegistryTest(unittest.TestCase):
    def test_clis_conhecidas(self):
        keys = [c.key for c in SUBSCRIPTION_CLIS]
        self.assertIn("claude-code", keys)
        self.assertIn("gemini-cli", keys)
        self.assertIn("codex", keys)

    def test_get_cli(self):
        cli = get_cli("claude-code")
        self.assertEqual(cli.binary, "claude")

    def test_get_cli_desconhecida(self):
        with self.assertRaises(LookupError):
            get_cli("nao-existe")

    def test_available_retorna_subconjunto(self):
        available = {c.key for c in available_clis()}
        self.assertTrue(available.issubset({c.key for c in SUBSCRIPTION_CLIS}))

    def test_comando_inclui_binario(self):
        for cli in SUBSCRIPTION_CLIS:
            command = cli.command("sistema", )
            self.assertEqual(command[0], cli.binary)

    def test_chat_tem_permissao_total_sem_afetar_o_pipeline(self):
        claude = get_cli("claude-code")
        self.assertIn("--dangerously-skip-permissions", claude.chat_command("s"))
        self.assertNotIn("--dangerously-skip-permissions", claude.command("s"))
        self.assertIn("--yolo", get_cli("gemini-cli").chat_args)

    def test_detecta_modelo_global_do_codex(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.toml"
            config.write_text(
                'model = "gpt-5.6-sol"\n[profiles.outro]\nmodel = "ignorado"\n',
                encoding="utf-8",
            )
            with patch.dict("os.environ", {"CODEX_HOME": tmp}):
                self.assertEqual(configured_model("codex"), "gpt-5.6-sol")

    def test_nao_confunde_modelo_de_perfil_com_global(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "config.toml"
            config.write_text('[profiles.outro]\nmodel = "nao-efetivo"\n', encoding="utf-8")
            with patch.dict("os.environ", {"CODEX_HOME": tmp}):
                self.assertIsNone(configured_model("codex"))


class ProfileCompatTest(unittest.TestCase):
    def test_perfil_antigo_sem_text_provider_carrega(self):
        from audiofy.profiles import Profile
        old = {"name": "meu", "text_model": "a/b", "audit_model": "a/c",
               "tts_model": "a/d", "presenters_spec": "n:V", "description": ""}
        profile = Profile(**old)
        self.assertEqual(profile.text_provider, "openrouter")

    def test_perfil_assinatura_embutido(self):
        from audiofy.profiles import BUILTIN_PROFILES
        assinatura = next(p for p in BUILTIN_PROFILES if p.name == "assinatura")
        self.assertNotEqual(assinatura.text_provider, "openrouter")


class RunCliTest(unittest.TestCase):
    """No Windows shims npm são resolvidos sem passar pelo cmd.exe."""

    def _run(self, platform: str) -> dict:
        calls = {}

        def fake_run(command, **kwargs):
            calls["command"] = command
            calls["kwargs"] = kwargs

        with tempfile.TemporaryDirectory() as tmp:
            shim = Path(tmp) / "claude.cmd"
            shim.write_text(
                '@ECHO off\n"%dp0%\\node.exe" '
                '"%dp0%\\node_modules\\@anthropic-ai\\claude-code\\cli.js" %*\n',
                encoding="utf-8",
            )
            paths = {"claude": str(shim), "node": "C:/nodejs/node.exe"}
            with (
                patch.object(subscription.subprocess, "run", side_effect=fake_run),
                patch.object(subscription.shutil, "which", side_effect=paths.get),
                patch.object(subscription.sys, "platform", platform),
            ):
                run_cli(["claude", "-p", "--append-system-prompt", "voz\ncalma"], "olá")
        return calls

    def test_windows_executa_node_diretamente_e_preserva_prompt_multilinha(self):
        calls = self._run("win32")
        self.assertEqual(calls["command"][0], "C:/nodejs/node.exe")
        self.assertTrue(calls["command"][1].endswith("claude-code/cli.js"))
        self.assertEqual(calls["command"][-1], "voz\ncalma")
        self.assertNotIn("shell", calls["kwargs"])

    def test_posix_executa_sem_shell(self):
        calls = self._run("linux")
        self.assertEqual(calls["command"][0], "claude")
        self.assertNotIn("shell", calls["kwargs"])

    def test_chat_json_rejeita_stdout_ausente_com_erro_claro(self):
        empty = subprocess.CompletedProcess(["claude"], 0, None, None)
        with (
            patch.object(subscription, "run_cli", return_value=empty),
            patch.object(subscription.shutil, "which", return_value="claude"),
        ):
            with self.assertRaisesRegex(SubscriptionError, "sem retornar uma resposta"):
                chat_json("claude-code", "sistema", "usuário")

    def test_chat_json_traduz_oserror(self):
        with (
            patch.object(subscription, "run_cli",
                         side_effect=OSError("arquivo não encontrado")),
            patch.object(subscription.shutil, "which", return_value="claude"),
        ):
            with self.assertRaises(SubscriptionError) as context:
                chat_json("claude-code", "sistema", "usuário")
        self.assertIn("claude", str(context.exception))


if __name__ == "__main__":
    unittest.main()
