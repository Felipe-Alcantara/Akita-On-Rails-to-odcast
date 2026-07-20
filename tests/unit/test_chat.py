"""Testes do chat de pesquisa: parsing de ações e persistência de sessão."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy.chat import ChatSession, _fix_json_newlines, parse_actions  # noqa: E402


class ParseActionsTest(unittest.TestCase):
    def test_resposta_sem_acao(self):
        text, actions = parse_actions("Só uma resposta normal.")
        self.assertEqual(text, "Só uma resposta normal.")
        self.assertEqual(actions, [])

    def test_resposta_com_acao(self):
        reply = (
            "Achei este artigo.\n\n```acao\n"
            '{"tipo": "adicionar_url", "url": "https://ex.com/a"}\n```'
        )
        text, actions = parse_actions(reply)
        self.assertEqual(text, "Achei este artigo.")
        self.assertEqual(actions[0]["tipo"], "adicionar_url")

    def test_multiplas_acoes(self):
        reply = (
            '```acao\n{"tipo": "buscar", "fonte": "akita", "termos": "ia"}\n```\n'
            '```acao\n{"tipo": "gerar", "fonte": "akita", "item_id": "x"}\n```'
        )
        _, actions = parse_actions(reply)
        self.assertEqual(len(actions), 2)

    def test_acao_com_json_invalido_e_ignorada(self):
        reply = "Texto.\n```acao\n{quebrado\n```"
        text, actions = parse_actions(reply)
        self.assertEqual(actions, [])
        self.assertEqual(text, "Texto.")

    def test_acao_desconhecida_ou_incompleta_e_ignorada(self):
        reply = (
            '```acao\n{"tipo": "apagar_tudo"}\n```\n'
            '```acao\n{"tipo": "gerar", "fonte": "akita"}\n```'
        )
        _, actions = parse_actions(reply)
        self.assertEqual(actions, [])

    def test_adicionar_texto_com_corpo_longo_e_aceito(self):
        corpo = "parágrafo. " * 2000  # bem acima do limite de 4096 dos campos curtos
        reply = (
            "```acao\n"
            + json.dumps({"tipo": "adicionar_texto", "titulo": "Tema pesquisado", "texto": corpo})
            + "\n```"
        )
        _, actions = parse_actions(reply)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["tipo"], "adicionar_texto")

    def test_adicionar_texto_sem_titulo_e_ignorado(self):
        reply = '```acao\n{"tipo": "adicionar_texto", "texto": "corpo"}\n```'
        _, actions = parse_actions(reply)
        self.assertEqual(actions, [])

    def test_newlines_literais_dentro_de_string_json(self):
        reply = (
            "Pronto.\n\n```acao\n"
            '{"tipo": "adicionar_texto", "titulo": "Art", "texto": "P1.\n\nP2.\n\nP3."}\n```'
        )
        _, actions = parse_actions(reply)
        self.assertEqual(len(actions), 1)
        self.assertIn("\n", actions[0]["texto"])

    def test_fix_json_newlines_preserva_json_valido(self):
        valid = '{"tipo": "buscar", "fonte": "akita", "termos": "ia"}'
        self.assertEqual(json.loads(_fix_json_newlines(valid)), json.loads(valid))

    def test_fix_json_newlines_preserva_escaped_newlines(self):
        raw = r'{"texto": "A\nB"}'
        result = json.loads(_fix_json_newlines(raw))
        self.assertEqual(result["texto"], "A\nB")

    def test_fix_json_newlines_corrige_newlines_literais(self):
        raw = '{"texto": "A\nB"}'
        result = json.loads(_fix_json_newlines(raw))
        self.assertEqual(result["texto"], "A\nB")

    def test_fix_json_newlines_preserva_aspas_escapadas(self):
        raw = r'{"texto": "disse \"olá\""}'
        result = json.loads(_fix_json_newlines(raw))
        self.assertEqual(result["texto"], 'disse "olá"')


class ChatSessionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.chat_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _fake_provider(self, reply: str):
        def call(system, user, settings):
            self.last_prompt = user
            return reply

        return call

    def test_envia_e_persiste(self):
        session = ChatSession("t", chat_dir=self.chat_dir)
        text, _ = session.send("Oi", None, call_provider=self._fake_provider("Olá!"))
        self.assertEqual(text, "Olá!")
        reloaded = ChatSession("t", chat_dir=self.chat_dir)
        self.assertEqual(len(reloaded.messages), 2)

    def test_historico_entra_no_prompt(self):
        session = ChatSession("t", chat_dir=self.chat_dir)
        session.send("Primeira", None, call_provider=self._fake_provider("R1"))
        session.send("Segunda", None, call_provider=self._fake_provider("R2"))
        self.assertIn("Primeira", self.last_prompt)
        self.assertIn("R1", self.last_prompt)

    def test_clear(self):
        session = ChatSession("t", chat_dir=self.chat_dir)
        session.send("Oi", None, call_provider=self._fake_provider("Olá"))
        session.clear()
        self.assertEqual(ChatSession("t", chat_dir=self.chat_dir).messages, [])

    def test_id_de_sessao_nao_permite_path_traversal(self):
        with self.assertRaisesRegex(ValueError, "ID da sessão"):
            ChatSession("../../outra-pasta", chat_dir=self.chat_dir)

    def test_mensagem_vazia_ou_excessiva_e_rejeitada(self):
        session = ChatSession("t", chat_dir=self.chat_dir)
        with self.assertRaises(ValueError):
            session.send("", None, call_provider=self._fake_provider("não chamado"))
        with self.assertRaises(ValueError):
            session.send("x" * 50_001, None, call_provider=self._fake_provider("não chamado"))

    def test_historico_nao_contem_blocos_acao_crus(self):
        reply = (
            "Achei.\n\n```acao\n"
            '{"tipo": "adicionar_url", "url": "https://ex.com"}\n```'
        )
        session = ChatSession("t", chat_dir=self.chat_dir)
        session.send("Busca", None, call_provider=self._fake_provider(reply))
        stored = session.messages[-1]["content"]
        self.assertNotIn("```acao", stored)
        self.assertEqual(stored, "Achei.")

    def test_prefixo_de_modo_e_removido_do_historico(self):
        session = ChatSession("t", chat_dir=self.chat_dir)
        session.send(
            "[MODO PESQUISA] inteligência artificial",
            None,
            call_provider=self._fake_provider("Pesquisei."),
        )
        stored = session.messages[-2]["content"]
        self.assertEqual(stored, "inteligência artificial")
        self.assertNotIn("[MODO", stored)

    def test_contexto_trunca_respostas_longas(self):
        long_reply = "A" * 2000
        session = ChatSession("t", chat_dir=self.chat_dir)
        session.send("Oi", None, call_provider=self._fake_provider(long_reply))
        transcript = session._transcript()
        self.assertIn("[…]", transcript)
        # O texto original de 2000 chars não deve aparecer inteiro no contexto
        self.assertLess(len(transcript), 1500)


if __name__ == "__main__":
    unittest.main()
