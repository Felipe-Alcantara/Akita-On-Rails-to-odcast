"""Testes do provedor de texto por assinatura (CLIs locais)."""

import subprocess
import sys
import tempfile
import unittest
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
            command = cli.command(
                "sistema",
            )
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

        old = {
            "name": "meu",
            "text_model": "a/b",
            "audit_model": "a/c",
            "tts_model": "a/d",
            "presenters_spec": "n:V",
            "description": "",
        }
        profile = Profile(**old)
        self.assertEqual(profile.text_provider, "openrouter")

    def test_perfil_assinatura_embutido(self):
        from audiofy.profiles import BUILTIN_PROFILES

        assinatura = next(p for p in BUILTIN_PROFILES if p.name == "claude-code-duo")
        self.assertNotEqual(assinatura.text_provider, "openrouter")


class RunCliTest(unittest.TestCase):
    """No Windows shims npm são resolvidos sem passar pelo cmd.exe."""

    NODE_SHIM = (
        '@ECHO off\n"%dp0%\\node.exe" '
        '"%dp0%\\node_modules\\@anthropic-ai\\claude-code\\cli.js" %*\n'
    )
    # Pacotes recentes do Claude Code distribuem um binário nativo no lugar do .js.
    NATIVE_SHIM = (
        "@ECHO off\nGOTO start\n:find_dp0\nSET dp0=%~dp0\nEXIT /b\n:start\nSETLOCAL\n"
        'CALL :find_dp0\n"%dp0%\\node_modules\\@anthropic-ai\\claude-code\\bin\\claude.exe"'
        "   %*\n"
    )

    def _run(self, platform: str, shim_text: str | None = None) -> dict:
        calls = {}

        def fake_run(command, **kwargs):
            calls["command"] = command
            calls["kwargs"] = kwargs

        with tempfile.TemporaryDirectory() as tmp:
            shim = Path(tmp) / "claude.cmd"
            shim.write_text(shim_text or self.NODE_SHIM, encoding="utf-8")
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
        # O separador vem de os.sep, então a asserção não pode fixar "/" nem "\".
        self.assertEqual(Path(calls["command"][1]).parts[-2:], ("claude-code", "cli.js"))
        self.assertEqual(calls["command"][-1], "voz\ncalma")
        self.assertNotIn("shell", calls["kwargs"])

    def test_windows_executa_binario_nativo_do_shim(self):
        calls = self._run("win32", self.NATIVE_SHIM)
        self.assertEqual(Path(calls["command"][0]).parts[-2:], ("bin", "claude.exe"))
        self.assertEqual(calls["command"][-1], "voz\ncalma")

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
            patch.object(subscription, "run_cli", side_effect=OSError("arquivo não encontrado")),
            patch.object(subscription.shutil, "which", return_value="claude"),
        ):
            with self.assertRaises(SubscriptionError) as context:
                chat_json("claude-code", "sistema", "usuário")
        self.assertIn("claude", str(context.exception))


class ModeloDaAssinaturaTest(unittest.TestCase):
    """Escolha explícita do modelo em cada CLI de assinatura."""

    def test_sem_modelo_o_comando_fica_como_antes(self):
        self.assertNotIn("--model", get_cli("claude-code").command("SYS"))
        self.assertEqual(
            get_cli("codex").command("SYS"),
            ["codex", "exec", "-", "-c", 'model_reasoning_effort="high"'],
        )

    def test_modelo_vira_flag_no_fim_do_comando(self):
        for key in ("claude-code", "gemini-cli", "codex"):
            command = get_cli(key).command("SYS", "meu-modelo")
            model_index = command.index("--model")
            self.assertEqual(command[model_index : model_index + 2], ["--model", "meu-modelo"], key)

    def test_gemini_recebe_o_modelo_mesmo_lendo_tudo_por_stdin(self):
        # A CLI do Gemini não tem args de modo headless; o modelo precisava chegar
        # por outro caminho que não o `command()` do ramo com argumentos.
        self.assertEqual(
            get_cli("gemini-cli").command("", "gemini-2.5-pro"),
            ["gemini", "--model", "gemini-2.5-pro"],
        )

    def test_chat_command_mantem_permissoes_depois_do_modelo(self):
        command = get_cli("claude-code").chat_command("SYS", "opus")
        self.assertIn("--model", command)

    def test_claude_code_exige_esforco_alto(self):
        self.assertIn("--effort", get_cli("claude-code").command("SYS"))
        command = get_cli("claude-code").command("SYS")
        self.assertEqual(command[command.index("--effort") + 1], "high")

    def test_codex_exige_esforco_de_raciocinio_alto(self):
        command = get_cli("codex").command("SYS")
        self.assertIn('model_reasoning_effort="high"', command)

    def test_chat_json_repassa_o_modelo_para_a_cli(self):
        done = subprocess.CompletedProcess(["claude"], 0, '{"ok": true}', "")
        with (
            patch.object(subscription, "run_cli", return_value=done) as run,
            patch.object(subscription.shutil, "which", return_value="claude"),
        ):
            chat_json("claude-code", "sistema", "usuário", "haiku")
        self.assertEqual(run.call_args.args[0][-2:], ["--model", "haiku"])

    def test_chat_json_sem_modelo_nao_passa_a_flag(self):
        done = subprocess.CompletedProcess(["claude"], 0, '{"ok": true}', "")
        with (
            patch.object(subscription, "run_cli", return_value=done) as run,
            patch.object(subscription.shutil, "which", return_value="claude"),
        ):
            chat_json("claude-code", "sistema", "usuário")
        self.assertNotIn("--model", run.call_args.args[0])

    def test_todas_as_clis_anunciam_sugestoes_de_modelo(self):
        for cli in SUBSCRIPTION_CLIS:
            self.assertTrue(cli.model_suggestions, cli.key)
            self.assertTrue(cli.model_flag, cli.key)


if __name__ == "__main__":
    unittest.main()
