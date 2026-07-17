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
import tempfile
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
        launch_status = self.load(directory) or {}
        previous = launch_status if resume else {}
        now = time.time()
        previous_cost = float(previous.get("cost_usd", 0.0) or 0.0)
        self._data: dict = {
            "episode_id": episode_id,
            "pid": os.getpid(),
            "state": "rodando",
            "stage": "",
            "progress": {"current": 0, "total": 0},
            "cost_usd": previous_cost,
            "cost_exact": bool(previous.get("cost_exact", previous_cost == 0)),
            "started_at": previous.get("started_at", now),
            "run_started_at": now,
            "updated_at": now,
            "resume_count": int(previous.get("resume_count", 0) or 0) + bool(previous),
            "retry": None,
            "last_error": None,
        }
        # O launcher já limpou aborts antigos. Um abort pedido enquanto o worker
        # iniciava precisa sobreviver até o primeiro checkpoint do processo filho.
        if launch_status.get("stage") != "iniciando":
            (self.directory / self.ABORT_FILE).unlink(missing_ok=True)
        self._flush()

    # ── Escrita ──────────────────────────────────────────────────────────

    @staticmethod
    def _write(directory: Path, data: dict) -> None:
        data["updated_at"] = time.time()
        target = directory / GenerationTracker.STATUS_FILE
        # Launcher, worker e reconciliação podem publicar quase ao mesmo tempo.
        # Um nome fixo (status.json.tmp) fazia dois processos disputarem o mesmo
        # arquivo e o Path.rename não sobrescreve o destino no Windows. Um temporário
        # exclusivo no mesmo diretório + os.replace mantém a troca atômica inclusive
        # em pastas sincronizadas pelo OneDrive.
        temporary_name = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=directory,
                prefix=f".{GenerationTracker.STATUS_FILE}.", suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_name = temporary.name
                json.dump(data, temporary, ensure_ascii=False, indent=2)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, target)
        finally:
            if temporary_name:
                Path(temporary_name).unlink(missing_ok=True)

    def _flush(self) -> None:
        self._write(self.directory, self._data)

    @classmethod
    def mark_starting(cls, directory: Path, episode_id: str,
                      resume: bool = True) -> None:
        """Publica o início antes de lançar o worker, fechando a janela sem feedback."""
        directory.mkdir(parents=True, exist_ok=True)
        previous = (cls.load(directory) or {}) if resume else {}
        now = time.time()
        progress = previous.get("progress", {"current": 0, "total": 0})
        if not isinstance(progress, dict):
            progress = {"current": 0, "total": 0}
        data = {
            "episode_id": episode_id,
            "pid": None,
            "state": "rodando",
            "stage": "iniciando",
            "progress": {
                "current": int(progress.get("current", 0) or 0),
                "total": int(progress.get("total", 0) or 0),
            },
            "cost_usd": float(previous.get("cost_usd", 0.0) or 0.0),
            "cost_exact": bool(previous.get(
                "cost_exact", not float(previous.get("cost_usd", 0.0) or 0.0)
            )),
            "started_at": previous.get("started_at", now),
            "run_started_at": now,
            "updated_at": now,
            "resume_count": int(previous.get("resume_count", 0) or 0),
            "retry": None,
            "last_error": None,
        }
        (directory / cls.ABORT_FILE).unlink(missing_ok=True)
        cls._write(directory, data)

    @classmethod
    def mark_launch_failed(cls, directory: Path, error: str) -> None:
        data = cls.load(directory) or {}
        data.update({
            "state": "falhou",
            "stage": "inicialização",
            "retry": None,
            "last_error": str(error)[:300],
        })
        cls._write(directory, data)

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

    def add_cost(self, usd: float, *, exact: bool = True) -> None:
        changed = False
        if usd:
            self._data["cost_usd"] = round(self._data["cost_usd"] + usd, 6)
            changed = True
        if not exact and self._data["cost_exact"]:
            self._data["cost_exact"] = False
            changed = True
        if changed:
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

    @property
    def cost_exact(self) -> bool:
        return bool(self._data["cost_exact"])

    @staticmethod
    def load(directory: Path) -> dict | None:
        status = directory / GenerationTracker.STATUS_FILE
        if not status.is_file():
            return None
        return json.loads(status.read_text(encoding="utf-8"))

    # Quanto tempo um estado "iniciando" sem PID pode durar antes de ser
    # considerado um worker que nunca subiu (lançamento + imports do Python).
    STARTUP_GRACE_SECONDS = 90

    @classmethod
    def reconcile(cls, directory: Path) -> dict | None:
        """Carrega o status e corrige um 'rodando' cujo worker morreu.

        Um worker desanexado pode morrer sem atualizar o status (erro de
        importação, processo finalizado pelo sistema). Sem esta verificação, a
        interface mostraria "rodando" para sempre — o travamento silencioso.
        """
        from .process import pid_alive

        data = cls.load(directory)
        if not data or data.get("state") != "rodando":
            return data
        pid = data.get("pid")
        if pid:
            if not pid_alive(pid):
                data.update({
                    "state": "falhou",
                    "retry": None,
                    "last_error": ("O processo de geração terminou inesperadamente; "
                                   "veja generation.log na pasta do episódio."),
                })
                cls._write(directory, data)
        elif data.get("stage") == "iniciando":
            started = float(data.get("run_started_at", 0) or 0)
            if time.time() - started > cls.STARTUP_GRACE_SECONDS:
                data.update({
                    "state": "falhou",
                    "stage": "inicialização",
                    "retry": None,
                    "last_error": ("O worker de geração não iniciou; "
                                   "veja generation.log na pasta do episódio."),
                })
                cls._write(directory, data)
        return data
