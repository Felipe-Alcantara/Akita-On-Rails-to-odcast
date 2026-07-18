"""Testes da automação de qualidade do próprio repositório."""

import tempfile
import unittest
from pathlib import Path

from scripts.check_quality import validate_markdown_links


class MarkdownLinksTest(unittest.TestCase):
    def test_aceita_arquivo_existente_url_e_ancora(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docs").mkdir()
            (root / "docs" / "guia.md").write_text("# Guia\n", encoding="utf-8")
            (root / "README.md").write_text(
                "[Guia](docs/guia.md#uso) [Site](https://example.com) [Seção](#inicio)",
                encoding="utf-8",
            )

            validate_markdown_links(root, ["README.md"])

    def test_rejeita_destino_ausente(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("[Ausente](docs/ausente.md)", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "destino inexistente"):
                validate_markdown_links(root, ["README.md"])

    def test_rejeita_link_que_escapa_do_repositorio(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("[Fora](../fora.md)", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "escapa do repositório"):
                validate_markdown_links(root, ["README.md"])


if __name__ == "__main__":
    unittest.main()
