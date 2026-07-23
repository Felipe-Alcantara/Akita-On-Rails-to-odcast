"""Regressões da síntese retomável e idempotente por segmento."""

import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy.artifacts import final_audio_filename, segment_audio_filename  # noqa: E402
from audiofy.media import media_duration_seconds  # noqa: E402
from audiofy.pipeline import (  # noqa: E402
    _assemble,
    _chat_with_key_fallback,
    _concat_line,
    _exhaustion_label,
    _prepare_verbatim_turns,
    _synthesize_turns,
    _wait_for_retry,
)
from audiofy.presenters import Presenter  # noqa: E402
from audiofy.providers.openrouter import OpenRouterError, SpeechResult  # noqa: E402
from audiofy.runtime.status import GenerationAborted, GenerationTracker  # noqa: E402


def _settings(max_attempts: int = 3) -> SimpleNamespace:
    return SimpleNamespace(
        presenters=[Presenter("ana", "Kore", "natural")],
        tts_model="vendor/tts",
        tts_format="pcm",
        tts_sample_rate=24_000,
        tts_retry_attempts=max_attempts,
        tts_retry_base_seconds=0,
        tts_retry_max_seconds=0,
        language="pt-BR",
    )


def _valid_wav(path: Path) -> bytes:
    pcm = b"\x00\x00" * 300
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24_000)
        audio.writeframes(pcm)
    return pcm


def _segment_path(directory: Path, index: int, total: int) -> Path:
    return (
        directory
        / "segments"
        / segment_audio_filename(
            "conteudo", directory.name, "adaptation", index, total, "ana", "wav"
        )
    )


class ResumableSynthesisTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self._tmp.name)
        self.tracker = GenerationTracker(self.directory, "episodio")

    def tearDown(self):
        self._tmp.cleanup()

    @patch("audiofy.pipeline.openrouter.generation_cost_usd", return_value=0.012)
    @patch("audiofy.pipeline.openrouter.text_to_speech")
    def test_retomada_pula_segmento_pronto_e_repete_apenas_o_que_falhou(
        self, text_to_speech, _generation_cost
    ):
        segments = self.directory / "segments"
        segments.mkdir()
        first = segments / "001_ana.wav"
        _valid_wav(first)
        original = first.read_bytes()
        text_to_speech.side_effect = [
            OpenRouterError("Provider returned 400", retryable=True),
            SpeechResult(b"\x00\x00" * 300, "gen-2"),
        ]

        paths = _synthesize_turns(
            _settings(),
            self.directory,
            [{"speaker": "ana", "text": "já pronto"}, {"speaker": "ana", "text": "retomar daqui"}],
            self.tracker,
        )

        self.assertEqual(text_to_speech.call_count, 2)
        self.assertEqual(paths[0].read_bytes(), original)
        self.assertTrue(paths[1].is_file())
        status = GenerationTracker.load(self.directory)
        self.assertEqual(status["progress"], {"current": 2, "total": 2})
        self.assertIsNone(status["retry"])
        manifest = json.loads((self.directory / "segments.json").read_text(encoding="utf-8"))
        self.assertEqual(set(manifest["segments"]), {path.name for path in paths})
        self.assertEqual(manifest["segments"][paths[1].name]["generation_id"], "gen-2")
        self.assertEqual(manifest["segments"][paths[1].name]["cost_usd"], 0.012)
        self.assertEqual(status["cost_usd"], 0.012)

    @patch("audiofy.pipeline.openrouter.generation_cost_usd")
    @patch("audiofy.pipeline.openrouter.text_to_speech")
    def test_limite_de_tentativas_preserva_o_ultimo_checkpoint(
        self, text_to_speech, _generation_cost
    ):
        segments = self.directory / "segments"
        segments.mkdir()
        _valid_wav(segments / "001_ana.wav")
        text_to_speech.side_effect = OpenRouterError("indisponível", retryable=True)

        with self.assertRaisesRegex(OpenRouterError, "indisponível"):
            _synthesize_turns(
                _settings(max_attempts=2),
                self.directory,
                [{"speaker": "ana", "text": "preservado"}, {"speaker": "ana", "text": "falha"}],
                self.tracker,
            )

        self.assertEqual(text_to_speech.call_count, 2)
        self.assertTrue(_segment_path(self.directory, 1, 2).is_file())
        self.assertFalse(_segment_path(self.directory, 2, 2).exists())
        self.assertFalse(_segment_path(self.directory, 2, 2).with_suffix(".wav.tmp").exists())
        status = GenerationTracker.load(self.directory)
        self.assertEqual(status["progress"], {"current": 1, "total": 2})

    @patch("audiofy.pipeline.openrouter.generation_cost_usd")
    @patch("audiofy.pipeline.openrouter.text_to_speech")
    def test_erro_permanente_nao_e_repetido(self, text_to_speech, _generation_cost):
        text_to_speech.side_effect = OpenRouterError("chave inválida", retryable=False)

        with self.assertRaisesRegex(OpenRouterError, "chave inválida"):
            _synthesize_turns(
                _settings(max_attempts=5),
                self.directory,
                [{"speaker": "ana", "text": "fala"}],
                self.tracker,
            )

        text_to_speech.assert_called_once()

    @patch("audiofy.pipeline.openrouter.generation_cost_usd", return_value=0.01)
    @patch(
        "audiofy.pipeline.openrouter.text_to_speech",
        return_value=SpeechResult(b"\x00\x00" * 300, "gen-1"),
    )
    def test_manifesto_invalida_audio_quando_modelo_muda(self, text_to_speech, _generation_cost):
        turns = [{"speaker": "ana", "text": "mesma fala"}]
        first_settings = _settings()
        _synthesize_turns(first_settings, self.directory, turns, self.tracker)
        original_calls = text_to_speech.call_count

        changed_settings = _settings()
        changed_settings.tts_model = "vendor/tts-novo"
        resumed = GenerationTracker(self.directory, "episodio")
        _synthesize_turns(changed_settings, self.directory, turns, resumed)

        self.assertEqual(text_to_speech.call_count, original_calls + 1)

    @patch("audiofy.pipeline.openrouter.generation_cost_usd", return_value=0.01)
    @patch(
        "audiofy.pipeline.openrouter.text_to_speech",
        return_value=SpeechResult(b"\x00\x00" * 300, "gen-direcao"),
    )
    def test_turno_pode_fornecer_direcao_vocal_sem_alterar_texto(
        self, text_to_speech, _generation_cost
    ):
        _synthesize_turns(
            _settings(),
            self.directory,
            [{"speaker": "ana", "text": "Texto literal.", "instructions": "Suspense lento."}],
            self.tracker,
        )

        call = text_to_speech.call_args
        self.assertEqual(call.args[1], "Texto literal.")
        self.assertEqual(call.kwargs["instructions"], "Suspense lento.")

    @patch("audiofy.pipeline.estimate_tts_cost", return_value=0.02)
    @patch(
        "audiofy.pipeline.openrouter.generation_cost_usd",
        side_effect=OpenRouterError("metadado atrasado"),
    )
    @patch(
        "audiofy.pipeline.openrouter.text_to_speech",
        return_value=SpeechResult(b"\x00\x00" * 300, "gen-atrasada"),
    )
    def test_fallback_local_nao_consulta_conta_global_e_marca_aproximacao(
        self, _text_to_speech, _generation_cost, estimate_cost
    ):
        _synthesize_turns(
            _settings(),
            self.directory,
            [{"speaker": "ana", "text": "fala"}],
            self.tracker,
        )

        status = GenerationTracker.load(self.directory)
        manifest = json.loads((self.directory / "segments.json").read_text(encoding="utf-8"))
        entry = next(iter(manifest["segments"].values()))
        self.assertEqual(status["cost_usd"], 0.02)
        self.assertFalse(status["cost_exact"])
        self.assertFalse(entry["cost_exact"])
        estimate_cost.assert_called_once()

    @patch("audiofy.pipeline.api_key_candidates")
    @patch("audiofy.pipeline.openrouter.generation_cost_usd", return_value=0.01)
    @patch("audiofy.pipeline.openrouter.text_to_speech")
    def test_tenta_proxima_chave_quando_a_atual_atinge_limite(
        self, text_to_speech, _generation_cost, candidates
    ):
        first = _settings()
        first.api_key = "sk-or-chave-antiga"
        second = _settings()
        second.api_key = "sk-or-chave-disponivel"
        candidates.return_value = [("antiga", first), ("disponivel", second)]
        text_to_speech.side_effect = [
            OpenRouterError("Key limit exceeded", status_code=403),
            SpeechResult(b"\x00\x00" * 300, "gen-fallback"),
        ]

        _synthesize_turns(
            first,
            self.directory,
            [{"speaker": "ana", "text": "usa a alternativa"}],
            self.tracker,
        )

        self.assertEqual(text_to_speech.call_count, 2)
        self.assertEqual(text_to_speech.call_args_list[0].args[0].api_key, "sk-or-chave-antiga")
        self.assertEqual(text_to_speech.call_args_list[1].args[0].api_key, "sk-or-chave-disponivel")
        manifest = json.loads((self.directory / "segments.json").read_text(encoding="utf-8"))
        self.assertEqual(next(iter(manifest["segments"].values()))["key_label"], "disponivel")
        self.assertEqual(GenerationTracker.load(self.directory)["key_source"], "disponivel")

    @patch("audiofy.pipeline.api_key_candidates")
    @patch("audiofy.pipeline.openrouter.generation_cost_usd", return_value=0.01)
    @patch("audiofy.pipeline.openrouter.text_to_speech")
    def test_creditos_402_tambem_avancam_na_fila(
        self, text_to_speech, _generation_cost, candidates
    ):
        first, second = _settings(), _settings()
        first.api_key = "sk-or-sem-saldo"
        second.api_key = "sk-or-reserva"
        candidates.return_value = [("primeira", first), ("reserva", second)]
        text_to_speech.side_effect = [
            OpenRouterError("Insufficient credits", status_code=402),
            SpeechResult(b"\x00\x00" * 300, "gen-reserva"),
        ]

        _synthesize_turns(
            first,
            self.directory,
            [{"speaker": "ana", "text": "usa a reserva"}],
            self.tracker,
        )

        self.assertEqual(text_to_speech.call_count, 2)
        self.assertEqual(GenerationTracker.load(self.directory)["key_source"], "reserva")

    @patch("audiofy.pipeline.api_key_candidates")
    @patch("audiofy.pipeline.openrouter.chat_json")
    def test_texto_openrouter_tambem_avanca_na_fila(self, chat_json, candidates):
        first, second = _settings(), _settings()
        candidates.return_value = [("primeira", first), ("reserva", second)]
        expected = SimpleNamespace(data={"ok": True}, cost_usd=0.01)
        chat_json.side_effect = [
            OpenRouterError("Insufficient credits", status_code=402),
            expected,
        ]

        result = _chat_with_key_fallback(first, "vendor/model", "sistema", "prompt", self.tracker)

        self.assertIs(result, expected)
        self.assertEqual(chat_json.call_count, 2)
        self.assertEqual(GenerationTracker.load(self.directory)["key_source"], "reserva")

    def test_exhaustion_label_diferencia_402_de_403(self):
        err_402 = OpenRouterError("Insufficient credits", status_code=402)
        err_403 = OpenRouterError("Key limit exceeded", status_code=403)
        self.assertIn("saldo", _exhaustion_label(err_402))
        self.assertIn("limite", _exhaustion_label(err_403))

    def test_abort_interrompe_espera_antes_do_proximo_retry(self):
        self.tracker.stage("tts", total=2, current=1)
        GenerationTracker.request_abort(self.directory)

        with self.assertRaises(GenerationAborted):
            _wait_for_retry(30, self.tracker)

        self.assertEqual(GenerationTracker.load(self.directory)["state"], "abortado")


