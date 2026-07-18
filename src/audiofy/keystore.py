"""Cofre de chaves nomeadas do OpenRouter (padrão portado do Openia).

Decisões de segurança:
- as chaves nunca aparecem em código nem em arquivo versionado;
- persistem em `.audiofy/keys.json` com permissão 0600 no Unix (o `.audiofy/`
  está no .gitignore); no Windows a permissão não se aplica e o usuário é avisado;
- a variável de ambiente `OPENROUTER_API_KEY` (inclusive via .env) tem prioridade
  sobre o cofre, para uso temporário em CI/sessões.

Suporta várias chaves nomeadas ("pessoal", "trabalho"…) com uma marcada como ativa.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

ENV_VAR = "OPENROUTER_API_KEY"


@dataclass(frozen=True)
class NamedKey:
    name: str
    key: str

    @property
    def masked(self) -> str:
        return f"{self.key[:12]}…{self.key[-4:]}"


def validate_api_key(key: str) -> str:
    """Rejeita entradas obviamente inválidas (validação real acontece na API)."""
    key = key.strip()
    if not key:
        raise ValueError("a chave não pode ser vazia")
    if not key.startswith("sk-or-"):
        raise ValueError("isso não parece uma chave do OpenRouter (o esperado começa com 'sk-or-')")
    if len(key) < 20:
        raise ValueError("a chave parece curta demais para ser válida")
    return key


def validate_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("o nome não pode ser vazio")
    if len(name) > 40:
        raise ValueError("o nome é longo demais (máx. 40 caracteres)")
    return name


class KeyStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict = {"active": None, "keys": {}}
        if path.is_file():
            self._data = json.loads(path.read_text(encoding="utf-8"))

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        if os.name != "nt":
            self.path.chmod(0o600)

    # ── Operações ────────────────────────────────────────────────────────

    def add(self, name: str, key: str) -> None:
        """Adiciona (ou sobrescreve) uma chave; a primeira vira a ativa."""
        name, key = validate_name(name), validate_api_key(key)
        self._data["keys"][name] = key
        if self._data["active"] is None:
            self._data["active"] = name
        self._flush()

    def remove(self, name: str) -> None:
        self._data["keys"].pop(name, None)
        if self._data["active"] == name:
            remaining = sorted(self._data["keys"])
            self._data["active"] = remaining[0] if remaining else None
        self._flush()

    def set_active(self, name: str) -> None:
        if name not in self._data["keys"]:
            raise LookupError(f"Chave '{name}' não existe no cofre.")
        self._data["active"] = name
        self._flush()

    # ── Consulta ─────────────────────────────────────────────────────────

    def list_keys(self) -> list[NamedKey]:
        return [NamedKey(name, key) for name, key in sorted(self._data["keys"].items())]

    def active_name(self) -> str | None:
        return self._data["active"]

    def active_key(self) -> str | None:
        name = self._data["active"]
        return self._data["keys"].get(name) if name else None

    def resolve(self) -> str | None:
        """Chave efetiva: env var (inclusive .env) tem prioridade sobre o cofre."""
        return os.environ.get(ENV_VAR) or self.active_key()
