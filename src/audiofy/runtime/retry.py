"""Política reutilizável de retry com backoff exponencial e jitter."""

from __future__ import annotations

import random
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    """Calcula esperas limitadas entre tentativas de uma operação idempotente."""

    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float
    jitter_ratio: float = 0.2

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("A política de retry exige pelo menos uma tentativa.")
        if self.base_delay_seconds < 0 or self.max_delay_seconds < 0:
            raise ValueError("Os intervalos de retry não podem ser negativos.")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("O jitter do retry deve ficar entre 0 e 1.")

    def delay_after(self, failed_attempt: int) -> float:
        """Retorna a espera após `failed_attempt` (a primeira tentativa vale 1)."""
        if failed_attempt < 1:
            raise ValueError("A tentativa que falhou deve ser maior ou igual a 1.")
        base = min(
            self.max_delay_seconds,
            self.base_delay_seconds * (2 ** (failed_attempt - 1)),
        )
        return min(
            self.max_delay_seconds,
            base + random.uniform(0, base * self.jitter_ratio),
        )
