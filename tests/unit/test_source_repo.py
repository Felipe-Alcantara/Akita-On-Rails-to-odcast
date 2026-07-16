"""Testes do parser de frontmatter e da listagem de artigos."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from akita_podcast.source_repo import parse_frontmatter, strip_frontmatter  # noqa: E402


ARTICLE = """---
title: "Um Artigo de Exemplo"
date: 2026-06-14T14:00:00-03:00
draft: false
tags:
  - exemplo
---

Corpo do artigo em **Markdown**.
"""


class ParseFrontmatterTest(unittest.TestCase):
    def test_extrai_chaves_simples(self):
        meta = parse_frontmatter(ARTICLE)
        self.assertEqual(meta["title"], "Um Artigo de Exemplo")
        self.assertEqual(meta["draft"], "false")

    def test_ignora_listas_aninhadas(self):
        meta = parse_frontmatter(ARTICLE)
        self.assertNotIn("- exemplo", meta.values())

    def test_sem_frontmatter_retorna_vazio(self):
        self.assertEqual(parse_frontmatter("# Só um título\n"), {})

    def test_strip_remove_somente_frontmatter(self):
        body = strip_frontmatter(ARTICLE)
        self.assertNotIn("draft:", body)
        self.assertIn("Corpo do artigo", body)

    def test_strip_preserva_texto_sem_frontmatter(self):
        text = "Parágrafo com --- traços no meio.\n"
        self.assertEqual(strip_frontmatter(text), text)

    def test_titulo_com_aspas_simples(self):
        meta = parse_frontmatter("---\ntitle: 'Outro Título'\n---\nCorpo.\n")
        self.assertEqual(meta["title"], "Outro Título")


if __name__ == "__main__":
    unittest.main()
