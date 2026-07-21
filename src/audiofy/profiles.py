"""Perfis nomeados de configuração: modelos + apresentadores.

Um perfil agrupa as escolhas de modelo de roteiro, de auditoria, de TTS e a
especificação de apresentadores. Perfis embutidos cobrem os casos comuns;
perfis customizados são persistidos em `.audiofy/profiles.json` (sem segredos).
Variáveis de ambiente `AUDIOFY_*` continuam tendo prioridade sobre o perfil.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .languages import DEFAULT_LANGUAGE, is_supported, supported_codes
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
    # Idioma do episódio gerado: "pt-BR" ou "en".
    language: str = "pt-BR"
    # Modelo passado à CLI de assinatura (ex.: "opus", "gemini-2.5-pro"). Vazio
    # mantém o que a própria CLI tem configurado. Ignorado quando o provedor é
    # o OpenRouter, que usa text_model/audit_model.
    subscription_model: str = ""


_TTS = "google/gemini-3.1-flash-tts-preview"
_PRO = "google/gemini-2.5-pro"
_FLASH = "google/gemini-2.5-flash"
_OPUS = "anthropic/claude-opus-4"
_SONNET = "anthropic/claude-sonnet-4.6"
_HAIKU = "anthropic/claude-haiku-4.5"
_GPT_SOL = "openai/gpt-sol"
_GPT4O = "openai/gpt-4o"
_GPT4O_MINI = "openai/gpt-4o-mini"

_TRIO_SPEC = (
    "apresentador_a:Kore:curioso, apresentador_b:Puck:animado, apresentador_c:Gacrux:analítico"
)
_MESA_SPEC = (
    "mediador:Kore:neutro, "
    "debatedor_a:Puck:animado, "
    "debatedor_b:Gacrux:ponderado, "
    "debatedor_c:Sadachbia:provocador"
)

BUILTIN_PROFILES: list[Profile] = [
    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  Assinatura Claude Code — texto grátis via CLI, só TTS paga        ║
    # ╚══════════════════════════════════════════════════════════════════════╝
    Profile(
        name="claude-code-duo",
        text_model="(assinatura)",
        audit_model="(assinatura)",
        tts_model=_TTS,
        presenters_spec=DEFAULT_SPEC,
        description=(
            "Dois apresentadores via assinatura Claude Code — custo zero no texto, só TTS paga"
        ),
        text_provider="claude-code",
    ),
    Profile(
        name="claude-code-trio",
        text_model="(assinatura)",
        audit_model="(assinatura)",
        tts_model=_TTS,
        presenters_spec=_TRIO_SPEC,
        description=("Três vozes via assinatura Claude Code — trio sem custo de texto"),
        text_provider="claude-code",
    ),
    Profile(
        name="claude-code-mesa-redonda",
        text_model="(assinatura)",
        audit_model="(assinatura)",
        tts_model=_TTS,
        presenters_spec=_MESA_SPEC,
        description=(
            "Mediador + três debatedores via assinatura Claude Code — debate sem custo de texto"
        ),
        text_provider="claude-code",
    ),
    Profile(
        name="claude-code-narrador",
        text_model="(assinatura)",
        audit_model="(assinatura)",
        tts_model=_TTS,
        presenters_spec="narrador:Sulafat:caloroso",
        description=(
            "Voz solo calorosa (Sulafat) via assinatura Claude Code — narração sem custo de texto"
        ),
        text_provider="claude-code",
    ),
    Profile(
        name="claude-code-leitor-reflexivo",
        text_model="(assinatura)",
        audit_model="(assinatura)",
        tts_model=_TTS,
        presenters_spec="narrador:Sulafat:reflexivo e envolvente",
        description=(
            "Leitura reflexiva via assinatura Claude Code — lê o texto e comenta cada parágrafo, sem custo de texto"
        ),
        text_provider="claude-code",
    ),
    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  Assinatura Codex — texto grátis via CLI OpenAI, só TTS paga       ║
    # ╚══════════════════════════════════════════════════════════════════════╝
    Profile(
        name="codex-duo",
        text_model="(assinatura)",
        audit_model="(assinatura)",
        tts_model=_TTS,
        presenters_spec=DEFAULT_SPEC,
        description=(
            "Dois apresentadores via assinatura Codex (OpenAI) — custo zero no texto, só TTS paga"
        ),
        text_provider="codex",
    ),
    Profile(
        name="codex-trio",
        text_model="(assinatura)",
        audit_model="(assinatura)",
        tts_model=_TTS,
        presenters_spec=_TRIO_SPEC,
        description=("Três vozes via assinatura Codex — trio sem custo de texto"),
        text_provider="codex",
    ),
    Profile(
        name="codex-narrador",
        text_model="(assinatura)",
        audit_model="(assinatura)",
        tts_model=_TTS,
        presenters_spec="narrador:Sulafat:caloroso",
        description=(
            "Voz solo calorosa (Sulafat) via assinatura Codex — narração sem custo de texto"
        ),
        text_provider="codex",
    ),
    Profile(
        name="codex-leitor-reflexivo",
        text_model="(assinatura)",
        audit_model="(assinatura)",
        tts_model=_TTS,
        presenters_spec="narrador:Sulafat:reflexivo e envolvente",
        description=(
            "Leitura reflexiva via assinatura Codex — lê o texto e comenta cada parágrafo, sem custo de texto"
        ),
        text_provider="codex",
    ),
    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  Assinatura Gemini CLI — texto grátis via CLI Google, só TTS paga  ║
    # ╚══════════════════════════════════════════════════════════════════════╝
    Profile(
        name="gemini-cli-duo",
        text_model="(assinatura)",
        audit_model="(assinatura)",
        tts_model=_TTS,
        presenters_spec=DEFAULT_SPEC,
        description=(
            "Dois apresentadores via assinatura Gemini CLI — custo zero no texto, só TTS paga"
        ),
        text_provider="gemini-cli",
    ),
    Profile(
        name="gemini-cli-trio",
        text_model="(assinatura)",
        audit_model="(assinatura)",
        tts_model=_TTS,
        presenters_spec=_TRIO_SPEC,
        description=("Três vozes via assinatura Gemini CLI — trio sem custo de texto"),
        text_provider="gemini-cli",
    ),
    Profile(
        name="gemini-cli-narrador",
        text_model="(assinatura)",
        audit_model="(assinatura)",
        tts_model=_TTS,
        presenters_spec="narrador:Sulafat:caloroso",
        description=(
            "Voz solo calorosa (Sulafat) via assinatura Gemini CLI — narração sem custo de texto"
        ),
        text_provider="gemini-cli",
    ),
    Profile(
        name="gemini-cli-leitor-reflexivo",
        text_model="(assinatura)",
        audit_model="(assinatura)",
        tts_model=_TTS,
        presenters_spec="narrador:Sulafat:reflexivo e envolvente",
        description=(
            "Leitura reflexiva via assinatura Gemini CLI — lê o texto e comenta cada parágrafo, sem custo de texto"
        ),
        text_provider="gemini-cli",
    ),
    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  Gemini — modelos Google via OpenRouter API                        ║
    # ╚══════════════════════════════════════════════════════════════════════╝
    Profile(
        name="gemini-duo",
        text_model=_PRO,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec=DEFAULT_SPEC,
        description=(
            "Dois apresentadores com roteiro Gemini Pro e auditoria Flash "
            "— equilíbrio diário entre qualidade e custo"
        ),
    ),
    Profile(
        name="gemini-duo-economico",
        text_model=_FLASH,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec=DEFAULT_SPEC,
        description=(
            "Dois apresentadores no Gemini Flash para tudo — ideal para rascunhos e testes rápidos"
        ),
    ),
    Profile(
        name="gemini-trio",
        text_model=_PRO,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec=_TRIO_SPEC,
        description=(
            "Três vozes (curioso, animado, analítico) com Gemini Pro — dinâmica rica de conversa"
        ),
    ),
    Profile(
        name="gemini-trio-economico",
        text_model=_FLASH,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec=_TRIO_SPEC,
        description=("Três vozes no Gemini Flash — trio econômico para rascunhos"),
    ),
    Profile(
        name="gemini-mesa-redonda",
        text_model=_PRO,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec=_MESA_SPEC,
        description=(
            "Mediador + três debatedores com Gemini Pro — formato de debate com quatro vozes"
        ),
    ),
    Profile(
        name="gemini-narrador",
        text_model=_PRO,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec="narrador:Sulafat:caloroso",
        description=("Voz solo calorosa (Sulafat) com Gemini Pro — estilo audiolivro"),
    ),
    Profile(
        name="gemini-narrador-economico",
        text_model=_FLASH,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec="narrador:Sulafat:caloroso",
        description=("Voz solo (Sulafat) no Gemini Flash — narração barata para testes"),
    ),
    Profile(
        name="gemini-narrador-premium",
        text_model=_PRO,
        audit_model=_PRO,
        tts_model=_TTS,
        presenters_spec="narrador:Orus:envolvente",
        description=(
            "Voz envolvente (Orus) com Gemini Pro em roteiro e auditoria "
            "— máxima qualidade de texto"
        ),
    ),
    Profile(
        name="gemini-leitor-reflexivo",
        text_model=_PRO,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec="narrador:Sulafat:reflexivo e envolvente",
        description=(
            "Leitura reflexiva com Gemini Pro — lê o texto integralmente e comenta cada parágrafo"
        ),
    ),
    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  Claude — modelos Anthropic via OpenRouter API                     ║
    # ╚══════════════════════════════════════════════════════════════════════╝
    Profile(
        name="claude-duo",
        text_model=_OPUS,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec=DEFAULT_SPEC,
        description=(
            "Dois apresentadores com Claude Opus e auditoria Gemini Flash "
            "— máxima qualidade Anthropic"
        ),
    ),
    Profile(
        name="claude-duo-economico",
        text_model=_SONNET,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec=DEFAULT_SPEC,
        description=("Dois apresentadores com Claude Sonnet — custo moderado com estilo Anthropic"),
    ),
    Profile(
        name="claude-trio",
        text_model=_OPUS,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec=_TRIO_SPEC,
        description=(
            "Três vozes (curioso, animado, analítico) com Claude Opus "
            "— trio com máxima qualidade Anthropic"
        ),
    ),
    Profile(
        name="claude-mesa-redonda",
        text_model=_OPUS,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec=_MESA_SPEC,
        description=(
            "Mediador + três debatedores com Claude Opus — debate com máxima qualidade Anthropic"
        ),
    ),
    Profile(
        name="claude-narrador",
        text_model=_OPUS,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec="narrador:Sulafat:caloroso",
        description=("Voz solo calorosa (Sulafat) com Claude Opus — narração premium Anthropic"),
    ),
    Profile(
        name="claude-leitor-reflexivo",
        text_model=_OPUS,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec="narrador:Sulafat:reflexivo e envolvente",
        description=(
            "Leitura reflexiva com Claude Opus — lê o texto integralmente e comenta cada parágrafo"
        ),
    ),
    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  OpenAI — modelos OpenAI via OpenRouter API                        ║
    # ╚══════════════════════════════════════════════════════════════════════╝
    Profile(
        name="openai-duo",
        text_model=_GPT_SOL,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec=DEFAULT_SPEC,
        description=(
            "Dois apresentadores com GPT SOL e auditoria Gemini Flash — máxima qualidade OpenAI"
        ),
    ),
    Profile(
        name="openai-duo-economico",
        text_model=_GPT4O,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec=DEFAULT_SPEC,
        description=("Dois apresentadores com GPT-4o — custo moderado com estilo OpenAI"),
    ),
    Profile(
        name="openai-trio",
        text_model=_GPT_SOL,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec=_TRIO_SPEC,
        description=(
            "Três vozes (curioso, animado, analítico) com GPT SOL "
            "— trio com máxima qualidade OpenAI"
        ),
    ),
    Profile(
        name="openai-mesa-redonda",
        text_model=_GPT_SOL,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec=_MESA_SPEC,
        description=(
            "Mediador + três debatedores com GPT SOL — debate com máxima qualidade OpenAI"
        ),
    ),
    Profile(
        name="openai-narrador",
        text_model=_GPT_SOL,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec="narrador:Sulafat:caloroso",
        description=("Voz solo calorosa (Sulafat) com GPT SOL — narração premium OpenAI"),
    ),
    Profile(
        name="openai-leitor-reflexivo",
        text_model=_GPT_SOL,
        audit_model=_FLASH,
        tts_model=_TTS,
        presenters_spec="narrador:Sulafat:reflexivo e envolvente",
        description=(
            "Leitura reflexiva com GPT SOL — lê o texto integralmente e comenta cada parágrafo"
        ),
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

    # Vira argumento de linha de comando da CLI: aceita só o alfabeto de nomes de
    # modelo, para que nada possa virar uma flag ou um argumento extra.
    subscription_model = str(payload.get("subscription_model", "")).strip()
    if provider == "openrouter":
        subscription_model = ""
    elif subscription_model and (
        len(subscription_model) > 100
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", subscription_model)
    ):
        raise ValueError(
            "O modelo da assinatura deve começar com letra ou número e usar apenas "
            "letras, números, '.', '_', ':' ou '-' (máx. 100 caracteres)."
        )

    description = str(payload.get("description", "")).strip()
    if len(description) > 300:
        raise ValueError("A descrição pode ter no máximo 300 caracteres.")
    language = str(payload.get("language", DEFAULT_LANGUAGE)).strip() or DEFAULT_LANGUAGE
    if not is_supported(language):
        supported = "', '".join(supported_codes())
        raise ValueError(f"Idioma deve ser um de: '{supported}'.")
    return Profile(
        name=name,
        text_model=text_model,
        audit_model=audit_model,
        tts_model=tts_model,
        presenters_spec=presenters_spec,
        description=description,
        text_provider=provider,
        language=language,
        subscription_model=subscription_model,
    )


class ProfileStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._custom: dict[str, Profile] = {}
        self._active: str = "gemini-duo"
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            self._active = data.get("active", "gemini-duo")
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
            return self.get("gemini-duo")

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
            self._active = "gemini-duo"
        self._flush()
