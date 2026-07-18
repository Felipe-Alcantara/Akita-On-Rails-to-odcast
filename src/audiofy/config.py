"""Configuração central do Audiofy: env, caminhos, perfis, chaves e apresentadores.

Resolução de configuração (maior prioridade primeiro):
1. variáveis de ambiente `AUDIOFY_*` e uma chave nomeada explicitamente selecionada;
2. `OPENROUTER_API_KEY` (inclusive via .env), perfil ativo e cofre de chaves;
3. padrões embutidos.
"""

from __future__ import annotations

import json
import os
import re
from copy import copy
from dataclasses import dataclass, field, replace
from pathlib import Path

from .keystore import KeyStore
from .presenters import Presenter, parse_presenters
from .profiles import ProfileStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
EPISODES_DIR = DATA_DIR / "episodes"
STATE_DIR = PROJECT_ROOT / ".audiofy"  # chaves, perfis e caches locais (gitignored)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DOTENV_PROVENANCE_ENV = "AUDIOFY_DOTENV_LOADED_KEYS"
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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


def _dotenv_values(path: Path) -> dict[str, str]:
    """Lê um .env simples sem alterar o ambiente do processo."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        if _ENV_NAME.fullmatch(key):
            values[key] = value
    return values


def _load_dotenv(path: Path) -> frozenset[str]:
    """Carrega o .env sem sobrescrever o shell e registra a origem das chaves."""
    loaded: set[str] = set()
    for key, value in _dotenv_values(path).items():
        if key not in os.environ:
            os.environ[key] = value
            loaded.add(key)
    return frozenset(loaded)


DOTENV_LOADED_KEYS = _load_dotenv(PROJECT_ROOT / ".env")


def desktop_environment(
    dotenv_path: Path | None = None, *, prefer_dotenv: bool = False
) -> dict[str, str]:
    """Prepara o Electron com valores atuais e a origem segura das chaves do .env.

    O processo principal pode durar horas. A marca de procedência permite que ele remova
    somente valores originados no arquivo antes de abrir cada bridge Python, que então relê
    o `.env`. Variáveis definidas explicitamente no shell nunca entram nessa lista.
    """
    path = dotenv_path or PROJECT_ROOT / ".env"
    values = _dotenv_values(path)
    environment = dict(os.environ)
    if prefer_dotenv:
        # O processo do menu pode ter herdado uma chave antiga exportada no shell.
        # O Electron inicia com a configuração visível no .env atual; a prioridade
        # shell continua valendo para a CLI e para o uso direto da API.
        for key, value in values.items():
            environment[key] = value
        provenance = set(values)
    else:
        for key in DOTENV_LOADED_KEYS:
            if key in values:
                environment[key] = values[key]
            else:
                environment.pop(key, None)
        provenance = set(DOTENV_LOADED_KEYS)
    environment[DOTENV_PROVENANCE_ENV] = ",".join(sorted(provenance))
    return environment


def environment_key_source() -> str | None:
    """Informa a procedência da chave do ambiente, sem considerar a seleção do cofre."""
    if not os.environ.get("OPENROUTER_API_KEY"):
        return None
    if "OPENROUTER_API_KEY" in DOTENV_LOADED_KEYS:
        return ".env"
    return "ambiente"


def api_key_source() -> str | None:
    """Informa a origem efetiva da chave sem retornar seu valor."""
    store = key_store()
    if store.prefers_named():
        return store.active_name()
    return environment_key_source() or store.active_name()


def api_key_candidates(settings: Settings) -> list[tuple[str, Settings]]:
    """Retorna a configuração atual e alternativas sem expor os segredos.

    A alternativa do `.env` é importante quando o processo pai herdou uma chave
    antiga do shell; o cofre cobre as demais chaves nomeadas cadastradas no app.
    """
    candidates: list[tuple[str, Settings]] = []
    seen: set[str] = set()

    def add(label: str, key: str | None) -> None:
        if not key or key in seen:
            return
        seen.add(key)
        try:
            candidate = replace(settings, api_key=key)
        except TypeError:
            # Test doubles e integrações antigas podem não ser dataclasses.
            candidate = copy(settings)
            if hasattr(candidate, "api_key"):
                candidate.api_key = key
        candidates.append((label, candidate))

    add("chave atual", getattr(settings, "api_key", None))
    add(".env", _dotenv_values(PROJECT_ROOT / ".env").get("OPENROUTER_API_KEY"))
    try:
        for named in key_store().list_keys():
            add(named.name, named.key)
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    return candidates


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
                "Nenhuma chave do OpenRouter configurada. Use o menu 'Chaves e verificação' "
                "(fica em .audiofy/keys.json, fora do Git) ou defina OPENROUTER_API_KEY."
            )
        return self.api_key
