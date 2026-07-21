"""Testes do contrato JSON compartilhado pelo Electron e por automações."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy import bridge  # noqa: E402
from audiofy.catalog import Model  # noqa: E402
from audiofy.estimates import EpisodeEstimate, EpisodeMetrics  # noqa: E402
from audiofy.profiles import Profile, profile_from_payload  # noqa: E402
from audiofy.sources.base import ContentItem  # noqa: E402


def _subscription_profile(subscription_model: str) -> Profile:
    """Perfil de assinatura para testes que não podem depender do disco."""
    return Profile(
        name="teste",
        text_model="(assinatura)",
        audit_model="(assinatura)",
        tts_model="vendor/tts",
        presenters_spec="narrador:Kore",
        text_provider="codex",
        subscription_model=subscription_model,
    )


class ProfilePayloadTest(unittest.TestCase):
    def test_openrouter_exige_e_preserva_modelos(self):
        profile = profile_from_payload(
            {
                "name": " meu ",
                "text_provider": "openrouter",
                "text_model": "vendor/text",
                "audit_model": "vendor/audit",
                "tts_model": "vendor/tts",
                "presenters_spec": "ana:Kore:curiosa",
            }
        )
        self.assertEqual(profile.name, "meu")
        self.assertEqual(profile.text_model, "vendor/text")

    def test_assinatura_normaliza_modelos_de_texto(self):
        profile = profile_from_payload(
            {
                "name": "assinante",
                "text_provider": "codex",
                "tts_model": "vendor/tts",
                "presenters_spec": "ana:Kore",
            }
        )
        self.assertEqual(profile.text_model, "(assinatura)")
        self.assertEqual(profile.audit_model, "(assinatura)")

    def test_rejeita_provedor_desconhecido(self):
        with self.assertRaisesRegex(ValueError, "Provedor"):
            profile_from_payload(
                {
                    "name": "inválido",
                    "text_provider": "qualquer-binario",
                    "tts_model": "vendor/tts",
                    "presenters_spec": "ana:Kore",
                }
            )

    def test_rejeita_lista_de_apresentadores_vazia(self):
        with self.assertRaisesRegex(ValueError, "apresentador"):
            profile_from_payload(
                {
                    "name": "sem-voz",
                    "text_model": "vendor/text",
                    "audit_model": "vendor/audit",
                    "tts_model": "vendor/tts",
                    "presenters_spec": "",
                }
            )

    def test_rejeita_nome_de_perfil_inseguro(self):
        with self.assertRaisesRegex(ValueError, "nome do perfil"):
            profile_from_payload(
                {
                    "name": "../../perfil",
                    "text_model": "vendor/text",
                    "audit_model": "vendor/audit",
                    "tts_model": "vendor/tts",
                    "presenters_spec": "ana:Kore",
                }
            )


class CatalogFallbackTest(unittest.TestCase):
    @patch("audiofy.providers.openrouter.list_tts_models", side_effect=RuntimeError("sem chave"))
    def test_catalogo_tts_mantem_vozes_sem_api(self, _list_models):
        result = bridge._cmd_tts_catalog()
        self.assertEqual(result["models"], [])
        self.assertIn("Kore", result["gemini_voices"])
        self.assertEqual(result["catalog_error"], "sem chave")


class GenerationLogTest(unittest.TestCase):
    def test_retorna_cauda_limitada_sanitizada_e_atividade_do_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            bridge.GenerationTracker(directory, "livro").stage("tts", total=12, current=4)
            log = ("linha antiga\n" * 8_000) + "chave sk-or-v1-segredomuitolongo\nTrecho 5/12\n"
            (directory / "generation.log").write_text(log, encoding="utf-8")
            with (
                patch("audiofy.bridge._episode_dir", return_value=directory),
                patch("audiofy.runtime.process.pid_alive", return_value=True),
            ):
                result = bridge._cmd_generation_log("livro")

        self.assertTrue(result["exists"])
        self.assertTrue(result["worker_alive"])
        self.assertTrue(result["truncated"])
        self.assertIn("Trecho 5/12", result["text"])
        self.assertNotIn("segredomuitolongo", result["text"])
        self.assertIn("[SEGREDO PROTEGIDO]", result["text"])
        self.assertLessEqual(len(result["text"].encode("utf-8")), 64 * 1024)

    def test_log_ausente_retorna_estado_previsivel(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("audiofy.bridge._episode_dir", return_value=Path(tmp)):
                result = bridge._cmd_generation_log("sem-log")

        self.assertFalse(result["exists"])
        self.assertEqual(result["text"], "")
        self.assertFalse(result["worker_alive"])


class AudioChunksTest(unittest.TestCase):
    @patch("audiofy.audio_audit.read_audio_audit")
    def test_lista_chunks_com_achados_sem_conteudo_de_audio(self, read_audit):
        read_audit.return_value = {
            "audited_at": "2026-07-19T10:00:00-03:00",
            "summary": {"segments": 1, "ok": 0, "warnings": 0, "critical": 1},
            "segments": [
                {
                    "file": "001.wav",
                    "duration_seconds": 10.0,
                    "severity": "critical",
                    "longest_silence_seconds": 6.0,
                    "silence_ratio": 0.6,
                    "silences": [],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            segments = directory / "segments"
            segments.mkdir()
            (segments / "001.wav").write_bytes(b"audio")
            (segments / "ignorar.txt").write_text("fora do contrato")
            (directory / "segments.json").write_text(
                json.dumps(
                    {
                        "source_key": "custom",
                        "generation_mode": "verbatim",
                        "segments": {
                            "001.wav": {
                                "kind": "chunk",
                                "chunk_index": 1,
                                "chunk_total": 8,
                                "speaker": "narrador",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            with patch("audiofy.bridge._episode_dir", return_value=directory):
                result = bridge._cmd_audio_chunks("item")

        self.assertEqual(len(result["chunks"]), 1)
        self.assertEqual(result["chunks"][0]["severity"], "critical")
        self.assertEqual(result["chunks"][0]["chunk_total"], 8)
        self.assertEqual(result["chunks"][0]["speaker"], "narrador")
        self.assertEqual(result["source_key"], "custom")
        self.assertEqual(result["audit"]["critical"], 1)


class CatalogContractTest(unittest.TestCase):
    @patch("audiofy.providers.openrouter.list_tts_models")
    @patch("audiofy.catalog.load_models")
    def test_catalogo_separa_texto_e_fala(self, load_models, list_tts_models):
        load_models.return_value = [Model("v/text", "Texto", 1, 2, ("text",))]
        list_tts_models.return_value = [
            {
                "id": "v/voice",
                "name": "Voz",
                "prompt_price": "0.000001",
                "completion_price": "0.000002",
            }
        ]
        result = bridge._cmd_models_list()
        self.assertEqual(result["text_models"][0]["id"], "v/text")
        self.assertEqual(result["tts_models"][0]["id"], "v/voice")
        self.assertIsNone(result["catalog_error"])


class SettingsInfoTest(unittest.TestCase):
    @patch("audiofy.providers.subscription.configured_model", return_value="gpt-test")
    @patch.dict("os.environ", {"AUDIOFY_TEXT_PROVIDER": "codex", "AUDIOFY_SUBSCRIPTION_MODEL": ""})
    def test_sem_modelo_no_perfil_reporta_o_configurado_na_cli(self, _configured_model):
        with patch("audiofy.config.profile_store") as store:
            store.return_value.active.return_value = _subscription_profile("")
            result = bridge._cmd_settings_info()
        self.assertEqual(result["text_provider"], "codex")
        self.assertEqual(result["subscription_model"], "gpt-test")
        self.assertEqual(result["profile_subscription_model"], "")
        self.assertIn("AUDIOFY_TEXT_PROVIDER", result["overrides"])

    @patch("audiofy.providers.subscription.configured_model", return_value="gpt-test")
    @patch.dict("os.environ", {"AUDIOFY_TEXT_PROVIDER": "codex", "AUDIOFY_SUBSCRIPTION_MODEL": ""})
    def test_modelo_do_perfil_vence_o_configurado_na_cli(self, _configured_model):
        with patch("audiofy.config.profile_store") as store:
            store.return_value.active.return_value = _subscription_profile("o3")
            result = bridge._cmd_settings_info()
        self.assertEqual(result["subscription_model"], "o3")
        self.assertEqual(result["profile_subscription_model"], "o3")

    def test_expoe_sugestoes_de_modelo_por_cli(self):
        result = bridge._cmd_settings_info()
        for cli in result["subscription_clis"]:
            self.assertTrue(cli["model_suggestions"], cli["key"])
            self.assertTrue(cli["supports_model"], cli["key"])

    def test_expoe_os_idiomas_do_registro_para_a_interface(self):
        result = bridge._cmd_settings_info()
        codes = [lang["code"] for lang in result["languages"]]
        self.assertIn("pt-BR", codes)
        self.assertIn("en", codes)
        for lang in result["languages"]:
            self.assertTrue(lang["label"])


class KeyManagementContractTest(unittest.TestCase):
    @patch("audiofy.config.api_key_source", return_value="trabalho")
    @patch("audiofy.config.key_store")
    def test_lista_informa_total_selecao_e_origem_efetiva(self, key_store, _source):
        named = Mock(name="trabalho", masked="sk-or-v1-abc…1234")
        named.name = "trabalho"
        store = key_store.return_value
        store.active_name.return_value = "trabalho"
        store.list_keys.return_value = [named]
        store.prefers_named.return_value = True

        result = bridge._cmd_keys_list()

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["effective_source"], "trabalho")
        self.assertTrue(result["keys"][0]["in_use"])
        self.assertEqual(result["keys"][0]["priority"], 1)

    @patch("audiofy.providers.openrouter.check_api_key_value")
    @patch("audiofy.config.key_store")
    def test_verifica_chave_nomeada_especifica(self, key_store, check):
        named = Mock(key="segredo-da-chave")
        key_store.return_value.get.return_value = named
        check.return_value = (True, "chave válida")

        result = bridge._cmd_check_named_key("trabalho")

        check.assert_called_once_with("segredo-da-chave")
        self.assertEqual(result, {"name": "trabalho", "available": True, "detail": "chave válida"})
        self.assertNotIn("segredo", str(result))

    @patch("audiofy.providers.openrouter.check_api_key_value")
    @patch("audiofy.config.environment_key_source", return_value=".env")
    def test_verifica_chave_do_ambiente_sem_devolver_segredo(self, _source, check):
        check.return_value = (True, "chave válida")
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "segredo-do-ambiente"}):
            result = bridge._cmd_check_environment_key()

        check.assert_called_once_with("segredo-do-ambiente")
        self.assertEqual(result, {"name": ".env", "available": True, "detail": "chave válida"})
        self.assertNotIn("segredo", str(result))

    @patch("audiofy.config.key_store")
    def test_usar_chave_nomeada_altera_a_selecao_persistida(self, key_store):
        result = bridge._cmd_use_named_key("trabalho")

        key_store.return_value.set_active.assert_called_once_with("trabalho")
        self.assertEqual(result, {"active": "trabalho"})

    @patch("audiofy.config.environment_key_source", return_value=".env")
    @patch("audiofy.config.key_store")
    def test_pode_voltar_para_chave_do_ambiente(self, key_store, _source):
        result = bridge._cmd_use_environment_key()

        key_store.return_value.use_environment.assert_called_once_with()
        self.assertEqual(result, {"active": ".env"})

    @patch("audiofy.config.environment_key_source", return_value=None)
    def test_nao_seleciona_ambiente_sem_chave_disponivel(self, _source):
        with self.assertRaisesRegex(RuntimeError, "Nenhuma OPENROUTER_API_KEY"):
            bridge._cmd_use_environment_key()

    @patch("audiofy.config.key_store")
    def test_reordena_fila_nomeada(self, key_store):
        result = bridge._cmd_move_named_key("reserva", "up")

        key_store.return_value.move.assert_called_once_with("reserva", "up")
        self.assertEqual(result, {"moved": "reserva", "direction": "up"})


class ChatHistoryContractTest(unittest.TestCase):
    @patch("audiofy.bridge._cmd_sources", return_value={"sources": [{"key": "custom"}]})
    @patch("audiofy.chat.ChatSession")
    def test_historico_inclui_fontes_esperadas_pelo_renderer(self, session, _sources):
        session.return_value.messages = [{"role": "user", "content": "oi"}]
        with (
            patch("sys.argv", ["bridge", "chat-history", "principal"]),
            patch("audiofy.bridge._emit") as emit,
        ):
            bridge.main()
        payload = emit.call_args.args[0]
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["sources"], [{"key": "custom"}])


class ForcedGenerationTest(unittest.TestCase):
    def test_opcoes_da_leitura_fiel_exigem_voz_conhecida(self):
        self.assertEqual(
            bridge._generation_options(["--mode=verbatim", "--voice=Sulafat", "--force"]),
            (True, "verbatim", "Sulafat", None, 0.08, "pt-BR"),
        )
        with self.assertRaisesRegex(ValueError, "voz de narrador"):
            bridge._generation_options(["--mode=verbatim"])

    @patch("audiofy.pipeline.generate_episode", return_value=Path("episode.mp3"))
    @patch("audiofy.bridge.get_source")
    def test_run_generation_repassa_force(self, get_source, generate_episode):
        get_source.return_value.get_item.return_value = object()
        result = bridge._cmd_run_generation("custom", "item", force=True)
        self.assertEqual(result, {"mp3": "episode.mp3"})
        self.assertTrue(generate_episode.call_args.kwargs["force"])
        self.assertEqual(generate_episode.call_args.kwargs["generation_mode"], "adaptation")

    def test_musica_e_validada_copiada_e_restrita_ao_cache_privado(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "trilha.mp3"
            source.write_bytes(b"audio")
            with (
                patch("audiofy.bridge.PROJECT_ROOT", root),
                patch("audiofy.bridge.STATE_DIR", root / ".audiofy"),
            ):
                relative, name = bridge._cache_background_music(str(source))
                cached = bridge._cached_background_path(relative)
                with self.assertRaisesRegex(ValueError, "cache privado"):
                    bridge._cached_background_path("trilha.mp3")
                self.assertEqual(cached.read_bytes(), b"audio")

        self.assertEqual(name, "trilha.mp3")
        self.assertTrue(relative.startswith(".audiofy/music/"))

    def test_opcoes_de_musica_limitam_volume(self):
        self.assertEqual(
            bridge._generation_options(
                ["--background-music=/tmp/trilha.mp3", "--background-volume=0.12"]
            ),
            (False, "adaptation", None, "/tmp/trilha.mp3", 0.12, "pt-BR"),
        )
        with self.assertRaisesRegex(ValueError, "1% e 25%"):
            bridge._generation_options(["--background-volume=0.5"])

    @patch("audiofy.pipeline.generate_episode", return_value=Path("livro.mp3"))
    @patch("audiofy.bridge.get_source")
    def test_worker_configura_um_narrador_e_preserva_modo(self, get_source, generate_episode):
        get_source.return_value.get_item.return_value = object()

        result = bridge._cmd_run_generation(
            "custom", "livro", generation_mode="verbatim", narration_voice="Sulafat"
        )

        settings = generate_episode.call_args.args[0]
        self.assertEqual(len(settings.presenters), 1)
        self.assertEqual(settings.presenters[0].voice, "Sulafat")
        self.assertEqual(generate_episode.call_args.kwargs["generation_mode"], "verbatim")
        self.assertEqual(result, {"mp3": "livro.mp3"})

    @patch("audiofy.pipeline.generate_episode", return_value=Path("livro.mp3"))
    @patch("audiofy.bridge._cached_background_path", return_value=Path("cache/trilha.mp3"))
    @patch("audiofy.bridge.get_source")
    def test_worker_repassa_musica_cacheada_e_volume(
        self, get_source, cached_background_path, generate_episode
    ):
        get_source.return_value.get_item.return_value = object()

        bridge._cmd_run_generation(
            "custom", "livro", background_music=".audiofy/music/hash.mp3", background_volume=0.12
        )

        cached_background_path.assert_called_once_with(".audiofy/music/hash.mp3")
        self.assertEqual(
            generate_episode.call_args.kwargs["background_music"], Path("cache/trilha.mp3")
        )
        self.assertEqual(generate_episode.call_args.kwargs["background_volume"], 0.12)

    @patch("audiofy.bridge.api_key_source", return_value="ambiente")
    def test_generate_inclui_force_no_subprocesso(self, _key_source):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "episode"
            settings = Mock()
            with (
                patch("audiofy.bridge._episode_dir", return_value=directory),
                patch("audiofy.bridge.Settings", return_value=settings),
                patch("audiofy.runtime.process.subprocess.Popen") as popen,
            ):
                result = bridge._cmd_generate("custom", "item", force=True)
            status = bridge.GenerationTracker.load(directory)
        settings.require_api_key.assert_called_once_with()
        self.assertTrue(result["started"])
        self.assertIn("--force", popen.call_args.args[0])
        self.assertEqual(status["state"], "rodando")
        self.assertEqual(status["stage"], "iniciando")
        self.assertEqual(status["key_source"], "ambiente")

    def test_generate_repassa_modo_e_voz_ao_subprocesso(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "livro"
            with (
                patch("audiofy.bridge._episode_dir", return_value=directory),
                patch("audiofy.bridge.Settings", return_value=Mock()),
                patch("audiofy.runtime.process.subprocess.Popen") as popen,
            ):
                result = bridge._cmd_generate(
                    "custom",
                    "livro",
                    generation_mode="verbatim",
                    narration_voice="Sulafat",
                )

            status = bridge.GenerationTracker.load(directory)
        command = popen.call_args.args[0]
        self.assertIn("--mode=verbatim", command)
        self.assertIn("--voice=Sulafat", command)
        self.assertEqual(result["generation_mode"], "verbatim")
        self.assertEqual(status["narration_voice"], "Sulafat")

    def test_worker_e_lancado_desanexado_de_forma_portatil(self):
        """O worker não pode usar start_new_session (POSIX-only) e travar no Windows."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "episode"
            with (
                patch("audiofy.bridge._episode_dir", return_value=directory),
                patch("audiofy.bridge.Settings", return_value=Mock()),
                patch("audiofy.runtime.process.subprocess.Popen") as popen,
                patch("audiofy.runtime.process.sys.platform", "win32"),
                patch("audiofy.runtime.process.subprocess.DETACHED_PROCESS", 8, create=True),
                patch(
                    "audiofy.runtime.process.subprocess.CREATE_NEW_PROCESS_GROUP", 512, create=True
                ),
            ):
                bridge._cmd_generate("custom", "item")
            self.assertNotIn("start_new_session", popen.call_args.kwargs)
            self.assertIn("creationflags", popen.call_args.kwargs)

    def test_worker_roda_com_utf8_forcado(self):
        """No Windows o worker herdaria cp1252 e os prints com emoji o derrubariam."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "episode"
            with (
                patch("audiofy.bridge._episode_dir", return_value=directory),
                patch("audiofy.bridge.Settings", return_value=Mock()),
                patch("audiofy.runtime.process.subprocess.Popen") as popen,
            ):
                bridge._cmd_generate("custom", "item")
            env = popen.call_args.kwargs["env"]
        self.assertEqual(env["PYTHONUTF8"], "1")
        self.assertEqual(env["PYTHONIOENCODING"], "utf-8")
        self.assertEqual(env["PYTHONUNBUFFERED"], "1")

    def test_rodando_orfao_nao_bloqueia_nova_geracao(self):
        """Worker morto com status 'rodando' era o que travava toda regeneração."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "episode"
            directory.mkdir(parents=True)
            import json as json_module

            (directory / "status.json").write_text(
                json_module.dumps(
                    {
                        "episode_id": "item",
                        "pid": 99999,
                        "state": "rodando",
                        "stage": "tts",
                        "cost_usd": 0,
                        "cost_exact": True,
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch("audiofy.bridge._episode_dir", return_value=directory),
                patch("audiofy.bridge.Settings", return_value=Mock()),
                patch("audiofy.runtime.process.pid_alive", return_value=False),
                patch("audiofy.runtime.process.subprocess.Popen") as popen,
            ):
                result = bridge._cmd_generate("custom", "item")
        self.assertTrue(result["started"])
        popen.assert_called_once()

    def test_abort_encerra_worker_ativo_e_informa_a_interface(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "episode"
            bridge.GenerationTracker(directory, "item").stage("tts", total=5, current=2)
            with (
                patch("audiofy.bridge._episode_dir", return_value=directory),
                patch.object(
                    bridge.GenerationTracker,
                    "abort_running",
                    return_value=(True, True),
                ) as abort_running,
            ):
                result = bridge._cmd_abort("item")

        self.assertTrue(result["aborted"])
        self.assertTrue(result["stopped"])
        self.assertIn("checkpoint", result["note"])
        abort_running.assert_called_once_with(directory)

    def test_falha_fora_do_pipeline_marca_status_falhou(self):
        """Erro antes do generate_episode (fonte, settings) não pode ficar mudo."""
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "episode"
            bridge.GenerationTracker.mark_starting(directory, "item")
            with (
                patch("audiofy.bridge._episode_dir", return_value=directory),
                patch("audiofy.bridge.get_source", side_effect=LookupError("fonte quebrada")),
            ):
                with self.assertRaises(LookupError):
                    bridge._cmd_run_generation("custom", "item")
            status = bridge.GenerationTracker.load(directory)
        self.assertEqual(status["state"], "falhou")
        self.assertIn("fonte quebrada", status["last_error"])

    def test_falha_ao_lancar_worker_fica_visivel_no_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "episode"
            settings = Mock()
            with (
                patch("audiofy.bridge._episode_dir", return_value=directory),
                patch("audiofy.bridge.Settings", return_value=settings),
                patch(
                    "audiofy.runtime.process.subprocess.Popen", side_effect=OSError("sem processo")
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "worker"):
                    bridge._cmd_generate("custom", "item")
            status = bridge.GenerationTracker.load(directory)

        self.assertEqual(status["state"], "falhou")
        self.assertEqual(status["stage"], "inicialização")
        self.assertIn("sem processo", status["last_error"])


class EpisodeSummaryTest(unittest.TestCase):
    def test_episodio_legado_com_mp3_e_metricas_e_catalogado_completo(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "2026-01-02-livro"
            directory.mkdir()
            (directory / "episode.mp3").write_bytes(b"x" * 2_048)
            (directory / "NOTES.md").write_text("# Meu livro\n", encoding="utf-8")
            EpisodeMetrics(
                source_words=1_000,
                script_words=900,
                duration_seconds=625.5,
                cost_usd=0.75,
                cost_exact=True,
                tts_model="vendor/tts",
                profile_name="narrador",
                generated_at="2026-01-03T12:30:00-03:00",
            ).write(directory)

            summary = bridge._episode_summary(directory)

        self.assertEqual(summary["state"], "concluido")
        self.assertEqual(summary["title"], "Meu livro")
        self.assertEqual(summary["source_created_at"], "2026-01-02")
        self.assertEqual(summary["generated_at"], "2026-01-03T12:30:00-03:00")
        self.assertEqual(summary["file_size_bytes"], 2_048)
        self.assertEqual(summary["duration_seconds"], 625.5)
        self.assertEqual(summary["cost_usd"], 0.75)
        self.assertTrue(summary["mp3"].endswith("episode.mp3"))

    def test_status_expoe_retomada_sem_conteudo_da_fala(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            tracker = bridge.GenerationTracker(directory, "episodio")
            tracker.stage("tts", total=10, current=4)
            tracker.retrying(
                segment=5,
                next_attempt=2,
                max_attempts=5,
                delay_seconds=2,
                error="falha temporária",
            )
            summary = bridge._episode_summary(directory)

        self.assertEqual(summary["retry"]["segment"], 5)
        self.assertEqual(summary["progress"], {"current": 4, "total": 10})
        self.assertEqual(summary["last_error"], "falha temporária")

    def test_mp3_parcial_nao_e_exposto_enquanto_montagem_esta_rodando(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            tracker = bridge.GenerationTracker(directory, "episodio")
            tracker.stage("montagem")
            (directory / "episode.mp3").write_bytes(b"parcial")

            running = bridge._episode_summary(directory)
            tracker.finish("concluido")
            completed = bridge._episode_summary(directory)

        self.assertIsNone(running["mp3"])
        self.assertTrue(completed["mp3"].endswith("episode.mp3"))


class ItemEstimateTest(unittest.TestCase):
    @patch("audiofy.estimates.read_episode_metrics", return_value=None)
    @patch("audiofy.estimates.estimate_episode")
    @patch("audiofy.bridge.Settings")
    @patch("audiofy.bridge.get_source")
    def test_item_expoe_media_faixa_duracao_e_amostra(
        self, get_source, settings, estimate_episode, _metrics
    ):
        get_source.return_value.get_item.return_value = ContentItem(
            item_id="item",
            title="Título",
            url="",
            published_at="2026-01-01",
            words=3_000,
            attribution="Fonte",
            text="conteúdo",
        )
        settings.return_value.tts_model = "vendor/tts"
        settings.return_value.profile_name = "gemini-duo-economico"
        estimate_episode.side_effect = [
            EpisodeEstimate(
                duration_minutes=20,
                duration_min_minutes=18,
                duration_max_minutes=22,
                speaking_rate_wpm=150,
                cost_usd=1.1,
                cost_min_usd=0.8,
                cost_max_usd=1.3,
                sample_count=2,
            ),
            EpisodeEstimate(
                duration_minutes=18,
                duration_min_minutes=16,
                duration_max_minutes=20,
                speaking_rate_wpm=165,
                cost_usd=0.9,
                cost_min_usd=0.7,
                cost_max_usd=1.1,
                sample_count=1,
            ),
            EpisodeEstimate(
                duration_minutes=22,
                duration_min_minutes=20,
                duration_max_minutes=24,
                speaking_rate_wpm=148,
                cost_usd=1.2,
                cost_min_usd=0.9,
                cost_max_usd=1.5,
                sample_count=0,
            ),
        ]

        result = bridge._cmd_item("custom", "item")

        self.assertEqual(result["estimated_cost_usd"], 1.1)
        self.assertEqual(result["estimate"]["sample_count"], 2)
        self.assertEqual(result["estimate"]["duration_minutes"], 20)
        self.assertEqual(result["estimates"]["verbatim"]["sample_count"], 1)
        self.assertEqual(result["estimates"]["reflexive"]["sample_count"], 0)
        self.assertEqual(
            [call.kwargs["generation_mode"] for call in estimate_episode.call_args_list],
            ["adaptation", "verbatim", "reflexive"],
        )


if __name__ == "__main__":
    unittest.main()
