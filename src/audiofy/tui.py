"""Componentes compartilhados da interface de terminal do Audiofy."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import questionary
from questionary import Choice, Style
from rich.console import Console
from rich.panel import Panel

_STYLE = Style(
    [
        ("qmark", "fg:#c084fc bold"),
        ("question", "bold"),
        ("answer", "fg:#a855f7 bold"),
        ("pointer", "fg:#c084fc bold"),
        ("highlighted", "fg:#c084fc bold"),
        ("selected", "fg:#4ade80"),
        ("instruction", "fg:#71717a"),
    ]
)
_CONSOLE = Console()


def show_header(source_key: str, running_count: int) -> None:
    """Desenha o cabeçalho do menu com o estado operacional relevante."""
    status = (
        f"[yellow]⚡ {running_count} geração(ões) consumindo créditos[/yellow]"
        if running_count
        else "[green]● nenhuma geração ativa[/green]"
    )
    _CONSOLE.print(
        Panel.fit(
            f"[bold #c084fc]🎙️ Audiofy Content AI[/bold #c084fc]\n"
            f"[dim]Fonte ativa:[/dim] {source_key}  •  {status}",
            border_style="#a855f7",
        )
    )


def choose(
    message: str, options: Sequence[tuple[str, Any]], default: Any | None = None
) -> Any | None:
    """Exibe uma seleção navegável por setas e retorna o valor escolhido."""
    choices = [Choice(title=title, value=value) for title, value in options]
    return questionary.select(
        message,
        choices=choices,
        default=default,
        instruction="(use ↑/↓ e Enter)",
        style=_STYLE,
        qmark="›",
        pointer="❯",
    ).ask()


def text(message: str, default: str = "") -> str | None:
    """Solicita uma entrada textual com estilo consistente."""
    return questionary.text(message, default=default, style=_STYLE, qmark="›").ask()


def multiline_text(message: str, default: str = "") -> str | None:
    """Solicita texto em múltiplas linhas sem abandonar a interface da TUI."""
    return questionary.text(
        message,
        default=default,
        multiline=True,
        instruction="(finalize com Alt+Enter ou Esc e depois Enter)",
        style=_STYLE,
        qmark="›",
    ).ask()


def secret(message: str) -> str | None:
    """Solicita um segredo sem ecoá-lo no terminal."""
    return questionary.password(message, style=_STYLE, qmark="›").ask()


def confirm(message: str, default: bool = False) -> bool:
    """Solicita confirmação explícita para operações sensíveis."""
    return bool(
        questionary.confirm(
            message,
            default=default,
            style=_STYLE,
            qmark="›",
        ).ask()
    )
