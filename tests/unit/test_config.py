"""Procedência e atualização segura da configuração de ambiente."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy import config  # noqa: E402


class DotenvEnvironmentTest(unittest.TestCase):
    def test_load_dotenv_registra_apenas_chaves_que_nao_vieram_do_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            dotenv = Path(directory) / ".env"
            dotenv.write_text("DO_ARQUIVO=novo\nDO_SHELL=arquivo\n", encoding="utf-8")
            with patch.dict(os.environ, {"DO_SHELL": "shell"}, clear=True):
                loaded = config._load_dotenv(dotenv)

                self.assertEqual(loaded, frozenset({"DO_ARQUIVO"}))
                self.assertEqual(os.environ["DO_ARQUIVO"], "novo")
                self.assertEqual(os.environ["DO_SHELL"], "shell")

    def test_desktop_atualiza_valor_do_dotenv_e_mantem_chave_do_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            dotenv = Path(directory) / ".env"
            dotenv.write_text("OPENROUTER_API_KEY=chave-atual\n", encoding="utf-8")
            environment = {
                "OPENROUTER_API_KEY": "chave-antiga",
                "CHAVE_DO_SHELL": "preservada",
            }
            with (
                patch.dict(os.environ, environment, clear=True),
                patch.object(config, "DOTENV_LOADED_KEYS", frozenset({"OPENROUTER_API_KEY"})),
            ):
                result = config.desktop_environment(dotenv)

            self.assertEqual(result["OPENROUTER_API_KEY"], "chave-atual")
            self.assertEqual(result["CHAVE_DO_SHELL"], "preservada")
            self.assertEqual(result[config.DOTENV_PROVENANCE_ENV], "OPENROUTER_API_KEY")

    def test_desktop_do_app_prioriza_dotenv_atual(self):
        with tempfile.TemporaryDirectory() as directory:
            dotenv = Path(directory) / ".env"
            dotenv.write_text("OPENROUTER_API_KEY=chave-atual\n", encoding="utf-8")
            with (
                patch.dict(os.environ, {"OPENROUTER_API_KEY": "chave-antiga"}, clear=True),
                patch.object(config, "DOTENV_LOADED_KEYS", frozenset()),
            ):
                result = config.desktop_environment(dotenv, prefer_dotenv=True)

            self.assertEqual(result["OPENROUTER_API_KEY"], "chave-atual")
            self.assertEqual(result[config.DOTENV_PROVENANCE_ENV], "OPENROUTER_API_KEY")

    def test_origem_distingue_dotenv_de_shell(self):
        with (
            patch.dict(os.environ, {"OPENROUTER_API_KEY": "chave"}, clear=True),
            patch.object(config, "DOTENV_LOADED_KEYS", frozenset({"OPENROUTER_API_KEY"})),
        ):
            self.assertEqual(config.api_key_source(), ".env")

        with (
            patch.dict(os.environ, {"OPENROUTER_API_KEY": "chave"}, clear=True),
            patch.object(config, "DOTENV_LOADED_KEYS", frozenset()),
        ):
            self.assertEqual(config.api_key_source(), "ambiente")


if __name__ == "__main__":
    unittest.main()
