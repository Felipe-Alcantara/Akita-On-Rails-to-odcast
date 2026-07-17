"""Testes do registro de fontes de conteúdo (Open/Closed)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy.sources import available_sources, get_source  # noqa: E402
from audiofy.sources.base import ContentItem, ContentSource  # noqa: E402


class RegistryTest(unittest.TestCase):
    def test_akita_registrada(self):
        self.assertIn("akita", [s.key for s in available_sources()])

    def test_get_source_por_chave(self):
        source = get_source("akita")
        self.assertIsInstance(source, ContentSource)
        self.assertEqual(source.key, "akita")

    def test_get_source_desconhecida(self):
        with self.assertRaises(LookupError):
            get_source("nao-existe")

    def test_content_item_contrato(self):
        item = ContentItem(
            item_id="2026-07-08/x", title="X", url="https://exemplo.com/x",
            published_at="2026-07-08", text="corpo", words=1,
            attribution="Baseado em X",
        )
        self.assertEqual(item.item_id, "2026-07-08/x")


if __name__ == "__main__":
    unittest.main()
