"""Testes do contrato JSON compartilhado pelo Electron e por automações."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy import bridge  # noqa: E402
from audiofy.catalog import Model  # noqa: E402
from audiofy.profiles import profile_from_payload  # noqa: E402


class ProfilePayloadTest(unittest.TestCase):
    def test_openrouter_exige_e_preserva_modelos(self):
        profile = profile_from_payload({
            "name": " meu ",
            "text_provider": "openrouter",
            "text_model": "vendor/text",
            "audit_model": "vendor/audit",
            "tts_model": "vendor/tts",
            "presenters_spec": "ana:Kore:curiosa",
        })
        self.assertEqual(profile.name, "meu")
        self.assertEqual(profile.text_model, "vendor/text")

    def test_assinatura_normaliza_modelos_de_texto(self):
        profile = profile_from_payload({
            "name": "assinante",
            "text_provider": "codex",
            "tts_model": "vendor/tts",
            "presenters_spec": "ana:Kore",
        })
        self.assertEqual(profile.text_model, "(assinatura)")
        self.assertEqual(profile.audit_model, "(assinatura)")

    def test_rejeita_provedor_desconhecido(self):
        with self.assertRaisesRegex(ValueError, "Provedor"):
            profile_from_payload({
                "name": "inválido",
                "text_provider": "qualquer-binario",
                "tts_model": "vendor/tts",
                "presenters_spec": "ana:Kore",
            })

    def test_rejeita_lista_de_apresentadores_vazia(self):
        with self.assertRaisesRegex(ValueError, "apresentador"):
            profile_from_payload({
                "name": "sem-voz",
                "text_model": "vendor/text",
                "audit_model": "vendor/audit",
                "tts_model": "vendor/tts",
                "presenters_spec": "",
            })

    def test_rejeita_nome_de_perfil_inseguro(self):
        with self.assertRaisesRegex(ValueError, "nome do perfil"):
            profile_from_payload({
                "name": "../../perfil",
                "text_model": "vendor/text",
                "audit_model": "vendor/audit",
                "tts_model": "vendor/tts",
                "presenters_spec": "ana:Kore",
            })


class CatalogFallbackTest(unittest.TestCase):
    @patch("audiofy.providers.openrouter.list_tts_models",
           side_effect=RuntimeError("sem chave"))
    def test_catalogo_tts_mantem_vozes_sem_api(self, _list_models):
        result = bridge._cmd_tts_catalog()
        self.assertEqual(result["models"], [])
        self.assertIn("Kore", result["gemini_voices"])
        self.assertEqual(result["catalog_error"], "sem chave")

    @patch("audiofy.providers.openrouter.list_tts_models")
    @patch("audiofy.catalog.load_models")
    def test_catalogo_separa_texto_e_fala(self, load_models, list_tts_models):
        load_models.return_value = [Model("v/text", "Texto", 1, 2, ("text",))]
        list_tts_models.return_value = [{
            "id": "v/voice", "name": "Voz",
            "prompt_price": "0.000001", "completion_price": "0.000002",
        }]
        result = bridge._cmd_models_list()
        self.assertEqual(result["text_models"][0]["id"], "v/text")
        self.assertEqual(result["tts_models"][0]["id"], "v/voice")
        self.assertIsNone(result["catalog_error"])


class SettingsInfoTest(unittest.TestCase):
    @patch("audiofy.providers.subscription.configured_model", return_value="gpt-test")
    @patch.dict("os.environ", {"AUDIOFY_TEXT_PROVIDER": "codex"})
    def test_informa_override_e_modelo_da_assinatura(self, _configured_model):
        result = bridge._cmd_settings_info()
        self.assertEqual(result["text_provider"], "codex")
        self.assertEqual(result["subscription_model"], "gpt-test")
        self.assertIn("AUDIOFY_TEXT_PROVIDER", result["overrides"])


class ChatHistoryContractTest(unittest.TestCase):
    @patch("audiofy.bridge._cmd_sources", return_value={"sources": [{"key": "custom"}]})
    @patch("audiofy.chat.ChatSession")
    def test_historico_inclui_fontes_esperadas_pelo_renderer(self, session, _sources):
        session.return_value.messages = [{"role": "user", "content": "oi"}]
        with patch("sys.argv", ["bridge", "chat-history", "principal"]), \
                patch("audiofy.bridge._emit") as emit:
            bridge.main()
        payload = emit.call_args.args[0]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["sources"], [{"key": "custom"}])


class ForcedGenerationTest(unittest.TestCase):
    @patch("audiofy.pipeline.generate_episode", return_value=Path("episode.mp3"))
    @patch("audiofy.bridge.get_source")
    def test_run_generation_repassa_force(self, get_source, generate_episode):
        get_source.return_value.get_item.return_value = object()
        result = bridge._cmd_run_generation("custom", "item", force=True)
        self.assertEqual(result, {"mp3": "episode.mp3"})
        self.assertTrue(generate_episode.call_args.kwargs["force"])

    def test_generate_inclui_force_no_subprocesso(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "episode"
            settings = Mock()
            with (
                patch("audiofy.bridge._episode_dir", return_value=directory),
                patch.object(bridge.GenerationTracker, "load", return_value=None),
                patch("audiofy.bridge.Settings", return_value=settings),
                patch("audiofy.bridge.subprocess.Popen") as popen,
            ):
                result = bridge._cmd_generate("custom", "item", force=True)
        settings.require_api_key.assert_called_once_with()
        self.assertTrue(result["started"])
        self.assertIn("--force", popen.call_args.args[0])


class EpisodeSummaryTest(unittest.TestCase):
    def test_status_expoe_retomada_sem_conteudo_da_fala(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            tracker = bridge.GenerationTracker(directory, "episodio")
            tracker.stage("tts", total=10, current=4)
            tracker.retrying(
                segment=5, next_attempt=2, max_attempts=5,
                delay_seconds=2, error="falha temporária",
            )
            summary = bridge._episode_summary(directory)

        self.assertEqual(summary["retry"]["segment"], 5)
        self.assertEqual(summary["progress"], {"current": 4, "total": 10})
        self.assertEqual(summary["last_error"], "falha temporária")


if __name__ == "__main__":
    unittest.main()
