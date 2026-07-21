"""Diagnóstico e preparação do ambiente, compartilhados por CLI e Electron."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import PROJECT_ROOT, Settings
from .providers.subscription import SUBSCRIPTION_CLIS

_PYTHON_MODULES = (
    "requests",
    "questionary",
    "rich",
    "akita-articles",
    "pypdf",
    "python-docx",
    "ebooklib",
    "pytesseract",
)
_TUI_PACKAGES = ("questionary==2.1.1", "rich==15.0.0")


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
        SetupCheck(
            "git", "Git", bool(shutil.which("git")), True, "pode ser instalado automaticamente"
        ),
        SetupCheck(
            "ffmpeg",
            "FFmpeg",
            bool(shutil.which("ffmpeg")),
            True,
            "pode ser instalado automaticamente",
        ),
        SetupCheck(
            "node",
            "Node.js",
            bool(shutil.which("node")),
            False,
            "opcional; necessário para o app desktop",
        ),
        SetupCheck(
            "npm",
            "npm",
            bool(shutil.which("npm")),
            False,
            "opcional; instala o app desktop",
        ),
        SetupCheck(
            "electron-deps",
            "Dependências do app desktop",
            (PROJECT_ROOT / "electron" / "node_modules" / "electron").is_dir(),
            False,
            "opcional; Instalar / Setup prepara quando npm está disponível",
        ),
        SetupCheck(
            "requests",
            "Biblioteca requests",
            importlib.util.find_spec("requests") is not None,
            True,
            "pode ser instalada automaticamente",
        ),
        SetupCheck(
            "questionary",
            "Menu interativo questionary",
            importlib.util.find_spec("questionary") is not None,
            True,
            "pode ser instalado automaticamente",
        ),
        SetupCheck(
            "rich",
            "Interface colorida Rich",
            importlib.util.find_spec("rich") is not None,
            True,
            "pode ser instalada automaticamente",
        ),
        SetupCheck(
            "akita-articles",
            "Módulo akita-articles",
            importlib.util.find_spec("akita_articles") is not None,
            True,
            "pode ser instalado automaticamente",
        ),
        SetupCheck(
            "pypdf",
            "Leitor de PDF (pypdf)",
            importlib.util.find_spec("pypdf") is not None,
            False,
            "opcional; extrai texto de PDFs enviados como arquivo",
        ),
        SetupCheck(
            "python-docx",
            "Leitor de DOCX (python-docx)",
            importlib.util.find_spec("docx") is not None,
            False,
            "opcional; extrai texto de documentos Word",
        ),
        SetupCheck(
            "ebooklib",
            "Leitor de EPUB (ebooklib)",
            importlib.util.find_spec("ebooklib") is not None,
            False,
            "opcional; extrai texto de ebooks EPUB",
        ),
        SetupCheck(
            "pytesseract",
            "Ponte de OCR (pytesseract)",
            importlib.util.find_spec("pytesseract") is not None,
            False,
            "opcional; conecta o Python ao Tesseract",
        ),
        SetupCheck(
            "tesseract",
            "OCR local (Tesseract)",
            bool(shutil.which("tesseract")),
            False,
            "opcional; lê texto de imagens e PDFs escaneados sem custo de IA",
        ),
        SetupCheck(
            "openrouter-key",
            "Chave OpenRouter",
            bool(Settings().api_key),
            True,
            "adicione uma chave na aba Configurações",
        ),
        *[
            SetupCheck(
                f"subscription-{cli.key}",
                cli.name,
                cli.is_available(),
                False,
                "opcional; habilita texto pela assinatura",
            )
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


def _run(command: list[str], timeout: int = 20 * 60, cwd: Path | None = None) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return False, str(error)[:300]
    detail = (result.stderr or result.stdout).strip().splitlines()
    return result.returncode == 0, detail[-1][:300] if detail else "instalação concluída"


def npm_command() -> list[str] | None:
    """Resolve o npm sem depender da execução implícita de ``npm.cmd`` no Windows."""
    npm = shutil.which("npm")
    if not npm:
        return None
    if sys.platform == "win32":
        node = shutil.which("node")
        if node:
            npm_cli = Path(node).parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
            if npm_cli.is_file():
                return [node, str(npm_cli)]
    return [npm]


def _install(label: str, *packages: str) -> dict:
    user_scope = [] if sys.prefix != sys.base_prefix else ["--user"]
    ok, detail = _run([sys.executable, "-m", "pip", "install", *user_scope, *packages])
    if not ok and "externally-managed-environment" in detail:
        # Python do Homebrew/Debian bloqueia pip fora de venv (PEP 668).
        ok, detail = _run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                *user_scope,
                "--break-system-packages",
                *packages,
            ]
        )
    return {"name": label, "ok": ok, "detail": detail}


_SYSTEM_MANAGERS = [
    ("brew", ["brew", "install"]),
    (
        "winget",
        [
            "winget",
            "install",
            "--accept-source-agreements",
            "--accept-package-agreements",
            "-e",
            "--id",
        ],
    ),
    ("apt-get", ["sudo", "-n", "apt-get", "install", "-y"]),
    ("dnf", ["sudo", "-n", "dnf", "install", "-y"]),
    ("pacman", ["sudo", "-n", "pacman", "-S", "--noconfirm"]),
]

_WINGET_IDS = {
    "git": "Git.Git",
    "ffmpeg": "Gyan.FFmpeg",
    "tesseract": "UB-Mannheim.TesseractOCR",
}
# O Tesseract muda de nome entre distribuições; apt/dnf também têm o pacote
# de idioma português separado, essencial para OCR de conteúdo em pt-BR.
_SYSTEM_PACKAGES = {
    ("apt-get", "tesseract"): ["tesseract-ocr", "tesseract-ocr-por"],
    ("dnf", "tesseract"): ["tesseract", "tesseract-langpack-por"],
}


def _install_system(tool: str) -> dict:
    """Instala uma ferramenta de sistema (git/ffmpeg/tesseract) pelo gerenciador disponível."""
    for manager, base in _SYSTEM_MANAGERS:
        if not shutil.which(manager):
            continue
        if manager == "winget":
            packages = [_WINGET_IDS.get(tool, tool)]
        else:
            packages = _SYSTEM_PACKAGES.get((manager, tool), [tool])
        ok, detail = _run([*base, *packages])
        if ok and not shutil.which(tool) and manager == "winget":
            detail = "instalado; reinicie o app para atualizar o PATH"
        return {"name": tool, "ok": ok, "detail": f"via {manager}: {detail}"}
    hint = (
        "instale o Homebrew (https://brew.sh) e tente novamente"
        if sys.platform == "darwin"
        else "nenhum gerenciador de pacotes encontrado (brew/apt/dnf/pacman/winget)"
    )
    return {"name": tool, "ok": False, "detail": hint}


def apply_setup() -> dict:
    """Instala dependências Python ausentes e cria o ``.env`` quando necessário."""
    before = {check.key: check for check in inspect_setup()}
    actions: list[dict] = []

    # git primeiro: o akita-articles é instalado via ``git+https://``.
    for tool in ("git", "ffmpeg", "tesseract"):
        if tool in before and not before[tool].ok:
            actions.append(_install_system(tool))

    missing_python = [key for key in _PYTHON_MODULES if key in before and not before[key].ok]
    if missing_python:
        actions.append(
            _install(
                "dependências Python",
                "-r",
                str(PROJECT_ROOT / "requirements.txt"),
            )
        )

    npm = npm_command()
    electron_dir = PROJECT_ROOT / "electron"
    electron_missing = "electron-deps" in before and not before["electron-deps"].ok
    if npm and electron_missing and (electron_dir / "package-lock.json").is_file():
        ok, detail = _run(
            [*npm, "ci", "--no-fund", "--no-audit"],
            cwd=electron_dir,
        )
        actions.append({"name": "dependências do app desktop", "ok": ok, "detail": detail})

    env_path = PROJECT_ROOT / ".env"
    example_path = PROJECT_ROOT / ".env.example"
    if not env_path.is_file():
        if example_path.is_file():
            shutil.copyfile(example_path, env_path)
            actions.append(
                {"name": ".env", "ok": True, "detail": "criado a partir de .env.example"}
            )
        else:
            actions.append({"name": ".env", "ok": False, "detail": ".env.example não encontrado"})

    return {**setup_report(), "actions": actions}


def ensure_tui() -> dict | None:
    """Instala o mínimo necessário para desenhar o menu na primeira execução."""
    missing = [
        spec
        for key, spec in zip(("questionary", "rich"), _TUI_PACKAGES, strict=True)
        if importlib.util.find_spec(key) is None
    ]
    if not missing:
        return None
    action = _install("interface interativa", *missing)
    importlib.invalidate_caches()
    return action
