"""Diagnóstico e preparação do ambiente, compartilhados por CLI e Electron."""

from __future__ import annotations

import contextlib
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import PROJECT_ROOT, STATE_DIR, Settings
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
            bool(tesseract_command()),
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


# `sudo -n` nunca pede senha, mas falha quando ela seria necessária. Já sendo
# root, o sudo é dispensável (e costuma faltar em contêineres).
_ROOT_PREFIX: list[str] = (
    []
    if sys.platform != "win32" and hasattr(os, "geteuid") and os.geteuid() == 0
    else ["sudo", "-n"]
)

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
    ("apt-get", [*_ROOT_PREFIX, "apt-get", "install", "-y"]),
    ("dnf", [*_ROOT_PREFIX, "dnf", "install", "-y"]),
    ("pacman", [*_ROOT_PREFIX, "pacman", "-S", "--noconfirm"]),
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

_APT_TESSERACT_PACKAGES = (
    "tesseract-ocr",
    "tesseract-ocr-eng",
    "tesseract-ocr-por",
    "libtesseract5",
    "liblept5",
)


def _private_tesseract_root() -> Path:
    return STATE_DIR / "tools" / "tesseract"


# Instaladores oficiais não colocam o Tesseract no PATH em todos os sistemas: o
# instalador do Windows não mexe no PATH do usuário e o Homebrew varia a raiz
# entre Intel e Apple Silicon. Procurar nesses caminhos evita reinstalar algo
# que já está na máquina.
_TESSERACT_KNOWN_PATHS = {
    "win32": (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        "~/AppData/Local/Programs/Tesseract-OCR/tesseract.exe",
        "~/AppData/Local/Tesseract-OCR/tesseract.exe",
    ),
    "darwin": (
        "/opt/homebrew/bin/tesseract",
        "/usr/local/bin/tesseract",
    ),
}
_TESSERACT_UNIX_PATHS = ("/usr/bin/tesseract", "/usr/local/bin/tesseract")


def _private_tesseract_binaries() -> tuple[Path, ...]:
    """Caminhos possíveis do executável dentro da instalação privada."""
    root = _private_tesseract_root()
    return (
        root / "usr" / "bin" / "tesseract",  # extração de .deb
        root / "tesseract.exe",  # pacote portátil do Windows
        root / "bin" / "tesseract.exe",
        root / "bin" / "tesseract",
    )


def tesseract_command() -> str | None:
    """Encontra o Tesseract no PATH, instalado pelo SO ou na cópia privada."""
    system = shutil.which("tesseract")
    if system:
        return system
    known = _TESSERACT_KNOWN_PATHS.get(sys.platform, _TESSERACT_UNIX_PATHS)
    for raw in known:
        path = Path(raw).expanduser()
        if path.is_file():
            return str(path)
    for candidate in _private_tesseract_binaries():
        if candidate.is_file():
            return str(candidate)
    return None


def user_tessdata_dir() -> Path:
    """Diretório de idiomas sempre gravável pelo usuário, sem privilégio de admin."""
    return STATE_DIR / "tools" / "tessdata"


def _system_tessdata_candidates(command: str) -> list[Path]:
    """Diretórios tessdata associados a um executável do Tesseract."""
    root = Path(command).resolve().parent
    return [
        root / "tessdata",
        root.parent / "share" / "tessdata",
        root.parent / "share" / "tesseract-ocr" / "5" / "tessdata",
        root.parent / "share" / "tesseract-ocr" / "4.00" / "tessdata",
    ]


