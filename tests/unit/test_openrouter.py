"""Classificação de falhas do adaptador OpenRouter para retry seguro."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy.providers.openrouter import OpenRouterError, _request  # noqa: E402


class OpenRouterRetryClassificationTest(unittest.TestCase):
    def setUp(self):
        self.settings = SimpleNamespace(require_api_key=lambda: "chave-de-teste")

    @patch("audiofy.providers.openrouter.time.sleep")
    @patch("audiofy.providers.openrouter.requests.request")
    def test_400_generico_do_provedor_tts_e_retomavel(self, request, _sleep):
        response = Mock(status_code=400, text='{"error":{"message":"Provider returned 400"}}')
        request.return_value = response

        with self.assertRaises(OpenRouterError) as raised:
            _request(self.settings, "POST", "/audio/speech", {"input": "fala"})

        self.assertTrue(raised.exception.retryable)
        self.assertEqual(raised.exception.status_code, 400)
        request.assert_called_once()

    @patch("audiofy.providers.openrouter.requests.request")
    def test_erro_de_autenticacao_nao_e_repetido(self, request):
        request.return_value = Mock(status_code=401, text="unauthorized")

        with self.assertRaises(OpenRouterError) as raised:
            _request(self.settings, "GET", "/credits")

        self.assertFalse(raised.exception.retryable)
        self.assertEqual(raised.exception.status_code, 401)
        request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
