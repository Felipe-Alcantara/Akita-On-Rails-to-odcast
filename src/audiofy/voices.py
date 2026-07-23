"""Catálogo unificado de vozes por modelo TTS e classificação por tier de custo.

Centraliza o mapeamento modelo TTS → vozes disponíveis para que o frontend,
a TUI e a validação do pipeline usem a mesma fonte de verdade. GEMINI_VOICES
e KOKORO_VOICES continuam em ``openrouter.py`` (compatibilidade); este módulo
os importa e re-exporta via ``TTS_VOICE_CATALOGS``.
"""

from __future__ import annotations

from .providers.openrouter import GEMINI_VOICES, KOKORO_VOICES

# ── Catálogo de vozes por modelo TTS ──────────────────────────────────────────
# Modelos com catálogo conhecido → dict {nome_voz: descrição}.
# Modelos sem catálogo → dict vazio (frontend mostra input de texto livre).

TTS_VOICE_CATALOGS: dict[str, dict[str, str]] = {
    "google/gemini-3.1-flash-tts-preview": GEMINI_VOICES,
    "hexgrad/kokoro-82m": KOKORO_VOICES,
    "canopylabs/orpheus-3b-0.1-ft": {},
    "deepgram/aura-2": {},
    "microsoft/mai-voice-2": {},
    "minimax/speech-2.8-hd": {},
    "minimax/speech-2.8-turbo": {},
    "mistralai/voxtral-mini-tts-2603": {},
    "sesame/csm-1b": {},
    "x-ai/grok-voice-tts-1.0": {},
    "zyphra/zonos-v0.1-hybrid": {},
    "zyphra/zonos-v0.1-transformer": {},
}

# ── Tiers de custo/qualidade ──────────────────────────────────────────────────
# O custo efetivo por milhão de caracteres considera tanto tokens de entrada
# quanto de saída. Para modelos que cobram apenas entrada, o valor é direto;
# para o Gemini TTS (entrada + saída de áudio), o custo efetivo é ~48× maior
# que o input isolado porque a saída domina o custo.

_TIER_ULTRA = "ultra-economico"
_TIER_ECO = "economico"
_TIER_STD = "padrao"
_TIER_PREMIUM = "premium"

TTS_TIERS: dict[str, dict[str, object]] = {
    "hexgrad/kokoro-82m": {
        "tier": _TIER_ULTRA,
        "label": "Ultra-econômico",
        "effective_cost_per_m_chars": 0.62,
    },
    "canopylabs/orpheus-3b-0.1-ft": {
        "tier": _TIER_ECO,
        "label": "Econômico",
        "effective_cost_per_m_chars": 7.0,
    },
    "sesame/csm-1b": {
        "tier": _TIER_ECO,
        "label": "Econômico",
        "effective_cost_per_m_chars": 7.0,
    },
    "zyphra/zonos-v0.1-hybrid": {
        "tier": _TIER_ECO,
        "label": "Econômico",
        "effective_cost_per_m_chars": 7.0,
    },
    "zyphra/zonos-v0.1-transformer": {
        "tier": _TIER_ECO,
        "label": "Econômico",
        "effective_cost_per_m_chars": 7.0,
    },
    "x-ai/grok-voice-tts-1.0": {
        "tier": _TIER_STD,
        "label": "Padrão",
        "effective_cost_per_m_chars": 15.0,
    },
    "mistralai/voxtral-mini-tts-2603": {
        "tier": _TIER_STD,
        "label": "Padrão",
        "effective_cost_per_m_chars": 16.0,
    },
    "microsoft/mai-voice-2": {
        "tier": _TIER_STD,
        "label": "Padrão",
        "effective_cost_per_m_chars": 22.0,
    },
    "deepgram/aura-2": {
        "tier": _TIER_STD,
        "label": "Padrão",
        "effective_cost_per_m_chars": 30.0,
    },
    "google/gemini-3.1-flash-tts-preview": {
        "tier": _TIER_PREMIUM,
        "label": "Premium",
        "effective_cost_per_m_chars": 48.0,
    },
    "minimax/speech-2.8-turbo": {
        "tier": _TIER_PREMIUM,
        "label": "Premium",
        "effective_cost_per_m_chars": 60.0,
    },
    "minimax/speech-2.8-hd": {
        "tier": _TIER_PREMIUM,
        "label": "Premium",
        "effective_cost_per_m_chars": 100.0,
    },
}

# ── Mapa agregado para busca rápida ──────────────────────────────────────────

ALL_KNOWN_VOICES: dict[str, str] = {}
for _catalog in TTS_VOICE_CATALOGS.values():
    ALL_KNOWN_VOICES.update(_catalog)


def voices_for_model(tts_model_id: str) -> dict[str, str] | None:
    """Catálogo de vozes do modelo, ou ``None`` se não há catálogo conhecido."""
    return TTS_VOICE_CATALOGS.get(tts_model_id)


def is_known_voice(voice: str) -> bool:
    """Verifica se a voz existe em qualquer catálogo registrado."""
    return voice in ALL_KNOWN_VOICES


def voice_style(voice: str) -> str:
    """Descrição de estilo da voz em qualquer catálogo, ou string vazia."""
    return ALL_KNOWN_VOICES.get(voice, "")