def configure_tesseract() -> str | None:
    """Configura pytesseract, bibliotecas e idiomas para a instalação encontrada."""
    command = tesseract_command()
    if not command:
        return None
    private_root = _private_tesseract_root()
    if Path(command).is_relative_to(private_root):
        lib_dirs = [
            path
            for pattern in ("usr/lib/*-linux-gnu", "lib/*-linux-gnu")
            for path in private_root.glob(pattern)
            if path.is_dir()
        ]
        if lib_dirs:
            current = os.environ.get("LD_LIBRARY_PATH", "")
            os.environ["LD_LIBRARY_PATH"] = os.pathsep.join(
                [*(str(path) for path in lib_dirs), *([current] if current else [])]
            )
    # O tessdata do usuário tem prioridade: é onde o Audiofy grava o idioma
    # português quando o diretório do sistema exige admin. Os idiomas que já
    # vieram com a instalação são copiados para lá, pois o Tesseract lê de um
    # único TESSDATA_PREFIX por vez.
    user_tessdata = user_tessdata_dir()
    if user_tessdata.is_dir() and any(user_tessdata.glob("*.traineddata")):
        os.environ["TESSDATA_PREFIX"] = str(user_tessdata)
    else:
        for tessdata in _system_tessdata_candidates(command):
            if tessdata.is_dir():
                os.environ["TESSDATA_PREFIX"] = str(tessdata)
                break
    # A ponte Python é opcional: sem ela o OCR fica indisponível, mas o
    # diagnóstico do Setup continua funcionando.
    with contextlib.suppress(ImportError):
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = command
    return command


def _install_private_tesseract_apt() -> tuple[bool, str]:
    """Baixa e extrai pacotes APT no estado local, sem sudo nem alteração do sistema."""
    if not shutil.which("dpkg-deb"):
        return False, "dpkg-deb não está disponível para extrair a instalação local"
    destination = _private_tesseract_root()
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=STATE_DIR) as temporary:
        download_dir = Path(temporary)
        ok, detail = _run(["apt-get", "download", *_APT_TESSERACT_PACKAGES], cwd=download_dir)
        if not ok:
            return False, detail
        archives = sorted(download_dir.glob("*.deb"))
        if not archives:
            return False, "o APT não baixou os pacotes do Tesseract"
        for archive in archives:
            ok, detail = _run(["dpkg-deb", "-x", str(archive), str(destination)])
            if not ok:
                return False, detail
    command = configure_tesseract()
    if not command:
        return False, "os pacotes foram extraídos, mas o executável não foi encontrado"
    ok, detail = _run([command, "--version"])
    if not ok:
        return False, f"Tesseract local não iniciou: {detail}"
    return True, "instalado localmente em .audiofy/tools (sem privilégio de administrador)"


# tessdata_fast equilibra tamanho e precisão; tessdata (completo) é mais exato
# e mais pesado, e serve a quem preferir qualidade a tempo de download.
_TESSDATA_URL = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/{lang}.traineddata"
_REQUIRED_LANGS = ("por", "eng")
# Build portátil (zip, sem instalador e sem admin) publicada pelo projeto
# UB-Mannheim. A versão fica isolada para que atualizá-la seja uma linha só.
_WINDOWS_TESSERACT_VERSION = "5.4.0"
_WINDOWS_TESSERACT_ZIP = (
    "https://github.com/UB-Mannheim/tesseract/releases/download/"
    f"v{_WINDOWS_TESSERACT_VERSION}/tesseract-{_WINDOWS_TESSERACT_VERSION}-portable.zip"
)

_DOWNLOAD_TIMEOUT = 120


def _download(url: str, destination: Path) -> tuple[bool, str]:
    """Baixa um arquivo usando apenas a biblioteca padrão, sem depender de curl/wget."""
    import urllib.error
    import urllib.parse
    import urllib.request

    # Só HTTPS: evita que uma URL adulterada vire leitura de arquivo local
    # (file://) ou tráfego em texto claro.
    if urllib.parse.urlparse(url).scheme != "https":
        return False, f"origem recusada, apenas HTTPS é aceito: {url}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=_DOWNLOAD_TIMEOUT) as response:
            with partial.open("wb") as handle:
                shutil.copyfileobj(response, handle)
    except (urllib.error.URLError, OSError, TimeoutError) as error:
        partial.unlink(missing_ok=True)
        return False, f"falha ao baixar {url}: {error}"
    # A troca só acontece com o download íntegro, então uma queda de rede não
    # deixa um idioma truncado no lugar do arquivo bom.
    partial.replace(destination)
    return True, str(destination)


