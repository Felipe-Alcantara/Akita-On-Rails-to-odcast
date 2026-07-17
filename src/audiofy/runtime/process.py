"""Execução de processos externa, portátil entre Windows e POSIX.

Centraliza três armadilhas que faziam o programa travar ou falhar em silêncio,
sobretudo no Windows:

- **Desanexar um worker de segundo plano.** ``start_new_session`` só existe no
  POSIX; no Windows é preciso ``creationflags``. Um lançamento com o argumento
  errado levanta exceção e o worker nunca roda.
- **Resolver a ferramenta de linha de comando.** ``ffmpeg``/``ffprobe`` podem não
  estar no PATH; chamar pelo nome cru gera ``FileNotFoundError`` sem contexto.
- **Rodar com limite de tempo.** Sem ``timeout`` um subprocesso que trava
  (ffmpeg à espera de entrada, rede parada) pendura a geração inteira.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


class ToolNotFoundError(RuntimeError):
    """A ferramenta externa exigida não está instalada nem no PATH."""


def detached_flags() -> dict:
    """Argumentos de ``Popen`` para desanexar um processo de longa duração.

    No Windows, ``DETACHED_PROCESS`` desliga o console herdado e
    ``CREATE_NEW_PROCESS_GROUP`` evita que um Ctrl+C no pai derrube o worker.
    No POSIX, ``start_new_session`` cria um novo grupo/sessão com o mesmo efeito.
    """
    if sys.platform == "win32":
        return {"creationflags": (subprocess.DETACHED_PROCESS
                                  | subprocess.CREATE_NEW_PROCESS_GROUP)}
    return {"start_new_session": True}


def resolve_tool(name: str) -> str:
    """Caminho absoluto de uma ferramenta externa, ou erro claro se faltar."""
    found = shutil.which(name)
    if not found:
        raise ToolNotFoundError(
            f"'{name}' não foi encontrado no PATH. Instale-o (o Setup do app "
            f"instala git e ffmpeg) e reabra o programa."
        )
    return found


def run_tool(name: str, args: list[str], *, timeout: float,
             check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    """Executa uma ferramenta externa resolvida, sempre com timeout.

    ``kwargs`` repassa opções de ``subprocess.run`` (cwd, input, etc.). O timeout
    é obrigatório para nenhuma chamada poder pendurar a geração em silêncio.
    """
    executable = resolve_tool(name)
    return subprocess.run(
        [executable, *args], timeout=timeout, check=check,
        capture_output=True, text=True, **kwargs,
    )


def launch_detached(args: list[str], *, cwd: str | Path | None = None,
                    env: dict | None = None, log_handle=None) -> subprocess.Popen:
    """Inicia um worker de segundo plano desanexado, de forma portátil."""
    stdout = log_handle if log_handle is not None else subprocess.DEVNULL
    stderr = subprocess.STDOUT if log_handle is not None else subprocess.DEVNULL
    return subprocess.Popen(
        args, cwd=str(cwd) if cwd is not None else None, env=env,
        stdout=stdout, stderr=stderr, **detached_flags(),
    )
