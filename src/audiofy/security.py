"""Validações de fronteira compartilhadas por fontes e sessões persistidas."""

from __future__ import annotations

import ipaddress
import re
import socket
from collections.abc import Callable
from urllib.parse import urlsplit

Resolver = Callable[..., list[tuple]]


def validate_identifier(value: str, label: str = "identificador", max_length: int = 100) -> str:
    """Aceita identificadores seguros para nomes de arquivos locais."""
    if not isinstance(value, str):
        raise ValueError(f"O {label} precisa ser texto.")
    value = value.strip()
    if (
        not value
        or len(value) > max_length
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value)
    ):
        raise ValueError(
            f"O {label} deve usar somente letras, números, '_' ou '-' "
            f"(máx. {max_length} caracteres)."
        )
    return value


def validate_public_url(url: str, resolver: Resolver = socket.getaddrinfo) -> str:
    """Aceita apenas HTTP(S) público, sem credenciais ou destinos de rede privada."""
    if not isinstance(url, str):
        raise ValueError("A URL precisa ser texto.")
    url = url.strip()
    if not url or len(url) > 2048 or "\n" in url or "\r" in url:
        raise ValueError("A URL está vazia ou excede o limite permitido.")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Use uma URL pública completa começando com http:// ou https://.")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URLs com usuário ou senha incorporados não são permitidas.")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = resolver(parsed.hostname, port, type=socket.SOCK_STREAM)
    except (OSError, ValueError) as error:
        raise ValueError(f"Não foi possível resolver o endereço da URL: {error}") from error
    if not addresses:
        raise ValueError("A URL não possui um endereço de rede válido.")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address[4][0])
        except (IndexError, ValueError) as error:
            raise ValueError("A URL retornou um endereço de rede inválido.") from error
        if not ip.is_global:
            raise ValueError("URLs de rede local, privada ou reservada não são permitidas.")
    return url