def ensure_tesseract_languages() -> tuple[bool, str]:
    """Garante português e inglês num tessdata do usuário, sem exigir admin."""
    command = tesseract_command()
    if not command:
        return False, "Tesseract não encontrado"
    target = user_tessdata_dir()
    target.mkdir(parents=True, exist_ok=True)
    # Aproveita os idiomas já presentes na instalação para evitar downloads.
    for source in _system_tessdata_candidates(command):
        if not source.is_dir():
            continue
        for existing in source.glob("*.traineddata"):
            copy = target / existing.name
            if not copy.exists():
                # Um idioma que não pôde ser copiado é rebaixado ao download.
                with contextlib.suppress(OSError):
                    shutil.copy2(existing, copy)
        break
    downloaded: list[str] = []
    for lang in _REQUIRED_LANGS:
        path = target / f"{lang}.traineddata"
        if path.is_file() and path.stat().st_size > 0:
            continue
        ok, detail = _download(_TESSDATA_URL.format(lang=lang), path)
        if not ok:
            return False, detail
        downloaded.append(lang)
    configure_tesseract()
    if downloaded:
        return True, f"idiomas instalados: {', '.join(downloaded)}"
    return True, "idiomas já disponíveis"


def _install_private_tesseract_windows() -> tuple[bool, str]:
    """Instala uma cópia portátil no estado local, sem instalador e sem admin."""
    import zipfile

    destination = _private_tesseract_root()
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=STATE_DIR) as temporary:
        archive = Path(temporary) / "tesseract.zip"
        ok, detail = _download(_WINDOWS_TESSERACT_ZIP, archive)
        if not ok:
            return False, detail
        try:
            with zipfile.ZipFile(archive) as bundle:
                bundle.extractall(destination)
        except (zipfile.BadZipFile, OSError) as error:
            return False, f"falha ao extrair o pacote portátil: {error}"
    # O zip costuma trazer tudo sob uma pasta raiz; nivela para achar o binário.
    if not any(path.is_file() for path in _private_tesseract_binaries()):
        for nested in destination.iterdir():
            if nested.is_dir() and (nested / "tesseract.exe").is_file():
                for item in nested.iterdir():
                    item.rename(destination / item.name)
                nested.rmdir()
                break
    command = configure_tesseract()
    if not command:
        return False, "o pacote foi extraído, mas o executável não foi encontrado"
    ok, detail = _run([command, "--version"])
    if not ok:
        return False, f"Tesseract local não iniciou: {detail}"
    return True, "instalado localmente em .audiofy/tools (sem admin)"


def _install_private_tesseract() -> tuple[bool, str]:
    """Instalação privada adequada ao SO, sempre sem senha."""
    if sys.platform == "win32":
        return _install_private_tesseract_windows()
    if shutil.which("apt-get"):
        return _install_private_tesseract_apt()
    return False, "sem método de instalação local para este sistema"


def _install_system(tool: str) -> dict:
    """Instala uma ferramenta de sistema (git/ffmpeg/tesseract) pelo gerenciador disponível."""
    # Uma cópia já presente fora do PATH dispensa qualquer instalação.
    if tool == "tesseract" and tesseract_command():
        configure_tesseract()
        return {"name": tool, "ok": True, "detail": "já instalado; usando a cópia existente"}
    for manager, base in _SYSTEM_MANAGERS:
        if not shutil.which(manager):
            continue
        if manager == "winget":
            packages = [_WINGET_IDS.get(tool, tool)]
        else:
            packages = _SYSTEM_PACKAGES.get((manager, tool), [tool])
        ok, detail = _run([*base, *packages])
        if not ok and tool == "tesseract":
            # Falha do gerenciador (falta de privilégio, fonte indisponível):
            # a instalação privada nunca precisa de senha.
            ok, detail = _install_private_tesseract()
            return {"name": tool, "ok": ok, "detail": f"local: {detail}"}
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

    # Só depois de tratar um Tesseract ausente: os idiomas vão para o tessdata
    # do usuário, pois o diretório do sistema costuma exigir admin.
    if "tesseract" in before and not before["tesseract"].ok and tesseract_command():
        ok, detail = ensure_tesseract_languages()
        actions.append({"name": "idiomas de OCR", "ok": ok, "detail": detail})

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
