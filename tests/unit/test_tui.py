"""Testes dos componentes compartilhados da interface de terminal."""

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy import tui  # noqa: E402


class TuiInputTest(unittest.TestCase):
    @patch("audiofy.tui.questionary.text")
    def test_texto_multilinha_mantem_estilo_e_instrucao_de_saida(self, prompt):
        question = Mock()
        question.ask.return_value = "linha 1\nlinha 2"
        prompt.return_value = question

        result = tui.multiline_text("Cole o conteúdo:")

        self.assertEqual(result, "linha 1\nlinha 2")
        self.assertTrue(prompt.call_args.kwargs["multiline"])
        self.assertIn("Alt+Enter", prompt.call_args.kwargs["instruction"])
        self.assertIs(prompt.call_args.kwargs["style"], tui._STYLE)


if __name__ == "__main__":
    unittest.main()
