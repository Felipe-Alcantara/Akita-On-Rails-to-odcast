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
from typing import Any

from .presenters import DEFAULT_SPEC, parse_presenters


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


_TTS = "google/gemini-3.1-flash-tts-preview"
_PRO = "google/gemini-2.5-pro"
_FLASH = "google/gemini-2.5-flash"

_TRIO_SPEC = (
    "apresentador_a:Kore:curioso, "
    "apresentador_b:Puck:animado, "
    "apresentador_c:Gacrux:analítico"
)
_MESA_SPEC = (
    "mediador:Kore:neutro, "
    "debatedor_a:Puck:animado, "
    "debatedor_b:Gacrux:ponderado, "
    "debatedor_c:Sadachbia:provocador"
)

BUILTIN_PROFILES: list[Profile] = [
    # ── Podcast · 2 apresentadores ───────────────────────────────────────
    Profile(
        name="padrao",
        text_model=_PRO,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec=DEFAULT_SPEC,
        description=(
            "Dois apresentadores (curioso e didático) com roteiro Gemini Pro "
            "e auditoria Flash — equilíbrio diário entre qualidade e custo"
        ),
    ),
    Profile(
        name="economico",
        text_model=_FLASH,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec=DEFAULT_SPEC,
        description=(
            "Dois apresentadores no modelo mais barato (Flash para tudo) "
            "— ideal para rascunhos e testes rápidos"
        ),
    ),
    Profile(
        name="premium-claude",
        text_model="anthropic/claude-sonnet-4.6",
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec=DEFAULT_SPEC,
        description=(
            "Dois apresentadores com roteiro via Claude Sonnet "
            "— variação de estilo frente ao Gemini, auditoria econômica"
        ),
    ),
    # ── Podcast · 3 apresentadores ───────────────────────────────────────
    Profile(
        name="podcast-trio",
        text_model=_PRO,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec=_TRIO_SPEC,
        description=(
            "Três vozes contrastantes (curioso, animado, analítico) "
            "com roteiro Gemini Pro — dinâmica rica de conversa"
        ),
    ),
    Profile(
        name="podcast-trio-economico",
        text_model=_FLASH,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec=_TRIO_SPEC,
        description=(
            "Três vozes contrastantes no modelo mais barato (Flash para tudo) "
            "— trio econômico para rascunhos"
        ),
    ),
    # ── Podcast · 4 apresentadores ───────────────────────────────────────
    Profile(
        name="podcast-mesa-redonda",
        text_model=_PRO,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec=_MESA_SPEC,
        description=(
            "Mediador neutro e três debatedores (animado, ponderado, provocador) "
            "— formato de debate com roteiro Gemini Pro"
        ),
    ),
    # ── Narração solo ────────────────────────────────────────────────────
    Profile(
        name="narrador-unico",
        text_model=_PRO,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec="narrador:Sulafat:caloroso",
        description=(
            "Voz solo calorosa (Sulafat) com roteiro Gemini Pro "
            "— estilo audiolivro, auditoria econômica"
        ),
    ),
    Profile(
        name="narrador-economico",
        text_model=_FLASH,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec="narrador:Sulafat:caloroso",
        description=(
            "Voz solo calorosa (Sulafat) no modelo mais barato (Flash para tudo) "
            "— teste rápido de narração"
        ),
    ),
    Profile(
        name="narrador-premium",
        text_model=_PRO,
        audit_model=_PRO,
        tts_model=_TTS,
        presenters_spec="narrador:Orus:envolvente",
        description=(
            "Voz solo envolvente (Orus) com Gemini Pro em roteiro e auditoria "
            "— máxima qualidade de texto"
        ),
    ),
    Profile(
        name="narrador-assinatura",
        text_model="(assinatura)",
        audit_model="(assinatura)",
        tts_model=_TTS,
        presenters_spec="narrador:Sulafat:caloroso",
        description=(
            "Voz solo calorosa (Sulafat) via assinatura Claude Code "
            "— custo zero no texto, só TTS paga"
        ),
        text_provider="claude-code",
    ),
    # ── Assinaturas (texto por CLI, só TTS paga) ─────────────────────────
    Profile(
        name="assinatura",
        text_model="(assinatura)",
        audit_model="(assinatura)",
        tts_model=_TTS,
        presenters_spec=DEFAULT_SPEC,
        description=(
            "Dois apresentadores via assinatura Claude Code "
            "— custo zero no texto, só TTS paga"
        ),
        text_provider="claude-code",
    ),
    Profile(
        name="assinatura-codex",
        text_model="(assinatura)",
        audit_model="(assinatura)",
        tts_model=_TTS,
        presenters_spec=DEFAULT_SPEC,
        description=(
            "Dois apresentadores via assinatura Codex (OpenAI) "
            "— custo zero no texto, só TTS paga"
        ),
        text_provider="codex",
    ),
    Profile(
        name="assinatura-gemini",
        text_model="(assinatura)",
        audit_model="(assinatura)",
        tts_model=_TTS,
        presenters_spec=DEFAULT_SPEC,
        description=(
            "Dois apresentadores via assinatura Gemini CLI (Google) "
            "— custo zero no texto, só TTS paga"
        ),
        text_provider="gemini-cli",
    ),
]


