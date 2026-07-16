"""Configuração central: variáveis de ambiente, caminhos e modelos.

Modelos e vozes são configuração, não regra de negócio (ver docs/PLANO-TECNICO.md).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
SOURCE_REPO_DIR = DATA_DIR / "source" / "akitaonrails.github.io"
EPISODES_DIR = DATA_DIR / "episodes"

SOURCE_REPO_URL = "https://github.com/akitaonrails/akitaonrails.github.io.git"

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


@dataclass
class Settings:
    api_key: str = field(default_factory=lambda: os.environ.get("OPENROUTER_API_KEY", ""))
    text_model: str = field(
        default_factory=lambda: os.environ.get("AKITA_TEXT_MODEL", "google/gemini-2.5-pro")
    )
    audit_model: str = field(
        default_factory=lambda: os.environ.get("AKITA_AUDIT_MODEL", "google/gemini-2.5-flash")
    )
    tts_model: str = field(
        default_factory=lambda: os.environ.get(
            "AKITA_TTS_MODEL", "google/gemini-3.1-flash-tts-preview"
        )
    )
    voice_a: str = field(default_factory=lambda: os.environ.get("AKITA_VOICE_A", "Kore"))
    voice_b: str = field(default_factory=lambda: os.environ.get("AKITA_VOICE_B", "Puck"))
    tts_format: str = field(default_factory=lambda: os.environ.get("AKITA_TTS_FORMAT", "mp3"))

    def require_api_key(self) -> str:
        if not self.api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY não definida. Crie um arquivo .env na raiz do projeto "
                "(veja .env.example) ou exporte a variável no terminal."
            )
        return self.api_key