class AtomicAssemblyTest(unittest.TestCase):
    @patch("audiofy.pipeline.run_tool")
    def test_mp3_so_substitui_final_depois_do_ffmpeg(self, run_tool):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            segment = directory / "001.wav"
            _valid_wav(segment)
            old = directory / "episode.mp3"
            old.write_bytes(b"versao-anterior")
            expected = directory / final_audio_filename("conteudo", directory.name, "adaptation")

            def create_output(name, arguments, **_kwargs):
                self.assertEqual(name, "ffmpeg")
                self.assertEqual(expected.read_bytes(), b"versao-anterior")
                Path(arguments[-1]).write_bytes(b"versao-nova")

            run_tool.side_effect = create_output
            result = _assemble(
                directory,
                [segment],
                SimpleNamespace(title="Episódio", attribution="Fonte"),
            )

            self.assertEqual(result, expected)
            self.assertEqual(expected.read_bytes(), b"versao-nova")
            self.assertFalse(old.exists())
            self.assertFalse(expected.with_name(f"{expected.stem}.tmp.mp3").exists())
            self.assertIn("timeout", run_tool.call_args.kwargs)

    def test_assemble_sem_segmentos_falha_em_vez_de_montar_vazio(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "segmento"):
                _assemble(Path(tmp), [], SimpleNamespace(title="x", attribution="y"))

    @patch("audiofy.pipeline.run_tool")
    def test_mistura_musica_baixa_ate_o_fim_da_narracao_e_audita_mix(self, run_tool):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            segment = directory / "001.wav"
            music = directory / "trilha.mp3"
            _valid_wav(segment)
            music.write_bytes(b"musica")

            def create_output(_name, arguments, **_kwargs):
                Path(arguments[-1]).write_bytes(b"mix")

            run_tool.side_effect = create_output
            _assemble(
                directory,
                [segment],
                SimpleNamespace(title="Episódio", attribution="Fonte"),
                music,
                0.08,
            )

            arguments = run_tool.call_args.args[1]
            manifest = json.loads((directory / "mix.json").read_text(encoding="utf-8"))

        self.assertIn("-stream_loop", arguments)
        self.assertIn("[0:a][music]amix=inputs=2:duration=first", " ".join(arguments))
        self.assertIn("[1:a]volume=0.0800", " ".join(arguments))
        self.assertIn("[mixed]loudnorm=I=-16", " ".join(arguments))
        self.assertEqual(manifest["background_music"], "trilha.mp3")
        self.assertEqual(manifest["background_volume"], 0.08)
        self.assertEqual(len(manifest["background_sha256"]), 64)


