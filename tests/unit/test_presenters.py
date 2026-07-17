"""Testes da configuração de apresentadores (1..N vozes)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from audiofy.presenters import Presenter, parse_presenters  # noqa: E402


class ParsePresentersTest(unittest.TestCase):
    def test_padrao_dois_apresentadores(self):
        presenters = parse_presenters("")
        self.assertEqual(len(presenters), 2)
        self.assertEqual(presenters[0], Presenter("apresentador_a", "Kore", "curioso"))
        self.assertEqual(presenters[1], Presenter("apresentador_b", "Puck", "didático"))

    def test_um_apresentador(self):
        presenters = parse_presenters("narrador:Kore")
        self.assertEqual(presenters, [Presenter("narrador", "Kore", "")])

    def test_tres_apresentadores_com_tom(self):
        spec = "ana:Kore:animada, beto:Puck:cético, carla:Aoede:técnica"
        presenters = parse_presenters(spec)
        self.assertEqual([p.speaker for p in presenters], ["ana", "beto", "carla"])
        self.assertEqual(presenters[1].style, "cético")

    def test_especificacao_invalida(self):
        with self.assertRaises(ValueError):
            parse_presenters("sem-voz")

    def test_nomes_duplicados(self):
        with self.assertRaises(ValueError):
            parse_presenters("ana:Kore, ana:Puck")

    def test_voz_por_speaker(self):
        presenters = parse_presenters("ana:Kore, beto:Puck")
        voices = {p.speaker: p.voice for p in presenters}
        self.assertEqual(voices["beto"], "Puck")


if __name__ == "__main__":
    unittest.main()
