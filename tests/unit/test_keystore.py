"""Testes do cofre de chaves nomeadas do OpenRouter."""

import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy.keystore import KeyStore, validate_api_key, validate_name  # noqa: E402

FAKE_KEY = "sk-or-v1-abcdefghijklmnopqrstuvwxyz012345"


class ValidationTest(unittest.TestCase):
    def test_chave_valida(self):
        self.assertEqual(validate_api_key(f"  {FAKE_KEY} "), FAKE_KEY)

    def test_chave_sem_prefixo(self):
        with self.assertRaises(ValueError):
            validate_api_key("sk-proj-outra-coisa-qualquer")

    def test_chave_curta(self):
        with self.assertRaises(ValueError):
            validate_api_key("sk-or-x")

    def test_nome_vazio(self):
        with self.assertRaises(ValueError):
            validate_name("   ")


class KeyStoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = KeyStore(Path(self._tmp.name) / "keys.json")
        os.environ.pop("OPENROUTER_API_KEY", None)

    def tearDown(self):
        self._tmp.cleanup()
        os.environ.pop("OPENROUTER_API_KEY", None)

    def test_vazio_sem_chave_ativa(self):
        self.assertIsNone(self.store.active_key())
        self.assertEqual(self.store.list_keys(), [])

    def test_adicionar_ativa_primeira(self):
        self.store.add("pessoal", FAKE_KEY)
        self.assertEqual(self.store.active_key(), FAKE_KEY)
        self.assertEqual(self.store.active_name(), "pessoal")

    def test_multiplas_chaves_e_troca(self):
        self.store.add("pessoal", FAKE_KEY)
        self.store.add("trabalho", FAKE_KEY.replace("abc", "xyz"))
        self.store.set_active("trabalho")
        self.assertEqual(self.store.active_name(), "trabalho")
        self.assertTrue(self.store.prefers_named())
        self.assertEqual(len(self.store.list_keys()), 2)

    def test_selecao_explicita_supera_chave_do_ambiente(self):
        self.store.add("pessoal", FAKE_KEY)
        os.environ["OPENROUTER_API_KEY"] = "sk-or-v1-prioridade-do-ambiente-000000"

        self.store.set_active("pessoal")

        self.assertEqual(self.store.resolve(), FAKE_KEY)

    def test_pode_voltar_a_usar_chave_do_ambiente(self):
        self.store.add("pessoal", FAKE_KEY)
        self.store.set_active("pessoal")
        os.environ["OPENROUTER_API_KEY"] = "sk-or-v1-prioridade-do-ambiente-000000"

        self.store.use_environment()

        self.assertFalse(self.store.prefers_named())
        self.assertEqual(self.store.resolve(), "sk-or-v1-prioridade-do-ambiente-000000")

    def test_busca_chave_nomeada_sem_expor_as_demais(self):
        self.store.add("pessoal", FAKE_KEY)
        self.assertEqual(self.store.get("pessoal").key, FAKE_KEY)
        with self.assertRaises(LookupError):
            self.store.get("inexistente")

    def test_nome_duplicado_sobrescreve(self):
        self.store.add("pessoal", FAKE_KEY)
        self.store.add("pessoal", FAKE_KEY.replace("abc", "xyz"))
        self.assertEqual(len(self.store.list_keys()), 1)

    def test_remover(self):
        self.store.add("pessoal", FAKE_KEY)
        self.store.remove("pessoal")
        self.assertIsNone(self.store.active_key())

    def test_env_tem_prioridade(self):
        self.store.add("pessoal", FAKE_KEY)
        os.environ["OPENROUTER_API_KEY"] = "sk-or-v1-prioridade-do-ambiente-000000"
        self.assertEqual(self.store.resolve(), "sk-or-v1-prioridade-do-ambiente-000000")

    def test_resolve_usa_ativa_sem_env(self):
        self.store.add("pessoal", FAKE_KEY)
        self.assertEqual(self.store.resolve(), FAKE_KEY)

    def test_permissoes_restritas_no_unix(self):
        if os.name == "nt":
            self.skipTest("permissões POSIX não se aplicam no Windows")
        self.store.add("pessoal", FAKE_KEY)
        mode = stat.S_IMODE(self.store.path.stat().st_mode)
        self.assertEqual(mode, 0o600)

    def test_persistencia_entre_instancias(self):
        self.store.add("pessoal", FAKE_KEY)
        self.store.set_active("pessoal")
        reloaded = KeyStore(self.store.path)
        self.assertEqual(reloaded.active_key(), FAKE_KEY)
        self.assertTrue(reloaded.prefers_named())

    def test_cofre_antigo_preserva_prioridade_do_ambiente(self):
        self.store.path.parent.mkdir(parents=True, exist_ok=True)
        self.store.path.write_text(
            json.dumps({"active": "pessoal", "keys": {"pessoal": FAKE_KEY}}),
            encoding="utf-8",
        )
        os.environ["OPENROUTER_API_KEY"] = "sk-or-v1-prioridade-do-ambiente-000000"

        reloaded = KeyStore(self.store.path)

        self.assertFalse(reloaded.prefers_named())
        self.assertEqual(reloaded.resolve(), "sk-or-v1-prioridade-do-ambiente-000000")


if __name__ == "__main__":
    unittest.main()
