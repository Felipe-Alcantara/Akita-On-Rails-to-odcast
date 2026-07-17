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
import re
import shutil
import subprocess
from dataclasses import dataclass

_TIMEOUT_SECONDS = 900


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
        result = subprocess.run(
            command, input=stdin, capture_output=True, text=True,
            timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise SubscriptionError(f"{cli.name} excedeu {_TIMEOUT_SECONDS}s.") from error
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
