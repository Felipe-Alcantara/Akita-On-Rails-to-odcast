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

    def __init__(self, directory: Path, episode_id: str, resume: bool = True) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        previous = (self.load(directory) or {}) if resume else {}
        now = time.time()
        self._data: dict = {
            "episode_id": episode_id,
            "pid": os.getpid(),
            "state": "rodando",
            "stage": "",
            "progress": {"current": 0, "total": 0},
            "cost_usd": float(previous.get("cost_usd", 0.0) or 0.0),
            "started_at": previous.get("started_at", now),
            "run_started_at": now,
            "updated_at": now,
            "resume_count": int(previous.get("resume_count", 0) or 0) + bool(previous),
            "retry": None,
            "last_error": None,
        }
        # Um início novo limpa pedidos de abort antigos.
        (self.directory / self.ABORT_FILE).unlink(missing_ok=True)
        self._flush()

    # ── Escrita ──────────────────────────────────────────────────────────

    def _flush(self) -> None:
        self._data["updated_at"] = time.time()
        target = self.directory / self.STATUS_FILE
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.rename(target)

    def stage(self, name: str, total: int = 0, current: int = 0) -> None:
        """Entra em uma nova etapa; `total` > 0 habilita progresso granular."""
        if current < 0 or current > total:
            raise ValueError("O progresso atual precisa ficar entre zero e o total.")
        self._data["stage"] = name
        self._data["progress"] = {"current": current, "total": total}
        self._data["retry"] = None
        self._data["last_error"] = None
        self._flush()

    def advance(self, current: int) -> None:
        self._data["progress"]["current"] = current
        self._data["retry"] = None
        self._data["last_error"] = None
        self._flush()

    def retrying(self, *, segment: int, next_attempt: int, max_attempts: int,
                 delay_seconds: float, error: str) -> None:
        """Expõe uma espera de retry sem registrar o conteúdo enviado ao provedor."""
        self._data["retry"] = {
            "segment": segment,
            "attempt": next_attempt,
            "max_attempts": max_attempts,
            "retry_at": time.time() + delay_seconds,
        }
        self._data["last_error"] = str(error)[:300]
        self._flush()

    def record_error(self, error: str) -> None:
        self._data["retry"] = None
        self._data["last_error"] = str(error)[:300]
        self._flush()

    def add_cost(self, usd: float) -> None:
        if usd:
            self._data["cost_usd"] = round(self._data["cost_usd"] + usd, 6)
            self._flush()

    def finish(self, state: str, error: str | None = None) -> None:
        """Estado final: 'concluido', 'abortado' ou 'falhou'."""
        self._data["state"] = state
        self._data["retry"] = None
        if error:
            self._data["last_error"] = str(error)[:300]
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
