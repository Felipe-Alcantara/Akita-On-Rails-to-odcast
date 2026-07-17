"""Perfis nomeados de configuração: modelos + apresentadores.

Um perfil agrupa as escolhas de modelo de roteiro, de auditoria, de TTS e a
especificação de apresentadores. Perfis embutidos cobrem os casos comuns;
perfis customizados são persistidos em `.audiofy/profiles.json` (sem segredos).
Variáveis de ambiente `AUDIOFY_*` continuam tendo prioridade sobre o perfil.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from .presenters import DEFAULT_SPEC


@dataclass(frozen=True)
class Profile:
    name: str
    text_model: str
    audit_model: str
    tts_model: str
    presenters_spec: str
    description: str = ""
    # Provedor das etapas de texto: "openrouter" (API, custo por token) ou uma
    # CLI de assinatura ("claude-code", "gemini-cli", "codex") com custo zero.
    text_provider: str = "openrouter"


BUILTIN_PROFILES: list[Profile] = [
    Profile(
        name="padrao",
        text_model="google/gemini-2.5-pro",
        audit_model="google/gemini-2.5-flash",
        tts_model="google/gemini-3.1-flash-tts-preview",
        presenters_spec=DEFAULT_SPEC,
        description="Qualidade no roteiro, auditoria econômica, dois apresentadores",
    ),
    Profile(
        name="economico",
        text_model="google/gemini-2.5-flash",
        audit_model="google/gemini-2.5-flash",
        tts_model="google/gemini-3.1-flash-tts-preview",
        presenters_spec=DEFAULT_SPEC,
        description="Tudo no modelo mais barato — bom para experimentar",
    ),
    Profile(
        name="narrador-unico",
        text_model="google/gemini-2.5-pro",
        audit_model="google/gemini-2.5-flash",
        tts_model="google/gemini-3.1-flash-tts-preview",
        presenters_spec="narrador:Sulafat:caloroso",
        description="Narração solo, estilo audiolivro",
    ),
    Profile(
        name="assinatura",
        text_model="(assinatura)",
        audit_model="(assinatura)",
        tts_model="google/gemini-3.1-flash-tts-preview",
        presenters_spec=DEFAULT_SPEC,
        description="Texto pela CLI de assinatura (custo zero); só o TTS paga API",
        text_provider="claude-code",
    ),
]


class ProfileStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._custom: dict[str, Profile] = {}
        self._active: str = "padrao"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            self._active = data.get("active", "padrao")
            self._custom = {
                name: Profile(**fields) for name, fields in data.get("profiles", {}).items()
            }

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {
                    "active": self._active,
                    "profiles": {name: asdict(p) for name, p in self._custom.items()},
                },
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

    # ── Consulta ─────────────────────────────────────────────────────────

    def list_profiles(self) -> list[Profile]:
        merged = {p.name: p for p in BUILTIN_PROFILES}
        merged.update(self._custom)
        return list(merged.values())

    def get(self, name: str) -> Profile:
        for profile in self.list_profiles():
            if profile.name == name:
                return profile
        raise LookupError(f"Perfil '{name}' não existe.")

    def active(self) -> Profile:
        try:
            return self.get(self._active)
        except LookupError:
            return self.get("padrao")

    # ── Operações ────────────────────────────────────────────────────────

    def set_active(self, name: str) -> None:
        self.get(name)  # valida existência
        self._active = name
        self._flush()

    def save(self, profile: Profile) -> None:
        """Cria/atualiza um perfil customizado (pode sombrear um embutido)."""
        self._custom[profile.name] = profile
        self._flush()

    def remove(self, name: str) -> None:
        if name in {p.name for p in BUILTIN_PROFILES} and name not in self._custom:
            raise ValueError(f"O perfil embutido '{name}' não pode ser removido.")
        self._custom.pop(name, None)
        if self._active == name:
            self._active = "padrao"
        self._flush()
