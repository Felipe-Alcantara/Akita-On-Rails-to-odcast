"""Testes da política reutilizável de backoff."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy.runtime.retry import RetryPolicy  # noqa: E402


class RetryPolicyTest(unittest.TestCase):
    @patch("audiofy.runtime.retry.random.uniform", return_value=0.5)
    def test_backoff_cresce_e_respeita_teto_com_jitter(self, _uniform):
        policy = RetryPolicy(5, base_delay_seconds=2, max_delay_seconds=5)
        self.assertEqual(policy.delay_after(1), 2.5)
        self.assertEqual(policy.delay_after(2), 4.5)
        self.assertEqual(policy.delay_after(3), 5)

    def test_rejeita_configuracao_invalida(self):
        with self.assertRaises(ValueError):
            RetryPolicy(0, base_delay_seconds=1, max_delay_seconds=2)


if __name__ == "__main__":
    unittest.main()
