"""Rastreador da geração de um episódio.

Escreve `status.json` na pasta do episódio a cada mudança, para que CLI, app
Electron ou qualquer processo externo acompanhem em tempo real: etapa atual,
progresso, custo acumulado em US$ e estado (rodando/concluído/abortado/falhou).

O cancelamento é cooperativo: criar um arquivo `ABORT` na pasta do episódio faz
o pipeline parar no próximo checkpoint (entre segmentos/etapas), sem corromper
artefatos já salvos.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


class GenerationAborted(RuntimeError):
    """Levantada quando um pedido de abort é encontrado em um checkpoint."""


class GenerationTracker:
    STATUS_FILE = "status.json"
    ABORT_FILE = "ABORT"

    def __init__(self, directory: Path, episode_id: str) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._data: dict = {
            "episode_id": episode_id,
            "pid": os.getpid(),
            "state": "rodando",
            "stage": "",
            "progress": {"current": 0, "total": 0},
            "cost_usd": 0.0,
            "started_at": time.time(),
            "updated_at": time.time(),
        }
        # Um início novo limpa pedidos de abort antigos.
        (self.directory / self.ABORT_FILE).unlink(missing_ok=True)

    # ── Escrita ──────────────────────────────────────────────────────────

    def _flush(self) -> None:
        self._data["updated_at"] = time.time()
        target = self.directory / self.STATUS_FILE
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.rename(target)

    def stage(self, name: str, total: int = 0) -> None:
        """Entra em uma nova etapa; `total` > 0 habilita progresso granular."""
        self._data["stage"] = name
        self._data["progress"] = {"current": 0, "total": total}
        self._flush()

    def advance(self, current: int) -> None:
        self._data["progress"]["current"] = current
        self._flush()

    def add_cost(self, usd: float) -> None:
        if usd:
            self._data["cost_usd"] = round(self._data["cost_usd"] + usd, 6)
            self._flush()

    def finish(self, state: str) -> None:
        """Estado final: 'concluido', 'abortado' ou 'falhou'."""
        self._data["state"] = state
        self._flush()

    # ── Abort cooperativo ────────────────────────────────────────────────

    def checkpoint(self) -> None:
        """Chamado entre unidades de trabalho; honra pedidos de abort."""
        if (self.directory / self.ABORT_FILE).is_file():
            (self.directory / self.ABORT_FILE).unlink(missing_ok=True)
            self.finish("abortado")
            raise GenerationAborted("Geração abortada a pedido do usuário.")

    @staticmethod
    def request_abort(directory: Path) -> None:
        """Pede o cancelamento de uma geração em andamento (outro processo)."""
        (directory / GenerationTracker.ABORT_FILE).touch()

    # ── Leitura externa ──────────────────────────────────────────────────

    @property
    def cost_usd(self) -> float:
        return self._data["cost_usd"]

    @staticmethod
    def load(directory: Path) -> dict | None:
        status = directory / GenerationTracker.STATUS_FILE
        if not status.is_file():
            return None
        return json.loads(status.read_text(encoding="utf-8"))