class VerbatimPreparationTest(unittest.TestCase):
    def test_planeja_em_lotes_preserva_texto_e_reaproveita_cache(self):
        text = ("Capítulo um. O perigo aumentava lentamente...\n\n" * 150) + "Fim."
        item = SimpleNamespace(text=text, title="Livro de Teste")
        analyzer = Mock(
            return_value={
                "segments": [
                    {"id": index, "direction": f"direção {index}", "text": "reescrito"}
                    for index in range(1, 20)
                ]
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            tracker = GenerationTracker(directory, "livro", generation_mode="verbatim")

            turns = _prepare_verbatim_turns(_settings(), item, directory, tracker, False, analyzer)

            cached_analyzer = Mock()
            resumed = GenerationTracker(directory, "livro", generation_mode="verbatim")
            cached_turns = _prepare_verbatim_turns(
                _settings(), item, directory, resumed, False, cached_analyzer
            )

            script = json.loads((directory / "narration-script.json").read_text(encoding="utf-8"))
        self.assertEqual("".join(t["text"] for t in turns if t.get("kind") != "intro"), text)
        self.assertEqual(cached_turns, turns)
        self.assertEqual(script["mode"], "verbatim")
        self.assertNotIn("reescrito", str(turns))
        analyzer.assert_called_once()
        cached_analyzer.assert_not_called()


class FailureIsNeverSilentTest(unittest.TestCase):
    """Uma falha na montagem (ex.: ffmpeg ausente) deve virar estado 'falhou',
    nunca deixar o status preso em 'rodando' — a origem do travamento no Windows."""

    @patch("audiofy.pipeline._run")
    def test_erro_na_montagem_marca_falhou_e_nao_fica_rodando(self, run):
        from audiofy.pipeline import episode_dir, generate_episode
        from audiofy.runtime.process import ToolNotFoundError

        run.side_effect = ToolNotFoundError("'ffmpeg' não foi encontrado no PATH.")
        item = SimpleNamespace(
            item_id="ep-falha",
            title="t",
            published_at="",
            text="x",
            words=1,
            url="",
            attribution="a",
        )
        with tempfile.TemporaryDirectory() as tmp:
            with patch("audiofy.pipeline.EPISODES_DIR", Path(tmp)):
                with self.assertRaises(ToolNotFoundError):
                    generate_episode(_settings(), item)
                status = GenerationTracker.load(episode_dir("ep-falha"))
        self.assertEqual(status["state"], "falhou")
        self.assertIn("ffmpeg", status["last_error"])


class TrechoSemAudioTest(unittest.TestCase):
    """Um trecho que o TTS não consegue pronunciar não pode derrubar o episódio.

    Caso real: um PDF de livro deixou um rodapé de diagramação sozinho num
    trecho; o TTS devolvia resposta vazia, as 5 tentativas falhavam igual e a
    geração morria depois de 14 falas já pagas.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.directory = Path(self._tmp.name)
        self.tracker = GenerationTracker(self.directory, "episodio")
        self.addCleanup(self._tmp.cleanup)

    def _turns(self, quantidade):
        return [{"speaker": "ana", "text": f"fala {n}"} for n in range(1, quantidade + 1)]

    @patch("audiofy.pipeline.openrouter.generation_cost_usd", return_value=0.01)
    @patch("audiofy.pipeline.openrouter.text_to_speech")
    def test_pula_o_trecho_sem_audio_e_conclui_os_demais(self, text_to_speech, _cost):
        vazio = OpenRouterError("TTS retornou resposta vazia ou curta demais.", retryable=True)
        text_to_speech.side_effect = [
            SpeechResult(b"\x00\x00" * 300, "gen-1"),
            *[vazio] * 3,  # esgota as tentativas do trecho 2
            SpeechResult(b"\x00\x00" * 300, "gen-3"),
        ]

        paths = _synthesize_turns(_settings(), self.directory, self._turns(3), self.tracker)

        self.assertEqual(len(paths), 2, "o trecho sem áudio não entra na montagem")
        self.assertTrue(all(path.is_file() for path in paths))
        status = GenerationTracker.load(self.directory)
        self.assertEqual(status["state"], "rodando")

    @patch("audiofy.pipeline.openrouter.text_to_speech")
    def test_erro_diferente_continua_derrubando_a_geracao(self, text_to_speech):
        text_to_speech.side_effect = OpenRouterError("Provider returned 500", retryable=False)
        with self.assertRaises(OpenRouterError):
            _synthesize_turns(_settings(), self.directory, self._turns(2), self.tracker)

    @patch("audiofy.pipeline.openrouter.text_to_speech")
    def test_nenhum_trecho_com_audio_vira_erro_explicito(self, text_to_speech):
        text_to_speech.side_effect = OpenRouterError(
            "TTS retornou resposta vazia ou curta demais.", retryable=True
        )
        with self.assertRaisesRegex(ValueError, "Nenhuma fala gerou áudio"):
            _synthesize_turns(_settings(), self.directory, self._turns(2), self.tracker)


class ConcatLineTest(unittest.TestCase):
    def test_usa_barras_normais_para_o_ffmpeg(self):
        line = _concat_line(Path("/tmp/ep/001.wav"))
        self.assertNotIn("\\", line)
        self.assertTrue(line.startswith("file '"))
        self.assertTrue(line.endswith("'\n"))

    def test_escapa_aspas_simples_no_caminho(self):
        line = _concat_line(Path("/tmp/ep's/001.wav"))
        self.assertIn(r"'\''", line)


class MediaDurationTest(unittest.TestCase):
    def test_wav_com_taxa_invalida_falha_claramente(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.wav"
            with wave.open(str(path), "wb") as audio:
                audio.setnchannels(1)
                audio.setsampwidth(2)
                audio.setframerate(24_000)
                audio.writeframes(b"\x00\x00")
            # força framerate 0 relendo com patch do resultado
            with patch("audiofy.media.wave.open") as wave_open:
                handle = wave_open.return_value.__enter__.return_value
                handle.getframerate.return_value = 0
                handle.getnframes.return_value = 10
                with self.assertRaisesRegex(ValueError, "taxa de amostragem"):
                    media_duration_seconds(path)

    @patch("audiofy.media.run_tool")
    def test_mp3_com_saida_nao_numerica_falha_claramente(self, run_tool):
        run_tool.return_value = SimpleNamespace(stdout="N/A\n")
        with self.assertRaisesRegex(ValueError, "duração"):
            media_duration_seconds(Path("episode.mp3"))


if __name__ == "__main__":
    unittest.main()
