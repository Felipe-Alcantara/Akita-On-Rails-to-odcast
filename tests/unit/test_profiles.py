"""Testes dos perfis nomeados de configuração (modelos + apresentadores)."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy.config import Settings  # noqa: E402
from audiofy.profiles import BUILTIN_PROFILES, Profile, ProfileStore  # noqa: E402


class ProfileStoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = ProfileStore(Path(self._tmp.name) / "profiles.json")

    def tearDown(self):
        self._tmp.cleanup()

    def test_builtin_padrao_e_o_ativo_inicial(self):
        self.assertEqual(self.store.active().name, "padrao")

    def test_builtins_presentes(self):
        names = [p.name for p in self.store.list_profiles()]
        for builtin in BUILTIN_PROFILES:
            self.assertIn(builtin.name, names)

    def test_trocar_perfil_ativo(self):
        self.store.set_active("economico")
        self.assertEqual(self.store.active().name, "economico")

    def test_perfil_economico_usa_modelo_mais_barato_no_roteiro(self):
        economico = self.store.get("economico")
        self.assertEqual(economico.text_model, economico.audit_model)

    def test_perfil_codex_usa_assinatura_openai(self):
        codex = self.store.get("assinatura-codex")
        self.assertEqual(codex.text_provider, "codex")
        self.assertEqual(codex.text_model, "(assinatura)")
        self.assertTrue(codex.tts_model)
        self.store.set_active("assinatura-codex")
        self.assertEqual(self.store.active(), codex)

    def test_perfil_gemini_cli_usa_assinatura_google(self):
        gemini = self.store.get("assinatura-gemini")
        self.assertEqual(gemini.text_provider, "gemini-cli")
        self.assertEqual(gemini.text_model, "(assinatura)")

    def test_narrador_economico_usa_flash_em_tudo(self):
        eco = self.store.get("narrador-economico")
        self.assertEqual(eco.text_model, eco.audit_model)
        self.assertIn("flash", eco.text_model.lower())

    def test_narrador_premium_usa_pro_em_tudo(self):
        prem = self.store.get("narrador-premium")
        self.assertIn("pro", prem.text_model.lower())
        self.assertIn("pro", prem.audit_model.lower())

    def test_podcast_trio_tem_tres_apresentadores(self):
        from audiofy.presenters import parse_presenters
        trio = self.store.get("podcast-trio")
        self.assertEqual(len(parse_presenters(trio.presenters_spec)), 3)

    def test_podcast_mesa_redonda_tem_quatro_apresentadores(self):
        from audiofy.presenters import parse_presenters
        mesa = self.store.get("podcast-mesa-redonda")
        self.assertEqual(len(parse_presenters(mesa.presenters_spec)), 4)

    def test_premium_claude_usa_anthropic(self):
        claude = self.store.get("premium-claude")
        self.assertTrue(claude.text_model.startswith("anthropic/"))

    def test_narrador_assinatura_e_solo(self):
        from audiofy.presenters import parse_presenters
        solo = self.store.get("narrador-assinatura")
        self.assertEqual(len(parse_presenters(solo.presenters_spec)), 1)
        self.assertEqual(solo.text_provider, "claude-code")

    def test_criar_perfil_customizado(self):
        custom = Profile(
            name="meu",
            text_model="x/y",
            audit_model="x/z",
            tts_model="x/tts",
            presenters_spec="solo:Sulafat",
        )
        self.store.save(custom)
        self.store.set_active("meu")
        self.assertEqual(self.store.active().presenters_spec, "solo:Sulafat")
        self.assertTrue(self.store.is_custom("meu"))
        self.assertFalse(self.store.is_custom("padrao"))

    def test_persistencia_entre_instancias(self):
        self.store.save(Profile("meu", "a/b", "a/c", "a/d", "n:V"))
        self.store.set_active("meu")
        reloaded = ProfileStore(self.store.path)
        self.assertEqual(reloaded.active().name, "meu")

    def test_builtin_nao_pode_ser_removido(self):
        with self.assertRaises(ValueError):
            self.store.remove("padrao")

    def test_remover_custom_ativo_volta_ao_padrao(self):
        self.store.save(Profile("meu", "a/b", "a/c", "a/d", "n:V"))
        self.store.set_active("meu")
        self.store.remove("meu")
        self.assertEqual(self.store.active().name, "padrao")
        self.assertFalse(self.store.is_custom("meu"))

    def test_remover_override_revela_builtin(self):
        original = self.store.get("economico")
        self.store.save(Profile("economico", "x/y", "x/z", "x/tts", "n:V"))
        self.assertTrue(self.store.is_custom("economico"))
        self.store.remove("economico")
        self.assertEqual(self.store.get("economico"), original)

    def test_perfil_inexistente(self):
        with self.assertRaises(LookupError):
            self.store.set_active("nao-existe")


class SettingsProfileNameTest(unittest.TestCase):
    @patch("audiofy.config._default_settings")
    def test_nome_do_perfil_vem_da_configuracao_resolvida(self, defaults):
        defaults.return_value = {
            "api_key": "key",
            "profile_name": "assinatura-codex",
            "text_provider": "codex",
            "text_model": "(assinatura)",
            "audit_model": "(assinatura)",
            "tts_model": "tts/model",
            "presenters": [],
        }
        self.assertEqual(Settings().profile_name, "assinatura-codex")


if __name__ == "__main__":
    unittest.main()
