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
- **Encerrar a árvore do worker.** Um abort precisa interromper também TTS, CLI
  de assinatura ou ffmpeg que estejam bloqueando o próximo checkpoint.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path


class ToolNotFoundError(RuntimeError):
    """A ferramenta externa exigida não está instalada nem no PATH."""


def pid_alive(pid: int) -> bool:
    """Informa se um processo existe, sem sinalizá-lo nem matá-lo.

    No Windows ``os.kill(pid, 0)`` TERMINA o processo (TerminateProcess), então a
    consulta usa a API do kernel. Em caso de dúvida (sem permissão para abrir o
    processo), assume vivo — o vigia só declara morte quando tem certeza.
    """
    if not isinstance(pid, int) or pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            ERROR_ACCESS_DENIED = 5
            return kernel32.GetLastError() == ERROR_ACCESS_DENIED
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_until_stopped(pid: int, timeout: float) -> bool:
    deadline = time.monotonic() + max(0.0, timeout)
    alive = pid_alive(pid)
    while alive and time.monotonic() < deadline:
        time.sleep(0.05)
        alive = pid_alive(pid)
    return not alive


def process_command(pid: int) -> str | None:
    """Lê a linha de comando de um PID para confirmar sua identidade antes do sinal."""
    if not isinstance(pid, int) or pid <= 0:
        return None
    try:
        proc_command = Path(f"/proc/{pid}/cmdline")
        if proc_command.is_file():
            raw = proc_command.read_bytes().replace(b"\0", b" ").decode("utf-8", errors="replace")
            return " ".join(raw.split())
        if sys.platform == "win32":
            powershell = shutil.which("powershell") or shutil.which("pwsh")
            if not powershell:
                return None
            completed = subprocess.run(
                [
                    powershell,
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}').CommandLine",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            completed = subprocess.run(
                ["ps", "-p", str(pid), "-o", "command="],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        command = " ".join(completed.stdout.split())
        return command or None
    except (OSError, subprocess.SubprocessError):
        return None


def terminate_process(
    pid: int,
    grace_seconds: float = 2.0,
    expected_fragments: tuple[str, ...] = (),
) -> bool:
    """Encerra um worker desanexado e seus filhos sem atingir o processo atual.

    Retorna ``True`` quando o PID já terminou ou foi encerrado. No POSIX o worker
    abre uma sessão própria, então o grupo inclui um eventual ffmpeg. No Windows,
    ``taskkill /T`` oferece a mesma semântica para a árvore de processos.
    """
    if not isinstance(pid, int) or pid <= 0 or pid == os.getpid():
        return False
    if not pid_alive(pid):
        return True
    if expected_fragments:
        command = process_command(pid)
        if command is None or not all(fragment in command for fragment in expected_fragments):
            return False
    try:
        if sys.platform == "win32":
            completed = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if completed.returncode and pid_alive(pid):
                return False
        else:
            process_group = os.getpgid(pid)
            owns_group = process_group == pid and process_group != os.getpgrp()
            if owns_group:
                os.killpg(process_group, signal.SIGTERM)
            else:
                os.kill(pid, signal.SIGTERM)
            if _wait_until_stopped(pid, grace_seconds):
                return True
            if owns_group:
                os.killpg(process_group, signal.SIGKILL)
            else:
                os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    except (OSError, subprocess.SubprocessError):
        return not pid_alive(pid)
    return _wait_until_stopped(pid, 1.0)


def detached_flags() -> dict:
    """Argumentos de ``Popen`` para desanexar um processo de longa duração.

    No Windows, ``DETACHED_PROCESS`` desliga o console herdado e
    ``CREATE_NEW_PROCESS_GROUP`` evita que um Ctrl+C no pai derrube o worker.
    No POSIX, ``start_new_session`` cria um novo grupo/sessão com o mesmo efeito.
    """
    if sys.platform == "win32":
        return {
            "creationflags": (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
        }
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


def run_tool(
    name: str, args: list[str], *, timeout: float, check: bool = True, **kwargs
) -> subprocess.CompletedProcess:
    """Executa uma ferramenta externa resolvida, sempre com timeout.

    ``kwargs`` repassa opções de ``subprocess.run`` (cwd, input, etc.). O timeout
    é obrigatório para nenhuma chamada poder pendurar a geração em silêncio.
    """
    executable = resolve_tool(name)
    return subprocess.run(
        [executable, *args],
        timeout=timeout,
        check=check,
        capture_output=True,
        text=True,
        **kwargs,
    )


def launch_detached(
    args: list[str], *, cwd: str | Path | None = None, env: dict | None = None, log_handle=None
) -> subprocess.Popen:
    """Inicia um worker de segundo plano desanexado, de forma portátil."""
    stdout = log_handle if log_handle is not None else subprocess.DEVNULL
    stderr = subprocess.STDOUT if log_handle is not None else subprocess.DEVNULL
    return subprocess.Popen(
        args,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        stdout=stdout,
        stderr=stderr,
        **detached_flags(),
    )
