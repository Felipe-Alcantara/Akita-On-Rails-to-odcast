#!/usr/bin/env python3
"""Executa a régua de qualidade local do Audiofy.

Este é um utilitário interno de manutenção, sem usuário final; por isso não possui
um menu próprio. A porta de entrada do produto continua sendo ``start_app.py``.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlsplit

PROJECT_ROOT = Path(__file__).resolve().parents[1]
_MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]
    cwd: Path = PROJECT_ROOT


def npm_command() -> tuple[str, ...]:
    """Resolve o npm sem depender da execução implícita de ``npm.cmd`` no Windows."""
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("npm não encontrado; instale Node.js para validar o Electron.")
    if sys.platform == "win32":
        node = shutil.which("node")
        if node:
            npm_cli = Path(node).parent / "node_modules" / "npm" / "bin" / "npm-cli.js"
            if npm_cli.is_file():
                return node, str(npm_cli)
    return (npm,)


def validate_json_files() -> None:
    """Valida todos os arquivos JSON versionados, inclusive artefatos de episódios."""
    result = subprocess.run(
        ["git", "ls-files", "*.json"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    failures: list[str] = []
    for relative in result.stdout.splitlines():
        path = PROJECT_ROOT / relative
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            failures.append(f"{relative}: {error}")
    if failures:
        raise RuntimeError("JSON inválido:\n" + "\n".join(failures))


def validate_markdown_links(
    root: Path = PROJECT_ROOT, relative_files: list[str] | None = None
) -> None:
    """Confirma que links relativos na documentação apontam para arquivos existentes."""
    if relative_files is None:
        result = subprocess.run(
            ["git", "ls-files", "*.md"],
            cwd=root,
            capture_output=True,
            check=True,
            text=True,
        )
        relative_files = [
            relative for relative in result.stdout.splitlines() if not relative.startswith("data/")
        ]

    failures: list[str] = []
    resolved_root = root.resolve()
    for relative in relative_files:
        document = root / relative
        for raw_target in _MARKDOWN_LINK.findall(document.read_text(encoding="utf-8")):
            target = raw_target.strip().strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            candidate = (document.parent / unquote(parsed.path)).resolve()
            try:
                candidate.relative_to(resolved_root)
            except ValueError:
                failures.append(f"{relative}: link escapa do repositório ({target})")
                continue
            if not candidate.exists():
                failures.append(f"{relative}: destino inexistente ({target})")
    if failures:
        raise RuntimeError("Link interno inválido:\n" + "\n".join(failures))


def checks(*, quick: bool) -> list[Check]:
    python = sys.executable
    npm = npm_command()
    result = [
        Check(
            "Lint Python",
            (python, "-m", "ruff", "check", "start_app.py", "src", "tests", "scripts"),
        ),
        Check(
            "Formatação Python",
            (
                python,
                "-m",
                "ruff",
                "format",
                "--check",
                "start_app.py",
                "src",
                "tests",
                "scripts",
            ),
        ),
        Check(
            "Testes e cobertura Python",
            (
                python,
                "-m",
                "coverage",
                "run",
                "-m",
                "unittest",
                "discover",
                "-s",
                "tests",
                "-v",
            ),
        ),
        Check("Cobertura mínima", (python, "-m", "coverage", "report")),
        Check("Electron", (*npm, "--prefix", "electron", "run", "check")),
        Check("Whitespace Git", ("git", "diff", "--check")),
    ]
    if not quick:
        result.extend(
            [
                Check(
                    "Dependências Python",
                    (python, "-m", "pip_audit", "-r", "requirements.txt"),
                ),
                Check(
                    "Dependências Electron",
                    (*npm, "--prefix", "electron", "audit", "--audit-level=moderate"),
                ),
            ]
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="pula auditorias que dependem da rede",
    )
    args = parser.parse_args()

    try:
        selected = checks(quick=args.quick)
    except RuntimeError as error:
        print(f"ERRO: {error}", file=sys.stderr)
        return 1

    failures: list[str] = []
    for check in selected:
        print(f"\n==> {check.name}", flush=True)
        completed = subprocess.run(check.command, cwd=check.cwd)
        if completed.returncode:
            failures.append(check.name)

    print("\n==> Dados e documentação versionados", flush=True)
    try:
        validate_json_files()
        validate_markdown_links()
        print("Todos os arquivos JSON são válidos.")
        print("Todos os links internos da documentação apontam para arquivos existentes.")
    except (OSError, subprocess.SubprocessError, RuntimeError) as error:
        print(f"ERRO: {error}", file=sys.stderr)
        failures.append("dados/documentação versionados")

    if failures:
        print("\nQualidade reprovada: " + ", ".join(failures), file=sys.stderr)
        return 1
    print("\nQualidade aprovada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
