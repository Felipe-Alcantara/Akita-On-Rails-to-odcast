"""Testes da fonte genérica de conteúdo (URL ou texto colado)."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy.security import validate_public_url  # noqa: E402
from audiofy.sources.custom import CustomSource, extract_main_text, slugify  # noqa: E402

HTML = """<html><head><title>Página de Teste — Blog</title></head><body>
<nav><a href="/">home</a><a href="/sobre">sobre</a></nav>
<article>
<h1>Título do Artigo</h1>
<p>Primeiro parágrafo com conteúdo relevante o bastante para contar como texto principal.</p>
<p>Segundo parágrafo, também com bastante texto para o extrator considerar.</p>
<script>alert('nunca no texto')</script>
</article>
<footer>rodapé © 2026</footer>
</body></html>"""


class ExtractTest(unittest.TestCase):
    def test_extrai_texto_do_article(self):
        title, text = extract_main_text(HTML)
        self.assertEqual(title, "Página de Teste — Blog")
        self.assertIn("Primeiro parágrafo", text)
        self.assertIn("Segundo parágrafo", text)

    def test_remove_script_e_navegacao(self):
        _, text = extract_main_text(HTML)
        self.assertNotIn("alert", text)
        self.assertNotIn("rodapé", text)

    def test_slugify(self):
        self.assertEqual(slugify("Olá, Mundo — Teste!"), "ola-mundo-teste")


class CustomSourceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.source = CustomSource(inbox_dir=Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_vazio(self):
        self.assertTrue(self.source.is_ready())
        self.assertEqual(self.source.list_items(), [])

    def test_adicionar_texto(self):
        item_id = self.source.add_text(
            "Meu Artigo", "Corpo do conteúdo.", url="https://exemplo.com/a"
        )
        items = self.source.list_items()
        self.assertEqual(len(items), 1)
        item = self.source.get_item(item_id)
        self.assertEqual(item.title, "Meu Artigo")
        self.assertIn("Corpo do conteúdo", item.text)
        self.assertIn("exemplo.com", item.attribution)

    def test_busca(self):
        self.source.add_text("Sobre Fingerprint", "corpo")
        self.source.add_text("Outro Assunto", "corpo")
        hits = self.source.search("fingerprint")
        self.assertEqual(len(hits), 1)

    def test_get_inexistente(self):
        with self.assertRaises(LookupError):
            self.source.get_item("nao-existe")

    def test_ids_unicos_para_titulos_iguais(self):
        first = self.source.add_text("Mesmo Título", "a")
        second = self.source.add_text("Mesmo Título", "b")
        self.assertNotEqual(first, second)

    def test_titulo_nao_injeta_novo_campo_no_frontmatter(self):
        item_id = self.source.add_text("Título\ndate: 1999-01-01", "corpo")
        item = self.source.get_item(item_id)
        self.assertEqual(item.title, "Título date: 1999-01-01")

    def test_item_id_nao_permite_escapar_da_caixa_de_entrada(self):
        with self.assertRaisesRegex(ValueError, "ID do conteúdo"):
            self.source.get_item("../../segredo")


class PublicUrlValidationTest(unittest.TestCase):
    @staticmethod
    def _resolver_for(ip):
        return lambda *_args, **_kwargs: [(2, 1, 6, "", (ip, 443))]

    def test_aceita_https_publico(self):
        url = validate_public_url(
            "https://example.com/artigo",
            resolver=self._resolver_for("93.184.216.34"),
        )
        self.assertEqual(url, "https://example.com/artigo")

    def test_rejeita_esquema_local_e_credenciais(self):
        with self.assertRaises(ValueError):
            validate_public_url("file:///etc/passwd", resolver=self._resolver_for("8.8.8.8"))
        with self.assertRaises(ValueError):
            validate_public_url(
                "https://user:secret@example.com",
                resolver=self._resolver_for("8.8.8.8"),
            )

    def test_rejeita_destino_de_rede_privada(self):
        with self.assertRaisesRegex(ValueError, "rede local"):
            validate_public_url(
                "http://localhost/admin",
                resolver=self._resolver_for("127.0.0.1"),
            )


if __name__ == "__main__":
    unittest.main()
