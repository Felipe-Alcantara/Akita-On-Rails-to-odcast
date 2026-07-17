"""Configuração central do Audiofy: env, caminhos, perfis, chaves e apresentadores.

Resolução de configuração (maior prioridade primeiro):
1. variáveis de ambiente `AUDIOFY_*` / `OPENROUTER_API_KEY` (inclusive via .env);
2. perfil ativo (`.audiofy/profiles.json`) e cofre de chaves (`.audiofy/keys.json`);
3. padrões embutidos.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .keystore import KeyStore
from .presenters import Presenter, parse_presenters
from .profiles import ProfileStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
EPISODES_DIR = DATA_DIR / "episodes"
STATE_DIR = PROJECT_ROOT / ".audiofy"  # chaves, perfis e caches locais (gitignored)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} precisa ser um número inteiro.") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} precisa ficar entre {minimum} e {maximum}.")
    return value


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name, str(default))
    try:
        value = float(raw)
    except ValueError as error:
        raise ValueError(f"{name} precisa ser um número.") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} precisa ficar entre {minimum:g} e {maximum:g}.")
    return value


def _load_dotenv(path: Path) -> None:
    """Carrega um .env simples (KEY=VALUE) sem sobrescrever o ambiente."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(PROJECT_ROOT / ".env")

# O clone do blog do Akita continua em data/source/ (compartilhado com o módulo
# akita-articles via variável de ambiente própria dele).
os.environ.setdefault("AKITA_ARTICLES_HOME", str(DATA_DIR / "source"))


def key_store() -> KeyStore:
    return KeyStore(STATE_DIR / "keys.json")


def profile_store() -> ProfileStore:
    return ProfileStore(STATE_DIR / "profiles.json")


def _resolved(env_name: str, profile_value: str) -> str:
    return os.environ.get(env_name) or profile_value


def _default_settings() -> dict:
    profile = profile_store().active()
    return {
        "api_key": key_store().resolve() or "",
        "profile_name": profile.name,
        "text_provider": _resolved("AUDIOFY_TEXT_PROVIDER", profile.text_provider),
        "text_model": _resolved("AUDIOFY_TEXT_MODEL", profile.text_model),
        "audit_model": _resolved("AUDIOFY_AUDIT_MODEL", profile.audit_model),
        "tts_model": _resolved("AUDIOFY_TTS_MODEL", profile.tts_model),
        "presenters": parse_presenters(
            os.environ.get("AUDIOFY_PRESENTERS") or profile.presenters_spec
        ),
    }


@dataclass
class Settings:
    api_key: str = ""
    profile_name: str = ""
    text_provider: str = ""  # "openrouter" ou CLI de assinatura
    text_model: str = ""
    audit_model: str = ""
    tts_model: str = ""
    presenters: list[Presenter] = field(default_factory=list)
    # O Gemini TTS via OpenRouter só aceita "pcm" (cru, 16-bit mono); o pipeline
    # embrulha em WAV. Modelos que suportem "mp3"/"wav" podem trocar via env.
    tts_format: str = field(default_factory=lambda: os.environ.get("AUDIOFY_TTS_FORMAT", "pcm"))
    tts_sample_rate: int = field(
        default_factory=lambda: int(os.environ.get("AUDIOFY_TTS_SAMPLE_RATE", "24000"))
    )
    tts_retry_attempts: int = field(
        default_factory=lambda: _env_int("AUDIOFY_TTS_RETRY_ATTEMPTS", 5, 1, 20)
    )
    tts_retry_base_seconds: float = field(
        default_factory=lambda: _env_float("AUDIOFY_TTS_RETRY_BASE_SECONDS", 2, 0, 300)
    )
    tts_retry_max_seconds: float = field(
        default_factory=lambda: _env_float("AUDIOFY_TTS_RETRY_MAX_SECONDS", 30, 0, 900)
    )

    def __post_init__(self) -> None:
        if not 1 <= self.tts_retry_attempts <= 20:
            raise ValueError("tts_retry_attempts precisa ficar entre 1 e 20.")
        if self.tts_retry_base_seconds < 0 or self.tts_retry_max_seconds < 0:
            raise ValueError("Os intervalos de retry do TTS não podem ser negativos.")
        defaults = _default_settings()
        for name, value in defaults.items():
            if not getattr(self, name):
                setattr(self, name, value)

    def require_api_key(self) -> str:
        if not self.api_key:
            raise RuntimeError(
                "Nenhuma chave do OpenRouter configurada. Use o menu 'Chaves & saldo' "
                "(fica em .audiofy/keys.json, fora do Git) ou defina OPENROUTER_API_KEY."
            )
        return self.api_key
