"""Cofre de chaves nomeadas do OpenRouter (padrão portado do Openia).

Decisões de segurança:
- as chaves nunca aparecem em código nem em arquivo versionado;
- persistem em `.audiofy/keys.json` com permissão 0600 no Unix (o `.audiofy/`
  está no .gitignore); no Windows a permissão não se aplica e o usuário é avisado;
- a variável de ambiente `OPENROUTER_API_KEY` (inclusive via .env) tem prioridade
  por padrão, para uso temporário em CI/sessões;
- uma escolha explícita na interface pode usar uma chave nomeada até a pessoa
  voltar a selecionar a origem de ambiente.

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
        self._data: dict = {"active": None, "source": "environment", "keys": {}, "order": []}
        if path.is_file():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self._data.update(loaded)
        if self._data.get("source") not in {"environment", "named"}:
            self._data["source"] = "environment"
        known = self._data.get("keys", {})
        stored_order = self._data.get("order", [])
        self._data["order"] = [name for name in stored_order if name in known]
        self._data["order"].extend(name for name in known if name not in self._data["order"])

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
        if name not in self._data["order"]:
            self._data["order"].append(name)
        if self._data["active"] is None:
            self._data["active"] = name
        self._flush()

    def remove(self, name: str) -> None:
        self._data["keys"].pop(name, None)
        if name in self._data["order"]:
            self._data["order"].remove(name)
        if self._data["active"] == name:
            remaining = self._data["order"]
            self._data["active"] = remaining[0] if remaining else None
            if not remaining:
                self._data["source"] = "environment"
        self._flush()

    def set_active(self, name: str) -> None:
        """Seleciona e passa a usar uma chave nomeada, mesmo se houver variável de ambiente."""
        if name not in self._data["keys"]:
            raise LookupError(f"Chave '{name}' não existe no cofre.")
        self._data["active"] = name
        self._data["source"] = "named"
        self._data["order"].remove(name)
        self._data["order"].insert(0, name)
        self._flush()

    def move(self, name: str, direction: str) -> None:
        """Move uma chave na fila de fallback e mantém a prioridade 1 como ativa."""
        if name not in self._data["keys"]:
            raise LookupError(f"Chave '{name}' não existe no cofre.")
        if direction not in {"up", "down"}:
            raise ValueError("A direção precisa ser 'up' ou 'down'.")
        index = self._data["order"].index(name)
        target = index + (-1 if direction == "up" else 1)
        if 0 <= target < len(self._data["order"]):
            self._data["order"][index], self._data["order"][target] = (
                self._data["order"][target],
                self._data["order"][index],
            )
        if self._data.get("source") == "named" and self._data["order"]:
            self._data["active"] = self._data["order"][0]
        self._flush()

    def use_environment(self) -> None:
        """Volta à prioridade segura da chave fornecida pelo ambiente ou pelo ``.env``."""
        self._data["source"] = "environment"
        self._flush()

    # ── Consulta ─────────────────────────────────────────────────────────

    def list_keys(self) -> list[NamedKey]:
        return [NamedKey(name, self._data["keys"][name]) for name in self._data["order"]]

    def get(self, name: str) -> NamedKey:
        try:
            return NamedKey(name, self._data["keys"][name])
        except KeyError as error:
            raise LookupError(f"Chave '{name}' não existe no cofre.") from error

    def active_name(self) -> str | None:
        return self._data["active"]

    def active_key(self) -> str | None:
        name = self._data["active"]
        return self._data["keys"].get(name) if name else None

    def prefers_named(self) -> bool:
        return self._data.get("source") == "named" and self.active_key() is not None

    def resolve(self) -> str | None:
        """Resolve a origem escolhida, com fallback para não bloquear configurações antigas."""
        if self.prefers_named():
            return self.active_key()
        return os.environ.get(ENV_VAR) or self.active_key()
