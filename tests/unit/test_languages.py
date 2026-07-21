"""Registro central de idiomas: fonte única para rótulos e códigos suportados."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy.languages import (  # noqa: E402
    DEFAULT_LANGUAGE,
    LANGUAGES,
    get_language,
    is_supported,
    normalize,
    prompt_label,
    supported_codes,
)


class LanguageRegistryTest(unittest.TestCase):
    def test_idiomas_atuais_estao_registrados(self):
        self.assertIn("pt-BR", LANGUAGES)
        self.assertIn("en", LANGUAGES)
        self.assertEqual(DEFAULT_LANGUAGE, "pt-BR")

    def test_cada_entrada_traz_codigo_e_rotulos(self):
        for code, language in LANGUAGES.items():
            self.assertEqual(language.code, code)
            self.assertTrue(language.prompt_label)
            self.assertTrue(language.ui_label)

    def test_prompt_label_alimenta_os_prompts(self):
        self.assertEqual(prompt_label("pt-BR"), "português brasileiro")
        self.assertEqual(prompt_label("en"), "English")

    def test_codigo_desconhecido_cai_no_padrao_sem_levantar(self):
        # A geração não pode quebrar por um código vindo de um artefato antigo.
        self.assertEqual(get_language("xx-YY").code, DEFAULT_LANGUAGE)
        self.assertEqual(prompt_label("xx-YY"), prompt_label(DEFAULT_LANGUAGE))
        self.assertEqual(normalize("xx-YY"), DEFAULT_LANGUAGE)

    def test_normalize_preserva_codigo_suportado(self):
        self.assertEqual(normalize("en"), "en")

    def test_is_supported_e_supported_codes_concordam(self):
        for code in supported_codes():
            self.assertTrue(is_supported(code))
        self.assertFalse(is_supported("xx-YY"))


class AddingLanguageIsOnePlaceTest(unittest.TestCase):
    """Prova que registrar um idioma novo é local: uma entrada no registro já o
    torna suportado e válido em todo o pipeline, sem tocar nos módulos de texto."""

    def setUp(self):
        from audiofy.languages import Language

        self._added = "es"
        LANGUAGES[self._added] = Language(code="es", prompt_label="español", ui_label="Español")
        self.addCleanup(LANGUAGES.pop, self._added, None)

    def test_idioma_novo_passa_a_ser_suportado_e_valido(self):
        self.assertTrue(is_supported("es"))
        self.assertEqual(prompt_label("es"), "español")
        self.assertIn("es", supported_codes())

    def test_perfil_aceita_o_idioma_recem_registrado(self):
        from audiofy.profiles import profile_from_payload

        profile = profile_from_payload(
            {
                "name": "espanhol",
                "tts_model": "vendor/tts",
                "presenters_spec": "narrador:Kore",
                "text_provider": "claude-code",
                "language": "es",
            }
        )
        self.assertEqual(profile.language, "es")

    def test_export_usa_o_rotulo_do_idioma_novo(self):
        # Sem tocar em export.py, o rótulo do prompt sai do registro.
        self.assertEqual(prompt_label("es"), "español")


if __name__ == "__main__":
    unittest.main()
