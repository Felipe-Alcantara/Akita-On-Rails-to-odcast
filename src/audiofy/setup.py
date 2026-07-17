"""Diagnóstico e preparação do ambiente, compartilhados por CLI e Electron."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass

from .config import PROJECT_ROOT, Settings
from .providers.subscription import SUBSCRIPTION_CLIS

_PYTHON_PACKAGES = {
    "requests": "requests>=2.31,<3",
    "questionary": "questionary>=2.0,<3",
    "rich": "rich>=13,<15",
}


@dataclass(frozen=True)
class SetupCheck:
    key: str
    name: str
    ok: bool
    required: bool
    hint: str


def inspect_setup() -> list[SetupCheck]:
    """Retorna um retrato do ambiente sem modificar arquivos ou instalar pacotes."""
    return [
        SetupCheck("git", "Git", bool(shutil.which("git")), True,
                   "pode ser instalado automaticamente"),
        SetupCheck("ffmpeg", "FFmpeg", bool(shutil.which("ffmpeg")), True,
                   "pode ser instalado automaticamente"),
        SetupCheck("requests", "Biblioteca requests",
                   importlib.util.find_spec("requests") is not None, True,
                   "pode ser instalada automaticamente"),
        SetupCheck("questionary", "Menu interativo questionary",
                   importlib.util.find_spec("questionary") is not None, True,
                   "pode ser instalado automaticamente"),
        SetupCheck("rich", "Interface colorida Rich",
                   importlib.util.find_spec("rich") is not None, True,
                   "pode ser instalada automaticamente"),
        SetupCheck("akita-articles", "Módulo akita-articles",
                   importlib.util.find_spec("akita_articles") is not None, True,
                   "pode ser instalado automaticamente"),
        SetupCheck("openrouter-key", "Chave OpenRouter", bool(Settings().api_key), True,
                   "adicione uma chave na aba Configurações"),
        *[
            SetupCheck(f"subscription-{cli.key}", cli.name, cli.is_available(), False,
                       "opcional; habilita texto pela assinatura")
            for cli in SUBSCRIPTION_CLIS
        ],
    ]


def setup_report() -> dict:
    checks = inspect_setup()
    return {
        "checks": [asdict(check) for check in checks],
        "ready": all(check.ok for check in checks if check.required),
        "env_exists": (PROJECT_ROOT / ".env").is_file(),
    }


def _run(command: list[str], timeout: int = 20 * 60) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)[:300]
    detail = (result.stderr or result.stdout).strip().splitlines()
    return result.returncode == 0, detail[-1][:300] if detail else "instalação concluída"


def _install(label: str, *packages: str) -> dict:
    user_scope = [] if sys.prefix != sys.base_prefix else ["--user"]
    ok, detail = _run([sys.executable, "-m", "pip", "install", *user_scope, *packages])
    if not ok and "externally-managed-environment" in detail:
        # Python do Homebrew/Debian bloqueia pip fora de venv (PEP 668).
        ok, detail = _run([sys.executable, "-m", "pip", "install",
                           *user_scope, "--break-system-packages", *packages])
    return {"name": label, "ok": ok, "detail": detail}


_SYSTEM_MANAGERS = [
    ("brew", ["brew", "install"]),
    ("winget", ["winget", "install", "--accept-source-agreements",
                "--accept-package-agreements", "-e", "--id"]),
    ("apt-get", ["sudo", "-n", "apt-get", "install", "-y"]),
    ("dnf", ["sudo", "-n", "dnf", "install", "-y"]),
    ("pacman", ["sudo", "-n", "pacman", "-S", "--noconfirm"]),
]

_WINGET_IDS = {"git": "Git.Git", "ffmpeg": "Gyan.FFmpeg"}


def _install_system(tool: str) -> dict:
    """Instala uma ferramenta de sistema (git/ffmpeg) pelo gerenciador disponível."""
    for manager, base in _SYSTEM_MANAGERS:
        if not shutil.which(manager):
            continue
        package = _WINGET_IDS.get(tool, tool) if manager == "winget" else tool
        ok, detail = _run([*base, package])
        if ok and not shutil.which(tool) and manager == "winget":
            detail = "instalado; reinicie o app para atualizar o PATH"
        return {"name": tool, "ok": ok, "detail": f"via {manager}: {detail}"}
    hint = ("instale o Homebrew (https://brew.sh) e tente novamente"
            if sys.platform == "darwin"
            else "nenhum gerenciador de pacotes encontrado (brew/apt/dnf/pacman/winget)")
    return {"name": tool, "ok": False, "detail": hint}


def apply_setup() -> dict:
    """Instala dependências Python ausentes e cria o ``.env`` quando necessário."""
    before = {check.key: check for check in inspect_setup()}
    actions: list[dict] = []

    # git primeiro: o akita-articles é instalado via ``git+https://``.
    for tool in ("git", "ffmpeg"):
        if tool in before and not before[tool].ok:
            actions.append(_install_system(tool))

    missing_python = [spec for key, spec in _PYTHON_PACKAGES.items()
                      if key in before and not before[key].ok]
    if missing_python:
        actions.append(_install("dependências Python", *missing_python))
    if not before["akita-articles"].ok:
        actions.append(_install(
            "akita-articles",
            "git+https://github.com/Felipe-Alcantara/akita-articles",
        ))

    env_path = PROJECT_ROOT / ".env"
    example_path = PROJECT_ROOT / ".env.example"
    if not env_path.is_file():
        if example_path.is_file():
            shutil.copyfile(example_path, env_path)
            actions.append({"name": ".env", "ok": True,
                            "detail": "criado a partir de .env.example"})
        else:
            actions.append({"name": ".env", "ok": False,
                            "detail": ".env.example não encontrado"})

    return {**setup_report(), "actions": actions}


def ensure_tui() -> dict | None:
    """Instala o mínimo necessário para desenhar o menu na primeira execução."""
    missing = [spec for key, spec in _PYTHON_PACKAGES.items()
               if key in {"questionary", "rich"}
               and importlib.util.find_spec(key) is None]
    if not missing:
        return None
    action = _install("interface interativa", *missing)
    importlib.invalidate_caches()
    return action
