"""Configuração central do Audiofy: env, caminhos, modelos e apresentadores.

Modelos, vozes e apresentadores são configuração, não regra de negócio.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .presenters import Presenter, parse_presenters

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
EPISODES_DIR = DATA_DIR / "episodes"

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


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


@dataclass
class Settings:
    api_key: str = field(default_factory=lambda: os.environ.get("OPENROUTER_API_KEY", ""))
    text_model: str = field(
        default_factory=lambda: os.environ.get("AUDIOFY_TEXT_MODEL", "google/gemini-2.5-pro")
    )
    audit_model: str = field(
        default_factory=lambda: os.environ.get("AUDIOFY_AUDIT_MODEL", "google/gemini-2.5-flash")
    )
    tts_model: str = field(
        default_factory=lambda: os.environ.get(
            "AUDIOFY_TTS_MODEL", "google/gemini-3.1-flash-tts-preview"
        )
    )
    # O Gemini TTS via OpenRouter só aceita "pcm" (cru, 16-bit mono); o pipeline
    # embrulha em WAV. Modelos que suportem "mp3"/"wav" podem trocar via env.
    tts_format: str = field(default_factory=lambda: os.environ.get("AUDIOFY_TTS_FORMAT", "pcm"))
    tts_sample_rate: int = field(
        default_factory=lambda: int(os.environ.get("AUDIOFY_TTS_SAMPLE_RATE", "24000"))
    )
    presenters: list[Presenter] = field(
        default_factory=lambda: parse_presenters(os.environ.get("AUDIOFY_PRESENTERS", ""))
    )

    def require_api_key(self) -> str:
        if not self.api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY não definida. Crie um arquivo .env na raiz do projeto "
                "(veja .env.example) ou exporte a variável no terminal."
            )
        return self.api_key