def profile_from_payload(payload: dict[str, Any]) -> Profile:
    """Valida dados externos e cria um perfil pronto para persistência."""
    from .providers.subscription import SUBSCRIPTION_CLIS

    name = str(payload.get("name", "")).strip()
    if (
        not name
        or len(name) > 64
        or name in {".", ".."}
        or any(character in name for character in "/\\\r\n\0")
    ):
        raise ValueError(
            "O nome do perfil é obrigatório, deve ter até 64 caracteres e não pode "
            "conter barras ou quebras de linha."
        )
    presenters_spec = str(payload.get("presenters_spec", "")).strip()
    provider = str(payload.get("text_provider", "openrouter")).strip() or "openrouter"
    allowed_providers = {"openrouter", *(cli.key for cli in SUBSCRIPTION_CLIS)}
    if provider not in allowed_providers:
        raise ValueError(f"Provedor de texto desconhecido: {provider}")
    if not presenters_spec:
        raise ValueError("É preciso informar pelo menos um apresentador.")
    parse_presenters(presenters_spec)

    tts_model = str(payload.get("tts_model", "")).strip()
    if not tts_model or len(tts_model) > 300:
        raise ValueError("O modelo TTS é obrigatório.")
    if provider == "openrouter":
        text_model = str(payload.get("text_model", "")).strip()
        audit_model = str(payload.get("audit_model", "")).strip()
        if not text_model or not audit_model or len(text_model) > 300 or len(audit_model) > 300:
            raise ValueError("Os modelos de roteiro e auditoria são obrigatórios.")
    else:
        text_model = audit_model = "(assinatura)"

    description = str(payload.get("description", "")).strip()
    if len(description) > 300:
        raise ValueError("A descrição pode ter no máximo 300 caracteres.")
    return Profile(
        name=name,
        text_model=text_model,
        audit_model=audit_model,
        tts_model=tts_model,
        presenters_spec=presenters_spec,
        description=description,
        text_provider=provider,
    )


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
                ensure_ascii=False,
                indent=2,
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

    def is_custom(self, name: str) -> bool:
        """Informa se o perfil foi persistido pelo usuário (inclusive overrides)."""
        return name in self._custom

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
        profile = profile_from_payload(asdict(profile))
        self._custom[profile.name] = profile
        self._flush()

    def remove(self, name: str) -> None:
        if name in {p.name for p in BUILTIN_PROFILES} and name not in self._custom:
            raise ValueError(f"O perfil embutido '{name}' não pode ser removido.")
        self._custom.pop(name, None)
        if self._active == name:
            self._active = "padrao"
        self._flush()
