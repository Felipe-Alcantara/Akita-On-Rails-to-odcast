"""Provedor de texto por assinatura: CLIs locais (Claude Code, Gemini CLI, Codex).

As etapas de texto do pipeline (matriz de cobertura, roteiro, auditoria) podem
rodar em uma CLI de IA instalada na máquina, sob a assinatura do usuário —
custo marginal zero em vez de pagar por token no OpenRouter. O TTS continua
no provedor de API (assinaturas não expõem TTS programável).

Contrato declarativo no espírito do Openia: cada CLI é descrita por uma
instância de `SubscriptionCli`; o núcleo só conhece `chat_json`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_TIMEOUT_SECONDS = 900


def run_cli(command: list[str], stdin: str,
            timeout: int = _TIMEOUT_SECONDS) -> subprocess.CompletedProcess:
    """Executa uma CLI de assinatura de forma portátil.

    No Windows as CLIs instaladas via npm (claude, gemini) são scripts ``.cmd``,
    que o ``CreateProcess`` não executa diretamente — apenas o ``cmd.exe`` os
    resolve pelo PATH/PATHEXT. Os argumentos são citados por ``list2cmdline``;
    o comando vem do contrato declarativo, nunca de entrada do usuário.
    """
    if sys.platform == "win32":
        return subprocess.run(subprocess.list2cmdline(command), input=stdin,
                              capture_output=True, text=True, timeout=timeout, shell=True)
    return subprocess.run(command, input=stdin, capture_output=True, text=True,
                          timeout=timeout)


class SubscriptionError(RuntimeError):
    pass


@dataclass(frozen=True)
class SubscriptionCli:
    """CLI de IA que roda sob assinatura, em modo não interativo (stdin → stdout)."""

    key: str
    name: str
    binary: str
    args: tuple[str, ...]  # argumentos de modo headless; prompt entra por stdin

    def command(self, system: str) -> list[str]:
        return [self.binary, *[a.format(system=system) for a in self.args]]

    def is_available(self) -> bool:
        return shutil.which(self.binary) is not None


SUBSCRIPTION_CLIS: list[SubscriptionCli] = [
    SubscriptionCli(
        key="claude-code",
        name="Claude Code (assinatura Anthropic)",
        binary="claude",
        args=("-p", "--output-format", "text", "--append-system-prompt", "{system}"),
    ),
    SubscriptionCli(
        key="gemini-cli",
        name="Gemini CLI (conta Google)",
        binary="gemini",
        args=(),  # lê o prompt inteiro por stdin
    ),
    SubscriptionCli(
        key="codex",
        name="Codex CLI (assinatura OpenAI)",
        binary="codex",
        args=("exec", "-"),
    ),
]


def get_cli(key: str) -> SubscriptionCli:
    for cli in SUBSCRIPTION_CLIS:
        if cli.key == key:
            return cli
    raise LookupError(
        f"CLI de assinatura '{key}' desconhecida. Disponíveis: "
        f"{', '.join(c.key for c in SUBSCRIPTION_CLIS)}"
    )


def available_clis() -> list[SubscriptionCli]:
    return [cli for cli in SUBSCRIPTION_CLIS if cli.is_available()]


def _codex_configured_model() -> str | None:
    """Lê apenas o modelo global do Codex, sem carregar/expor outros campos.

    O projeto ainda suporta Python 3.10, portanto a leitura deliberadamente
    pequena evita depender de ``tomllib`` (Python 3.11+). O modelo global fica
    antes da primeira tabela TOML; modelos de perfis não são efetivos porque o
    Audiofy não passa ``--profile`` ao executar o Codex.
    """
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    config_path = codex_home / "config.toml"
    try:
        contents = config_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    top_level = re.split(r"(?m)^\s*\[", contents, maxsplit=1)[0]
    match = re.search(
        r"(?m)^\s*model\s*=\s*(['\"])([^'\"\r\n]+)\1\s*(?:#.*)?$",
        top_level,
    )
    return match.group(2).strip() if match else None


def configured_model(provider_key: str) -> str | None:
    """Retorna o modelo efetivo configurado para uma CLI, quando detectável."""
    if provider_key == "codex":
        return _codex_configured_model()
    return None


def _extract_json(text: str):
    """Aceita JSON puro ou cercado por ```json ... ``` (CLIs adoram cercas)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=0)
    return json.loads(text[start:])


def chat_json(provider_key: str, system: str, user: str):
    """Executa a CLI de assinatura e retorna um ChatResult com custo zero."""
    from .openrouter import ChatResult

    cli = get_cli(provider_key)
    if not cli.is_available():
        raise SubscriptionError(
            f"A CLI '{cli.binary}' ({cli.name}) não está instalada nesta máquina."
        )
    if cli.args:
        command, stdin = cli.command(system), user
    else:
        command, stdin = [cli.binary], f"{system}\n\n{user}"
    try:
        result = run_cli(command, stdin)
    except subprocess.TimeoutExpired as error:
        raise SubscriptionError(f"{cli.name} excedeu {_TIMEOUT_SECONDS}s.") from error
    except OSError as error:
        raise SubscriptionError(
            f"Não foi possível executar a CLI '{cli.binary}' ({cli.name}): {error}"
        ) from error
    if result.returncode != 0:
        raise SubscriptionError(
            f"{cli.name} falhou (código {result.returncode}): {result.stderr[:300]}"
        )
    try:
        data = _extract_json(result.stdout)
    except (json.JSONDecodeError, ValueError) as error:
        raise SubscriptionError(
            f"{cli.name} não retornou JSON válido: {error}"
        ) from error
    return ChatResult(data=data, cost_usd=0.0, prompt_tokens=0, completion_tokens=0)
